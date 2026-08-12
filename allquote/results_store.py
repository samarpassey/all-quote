"""Phase 3 batch-run persistence. See PLAN.md Task 7 Phase 3 (B1).

Files, not a database. Every QuoteResult/NormalizedQuote pair lands under
data/runs/<run_id>/results/, keyed by (run_id, distinct_rate_source_id,
attempt) via the filename. A later invocation gets a fresh run_id and never
touches an earlier run's files — "supersede" means data/runs/latest.json is
repointed to the new run_id, never that old files are overwritten in place,
so lineage across re-runs survives on disk.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from allquote.planner import PlannedRoute
from allquote.schemas import NormalizedQuote, QuoteResult

RUNS_ROOT = Path("data/runs")


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid4().hex[:6]}"


def run_dir(run_id: str, *, runs_root: Path = RUNS_ROOT) -> Path:
    return runs_root / run_id


def _safe_id(distinct_rate_source_id: str) -> str:
    return distinct_rate_source_id.replace("/", "_")


def save_manifest(
    run_id: str,
    planned_routes: list[PlannedRoute],
    *,
    started_at: datetime,
    runs_root: Path = RUNS_ROOT,
    notes: list[str] = (),
) -> Path:
    """One row per distinct rate source, recording which registry row was
    chosen as representative and which were suppressed as non-primary —
    so a run report can tell "deliberately suppressed as a known duplicate"
    (named here) apart from "never planned at all" (absent here entirely).

    `notes`: free-text, run-level context a caller wants attached to this
    run specifically (e.g. "supersedes run X because Y") -- report.py
    collects these across every merged run so the reason a run superseded
    an earlier one is queryable from the run report, not just tribal
    knowledge in a chat transcript.
    """
    path = run_dir(run_id, runs_root=runs_root) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "notes": list(notes),
        "routes": [
            {
                "distinct_rate_source_id": p.distinct_rate_source_id,
                "registry_id": p.registry_id,
                "suppressed_registry_ids": list(p.suppressed_registry_ids),
                "lane": p.lane,
                "tier": p.tier,
                "model_tier": p.model_tier,
            }
            for p in planned_routes
        ],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def save_result(
    run_id: str,
    distinct_rate_source_id: str,
    attempt: int,
    *,
    quote_result: QuoteResult,
    normalized_quote: NormalizedQuote,
    origin: str,
    runs_root: Path = RUNS_ROOT,
) -> Path:
    """`origin` is a plain label for the run report: "executed" (a fresh
    subprocess ran this batch), "carried_from_probe" (outcome + evidence
    already on file from an earlier live probe, not re-attempted), or
    "derived" (resolved from registry metadata, no contact made)."""
    path = (
        run_dir(run_id, runs_root=runs_root)
        / "results"
        / f"{_safe_id(distinct_rate_source_id)}__attempt-{attempt}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "distinct_rate_source_id": distinct_rate_source_id,
        "attempt": attempt,
        "origin": origin,
        "quote_result": json.loads(quote_result.model_dump_json()),
        "normalized_quote": json.loads(normalized_quote.model_dump_json()),
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def mark_not_attempted(
    run_id: str,
    distinct_rate_source_id: str,
    reason: str,
    *,
    runs_root: Path = RUNS_ROOT,
) -> Path:
    path = (
        run_dir(run_id, runs_root=runs_root)
        / "results"
        / f"{_safe_id(distinct_rate_source_id)}__not_attempted.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"distinct_rate_source_id": distinct_rate_source_id, "reason": reason}, indent=2
        )
    )
    return path


def mark_latest(run_id: str, *, runs_root: Path = RUNS_ROOT) -> Path:
    path = runs_root / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"run_id": run_id}, indent=2))
    return path


def load_latest_run_id(*, runs_root: Path = RUNS_ROOT) -> str | None:
    path = runs_root / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())["run_id"]


def load_manifest(run_id: str, *, runs_root: Path = RUNS_ROOT) -> dict:
    path = run_dir(run_id, runs_root=runs_root) / "manifest.json"
    return json.loads(path.read_text())


def list_run_ids(*, runs_root: Path = RUNS_ROOT) -> list[str]:
    """Every run directory under `runs_root`, oldest first. `run_id` is a
    `YYYYMMDDTHHMMSSZ-<hex>` stamp, so lexicographic sort is chronological.
    Excludes `latest.json` itself. A caller wanting the full history of a
    batch (base run plus any later partial re-runs that supersede part of
    it — see this module's docstring) walks this list in order rather than
    reading only `latest.json`, which points at the most recent run and
    nothing else."""
    if not runs_root.exists():
        return []
    return sorted(p.name for p in runs_root.iterdir() if p.is_dir())


def list_results(run_id: str, *, runs_root: Path = RUNS_ROOT) -> list[dict]:
    results_dir = run_dir(run_id, runs_root=runs_root) / "results"
    if not results_dir.exists():
        return []
    return [json.loads(path.read_text()) for path in sorted(results_dir.glob("*.json"))]
