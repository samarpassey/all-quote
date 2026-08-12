"""Phase 3 batch runner. See PLAN.md Task 7 Phase 3 (B1-B6) / the approved
plan.

Runs the full planner queue end to end: derived lane in-process (free, no
browser, no model, no network), contact lane as `python -m allquote.executor
run --live` subprocesses (reuses that CLI's existing 1-attempt-plus-1-retry
policy via run_route()'s internal is_transient use — this module does not
reimplement bounded-attempt logic). Every outcome normalizes through the
existing normalize_quote immediately and is persisted via results_store.

One route failing — a bad subprocess, unparseable output, a killed process —
must never abort the batch: `_execute_contact_route` and the derived-lane
loop each wrap their work in try/except and fall back to a synthetic
`unreachable` QuoteResult, then continue.
"""

import functools
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from allquote import planner, registry, results_store, vault
from allquote.evidence import write_evidence_record
from allquote.executor import _build_quote_result  # generic QuoteResult builder, not gate-specific
from allquote.normalize import normalize_quote
from allquote.normalize_basis import derive_requested_basis
from allquote.redact import safe_write_evidence
from allquote.schemas import IntakeProfile, MarketRecord, NormalizedQuote, QuoteResult, RequestedBasis, Status

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = Path("data/evidence")

PER_ROUTE_HARD_CAP_S = 190.0
INTERNAL_TIMEOUT_S = 160.0
DEFAULT_BUDGET_S = 3600.0
MAX_CONCURRENT = 3

# Already-probed routes carried forward as-is (Task 7 Phase 2): outcome and
# evidence are already on file, re-running would waste budget for no new
# information. Rates.ca and LowestRates.ca are the one exception — their
# probe outcome was produced by the pre-fix hard_ineligibility bug, so they
# are re-executed to carry a correctly-classified result.
_SCRATCH = Path(
    "/private/tmp/claude-501/-Users-samar-dev-all-quote-starter/"
    "63ba3f34-a3a7-4e01-849e-47b209489e71/scratchpad"
)
_PROBE_1, _PROBE_2 = _SCRATCH / "probe_phase2_results.json", _SCRATCH / "probe_phase2b_results.json"
_CARRY_FORWARD: dict[str, tuple[Path, int]] = {
    "route-allstate-canada": (_PROBE_1, 0),
    "route-co-operators": (_PROBE_1, 1),
    "route-desjardins-insurance": (_PROBE_1, 2),
    "route-surex": (_PROBE_2, 2),
}


def _load_carried_quote_result(registry_id: str) -> QuoteResult:
    path, index = _CARRY_FORWARD[registry_id]
    entry = json.loads(path.read_text())[index]
    assert entry["market_id"] == registry_id
    return QuoteResult.model_validate(entry["quote_result"])


# --- derived lane ------------------------------------------------------------
def run_derived_route(
    record: MarketRecord,
    *,
    profile: IntakeProfile,
    run_id: str,
    basis: RequestedBasis,
    evidence_root: Path,
    vault_path: Path,
    vault_key: str | None,
) -> tuple[QuoteResult, NormalizedQuote]:
    outcome = planner.resolve_derived_outcome(record)
    now = datetime.now(timezone.utc)
    destination = evidence_root / run_id / "derived" / record.registry_id / "derived_outcome.json"
    payload = json.dumps(
        {"registry_id": record.registry_id, "reason": outcome.reason, "cited_fields": outcome.cited_fields},
        indent=2, default=str,
    )
    safe_write_evidence(payload, "text", destination, profile=profile, vault_path=vault_path, vault_key=vault_key)
    evidence = write_evidence_record(
        registry_id=record.registry_id,
        kind="document",
        timestamp=now,
        source_url_or_phone=record.source_url,
        artifact_path=destination,
        provenance="derived",
    )
    quote_result = _build_quote_result(
        record,
        status=outcome.status,
        is_exact_quote=False,
        failure_reason=outcome.reason,
        next_action=None,
        evidence=evidence,
        confidence="low",
    )
    _, normalized = normalize_quote(
        quote_result, [], basis,
        distribution_type=record.distribution_type,
        requested_basis_id=basis.requested_basis_id,
        captured_at=now,
        evidence_ids=[evidence.evidence_id],
    )
    return quote_result, normalized


# --- contact lane -------------------------------------------------------------


def _run_contact_subprocess(
    market_id: str,
    model: str,
    *,
    internal_timeout_s: float = INTERNAL_TIMEOUT_S,
    hard_cap_s: float = PER_ROUTE_HARD_CAP_S,
) -> dict[str, Any]:
    """Same mechanism the Task 7 Phase 2 probes used: subprocess in its own
    process group so a hard-cap timeout can kill the whole tree (including
    Chromium), not just the python parent.

    `internal_timeout_s` is handed to the executor CLI's own --timeout-seconds
    (the budget run_route() gives one browser attempt); `hard_cap_s` is this
    function's external kill trigger and must stay comfortably above it so a
    route that legitimately times out internally gets to report that
    cleanly, rather than being SIGKILLed mid-write."""
    cmd = [
        sys.executable, "-m", "allquote.executor", "run",
        "--market-id", market_id, "--live",
        "--timeout-seconds", str(int(internal_timeout_s)), "--max-steps", "25",
    ]
    env = dict(os.environ, EXECUTOR_MODEL=model)
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd, cwd=REPO_ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    killed = False
    try:
        stdout, stderr = proc.communicate(input="y\n", timeout=hard_cap_s)
    except subprocess.TimeoutExpired:
        killed = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = proc.communicate()
    elapsed = time.monotonic() - started

    quote_result_dict = None
    if not killed and proc.returncode == 0:
        try:
            quote_result_dict = json.loads(stdout[stdout.index("{"):])
        except (ValueError, json.JSONDecodeError):
            quote_result_dict = None

    return {
        "market_id": market_id, "elapsed_s": elapsed, "killed": killed,
        "returncode": proc.returncode, "quote_result": quote_result_dict,
        "stdout_tail": stdout[-2000:], "stderr_tail": stderr[-2000:],
    }


def _synthetic_failure_result(
    record: MarketRecord, reason: str, *, run_id: str, evidence_root: Path,
    profile: IntakeProfile, vault_path: Path, vault_key: str | None,
) -> QuoteResult:
    """Fallback when a route's subprocess produced no usable QuoteResult
    (killed on the hard cap, crashed, unparseable stdout) — never let this
    abort the batch (B4); record it as unreachable with real evidence of
    the failure instead."""
    now = datetime.now(timezone.utc)
    destination = evidence_root / run_id / "batch_failures" / record.registry_id / "failure.json"
    safe_write_evidence(
        json.dumps({"registry_id": record.registry_id, "reason": reason}, indent=2),
        "text", destination, profile=profile, vault_path=vault_path, vault_key=vault_key,
    )
    evidence = write_evidence_record(
        registry_id=record.registry_id, kind="document", timestamp=now,
        source_url_or_phone=record.quote_url or record.source_url,
        artifact_path=destination, provenance="observed",
    )
    return _build_quote_result(
        record, status=Status.UNREACHABLE, is_exact_quote=False,
        failure_reason=reason, next_action="retry later", evidence=evidence, confidence="low",
    )


ContactRunner = Callable[[str, str], dict[str, Any]]


def _execute_contact_route(
    planned: planner.PlannedRoute, record: MarketRecord, *, contact_runner: ContactRunner,
    model: str, run_id: str, evidence_root: Path, profile: IntakeProfile,
    vault_path: Path, vault_key: str | None, hard_cap_s: float = PER_ROUTE_HARD_CAP_S,
) -> QuoteResult:
    try:
        outcome = contact_runner(record.registry_id, model)
        if outcome["quote_result"] is not None:
            return QuoteResult.model_validate(outcome["quote_result"])
        reason = (
            f"batch hard-cap kill after {hard_cap_s:.0f}s" if outcome["killed"]
            else f"subprocess exited rc={outcome['returncode']} with no parseable QuoteResult"
        )
    except Exception as exc:  # noqa: BLE001 - isolation boundary, see B4
        reason = f"batch orchestration error: {type(exc).__name__}: {exc}"
    return _synthetic_failure_result(
        record, reason, run_id=run_id, evidence_root=evidence_root,
        profile=profile, vault_path=vault_path, vault_key=vault_key,
    )


# --- orchestrator -------------------------------------------------------------


def run_batch(
    *,
    records: list[MarketRecord] | None = None,
    profile: IntakeProfile | None = None,
    contact_runner: ContactRunner | None = None,
    evidence_root: Path = EVIDENCE_ROOT,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
    runs_root: Path = results_store.RUNS_ROOT,
    budget_s: float = DEFAULT_BUDGET_S,
    run_id: str | None = None,
    internal_timeout_s: float = INTERNAL_TIMEOUT_S,
    hard_cap_s: float = PER_ROUTE_HARD_CAP_S,
    notes: list[str] = (),
) -> str:
    """`run_id`: pass a pre-generated id (results_store.new_run_id()) when a
    caller needs to know it before this function returns -- e.g. app.py's run
    console starts this in a background thread and polls
    data/runs/<run_id>/manifest.json, which save_manifest() below writes
    almost immediately, long before any route finishes.

    `internal_timeout_s`/`hard_cap_s`: per-route timeout override, default
    unchanged (160s/190s) so existing callers (app.py's run console, tests)
    see zero behaviour change unless they explicitly ask for something else.
    Only applied when `contact_runner` is left at its default -- an
    explicitly-passed contact_runner (e.g. a test fake) is used as-is."""
    from allquote import intake

    if contact_runner is None:
        contact_runner = functools.partial(
            _run_contact_subprocess, internal_timeout_s=internal_timeout_s, hard_cap_s=hard_cap_s
        )

    records = records if records is not None else registry.list_records()
    profile = profile if profile is not None else intake.load_profile()
    assert profile is not None, "no stored intake profile — run intake first"

    records_by_id = {r.registry_id: r for r in records}
    planned = planner.plan_routes(records)

    run_id = run_id or results_store.new_run_id()
    batch_started = datetime.now(timezone.utc)
    batch_deadline = time.monotonic() + budget_s
    results_store.save_manifest(run_id, planned, started_at=batch_started, runs_root=runs_root, notes=notes)

    basis = derive_requested_basis(
        profile.coverage_benchmark, requested_basis_id=f"basis-{run_id}", captured_at=batch_started
    )

    def _save(distinct_id: str, qr: QuoteResult, origin: str) -> None:
        _, nq = normalize_quote(
            qr, [], basis, distribution_type=records_by_id[qr.source.registry_id].distribution_type,
            requested_basis_id=basis.requested_basis_id, captured_at=datetime.now(timezone.utc),
            evidence_ids=[],
        )
        results_store.save_result(run_id, distinct_id, 1, quote_result=qr, normalized_quote=nq, origin=origin, runs_root=runs_root)

    # B2: derived lane, all 59, in-process, free.
    for p in planned:
        if p.lane != "derived":
            continue
        record = records_by_id[p.registry_id]
        qr, nq = run_derived_route(
            record, profile=profile, run_id=run_id, basis=basis, evidence_root=evidence_root,
            vault_path=vault_path, vault_key=vault_key,
        )
        results_store.save_result(run_id, p.distinct_rate_source_id, 1, quote_result=qr, normalized_quote=nq, origin="derived", runs_root=runs_root)

    # Contact lane: carry-forward (already probed, not re-run) + to-execute.
    contact = [p for p in planned if p.lane == "contact"]
    carried = [p for p in contact if p.registry_id in _CARRY_FORWARD]
    to_execute = [p for p in contact if p.registry_id not in _CARRY_FORWARD]

    for p in carried:
        qr = _load_carried_quote_result(p.registry_id)
        _save(p.distinct_rate_source_id, qr, "carried_from_probe")

    model_env = {"smart": os.environ.get("MODEL_SMART", ""), "cheap": os.environ.get("MODEL_CHEAP", "")}
    not_attempted: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
        for i in range(0, len(to_execute), MAX_CONCURRENT):
            chunk = to_execute[i:i + MAX_CONCURRENT]
            if time.monotonic() + hard_cap_s > batch_deadline:
                for p in chunk:
                    results_store.mark_not_attempted(run_id, p.distinct_rate_source_id, "batch wall-clock budget exhausted", runs_root=runs_root)
                    not_attempted.append(p.distinct_rate_source_id)
                continue
            futures = {
                pool.submit(
                    _execute_contact_route, p, records_by_id[p.registry_id],
                    contact_runner=contact_runner, model=model_env[p.model_tier],
                    run_id=run_id, evidence_root=evidence_root, profile=profile,
                    vault_path=vault_path, vault_key=vault_key, hard_cap_s=hard_cap_s,
                ): p
                for p in chunk
            }
            for fut in as_completed(futures):
                p = futures[fut]
                qr = fut.result()
                _save(p.distinct_rate_source_id, qr, "executed")

    results_store.mark_latest(run_id, runs_root=runs_root)
    if not_attempted:
        print(f"NOT ATTEMPTED (budget): {not_attempted}", file=sys.stderr)
    return run_id


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    run_id = run_batch()
    print(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
