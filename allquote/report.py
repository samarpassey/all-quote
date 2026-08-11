"""Run-report metrics. See PLAN.md's metrics task and docs/SCHEMAS.md's
"Metrics" section.

Merges Phase 3 batch-run history from data/runs/ into one effective
per-distinct-rate-source view (a later, partial re-run supersedes part of an
earlier full run -- see results_store.py's module docstring), builds a
READ-ONLY registry snapshot reflecting those outcomes, and computes all five
docs/SCHEMAS.md coverage metrics against it.

Pure computation over persisted data: no browser, no network, no writes to
data/allquote.db. See build_registry_snapshot()'s docstring for why this is
deliberately NOT the permanent registry write-back docs/ARCHITECTURE.md's
data-flow rule 5 describes -- that remains unbuilt; this module works around
its absence for reporting purposes only, and says so in every report it
prints.
"""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from allquote import metrics, registry, results_store
from allquote.schemas import MarketRecord, QuoteResult, Status


@dataclass(frozen=True)
class MergedRun:
    run_ids: tuple[str, ...]  # every run folder found, oldest first
    primary_registry_id: dict[str, str]  # distinct_rate_source_id -> primary registry_id
    payloads: dict[str, dict]  # distinct_rate_source_id -> raw result-or-not_attempted json


def merge_runs(*, runs_root: Path = results_store.RUNS_ROOT) -> MergedRun:
    """Walks every run directory chronologically; a later run's manifest
    entry and result payload replace an earlier run's for the same
    distinct_rate_source_id. This is the general form of "a 3-route re-run
    supersedes part of a 79-route batch": it doesn't special-case which run
    is "the base" -- any run found later on disk simply wins for the routes
    it covers, matching results_store.py's own supersession model."""
    run_ids = results_store.list_run_ids(runs_root=runs_root)
    primary_registry_id: dict[str, str] = {}
    payloads: dict[str, dict] = {}
    for run_id in run_ids:
        manifest = results_store.load_manifest(run_id, runs_root=runs_root)
        for route in manifest["routes"]:
            primary_registry_id[route["distinct_rate_source_id"]] = route["registry_id"]
        for payload in results_store.list_results(run_id, runs_root=runs_root):
            payloads[payload["distinct_rate_source_id"]] = payload
    return MergedRun(
        run_ids=tuple(run_ids), primary_registry_id=primary_registry_id, payloads=payloads
    )


def effective_quote_results(merged: MergedRun) -> list[tuple[QuoteResult, str]]:
    """(QuoteResult, origin) pairs, one per distinct source that produced a
    real result. `not_attempted` markers (budget exhausted before this
    route ran) carry no QuoteResult and are excluded here -- there is no
    evidence to evaluate -- but the distinct source they belong to stays
    `unresolved` in the registry snapshot below, so it is never silently
    dropped from market_completion's denominator; it is just correctly
    never counted as resolved."""
    out: list[tuple[QuoteResult, str]] = []
    for payload in merged.payloads.values():
        if "quote_result" not in payload:
            continue
        out.append((QuoteResult.model_validate(payload["quote_result"]), payload["origin"]))
    return out


def build_registry_snapshot(
    base_registry: list[MarketRecord], merged: MergedRun
) -> list[MarketRecord]:
    """Overrides `status` on the PRIMARY registry row for every distinct
    source the merged run actually resolved. Two things this deliberately
    does NOT do:

    1. Touch non-primary (duplicate) rows. planner.py's _select_primary
       leaves those "deliberately... untouched in the registry" until Task
       8b's dedupe resolver (deferred) formally assigns them
       duplicate_rate_source. Overriding them here would fabricate
       verification that never happened for a route we never separately
       attempted.
    2. Synthesize last_verified_at from the run's own timestamp. That field
       means "a human, via registry.verify(), confirmed this route" -- a
       narrower and more deliberate claim than "a batch attempt produced
       some status." Stamping it here would make freshness trivially ~100%
       for anything the batch touched even once, which is exactly the
       "converges toward 100% by construction" failure metrics.py's module
       docstring warns against for market_completion, just relocated to a
       different metric. Left alone, freshness instead reports how much of
       the registry has actually been re-verified (registry.verify()
       called on it) during the hackathon window -- a real, and currently
       low, number.

    Does NOT write to data/allquote.db -- this snapshot exists only in
    memory for the duration of one report."""
    status_by_registry_id: dict[str, Status] = {}
    for distinct_id, registry_id in merged.primary_registry_id.items():
        payload = merged.payloads.get(distinct_id)
        if payload is None or "quote_result" not in payload:
            continue  # never attempted (budget exhausted) -> stays unresolved
        status_by_registry_id[registry_id] = Status(payload["quote_result"]["outcome"]["status"])

    return [
        record if (new_status := status_by_registry_id.get(record.registry_id)) is None
        else record.model_copy(update={"status": new_status})
        for record in base_registry
    ]


@dataclass(frozen=True)
class CoverageReport:
    run_ids: tuple[str, ...]
    registry_total_rows: int
    registry_distinct_sources: int
    verified_applicable: int
    market_completion: float | None
    comparable_quote_yield: float | None
    freshness: float | None
    evidence_rate: metrics.EvidenceRate
    duplicate_suppression: metrics.DuplicateSuppression
    notes: tuple[str, ...]


NOTES = (
    "market_completion/comparable_quote_yield/freshness denominator is a READ-ONLY, "
    "in-memory registry snapshot (build_registry_snapshot) built from merged run results -- "
    "not data/allquote.db's live status column, which no code path writes back to yet "
    "(docs/ARCHITECTURE.md rule 5 is unimplemented). Only the 79 PRIMARY rows are overridden; "
    "the 32 non-primary/duplicate rows stay unresolved (Task 8b dedupe resolver is deferred).",
    "freshness uses only last_verified_at values already stamped by registry.verify() -- it is "
    "NOT synthesized from this run's timestamp -- so it reflects how much of the registry has "
    "actually been re-verified, not merely re-run. Expect this to be low.",
    "duplicate_suppression.registry_seeded is the seed-time figure (collapsed by "
    "legal_underwriter alone at registry load); duplicate_suppression.runtime_resolved reads 0 "
    "until Task 8b's dedupe resolver lands.",
    "evidence_rate.observed_only excludes derived-lane outcomes (provenance=derived, no market "
    "contacted); evidence_rate.all_outcomes includes them. Both count a derived outcome's "
    "redacted reasoning document as a valid 'redacted artifact' -- see EvidenceRate's docstring.",
)


def compute_report(
    *, db_path: Path = registry.DB_PATH, runs_root: Path = results_store.RUNS_ROOT
) -> CoverageReport:
    base_registry = registry.list_records(db_path=db_path)
    merged = merge_runs(runs_root=runs_root)
    snapshot = build_registry_snapshot(base_registry, merged)

    pairs = effective_quote_results(merged)
    all_results = [qr for qr, _origin in pairs]
    observed_results = [qr for qr, origin in pairs if origin != "derived"]

    return CoverageReport(
        run_ids=merged.run_ids,
        registry_total_rows=len(base_registry),
        registry_distinct_sources=len(
            {r.distinct_rate_source_id for r in base_registry if r.distinct_rate_source_id}
        ),
        verified_applicable=sum(1 for r in snapshot if r.status != Status.UNRESOLVED),
        market_completion=metrics.market_completion(all_results, registry=snapshot),
        comparable_quote_yield=metrics.comparable_quote_yield(all_results, registry=snapshot),
        freshness=metrics.freshness(all_results, registry=snapshot),
        evidence_rate=metrics.evidence_rate(all_results, observed_results),
        duplicate_suppression=metrics.duplicate_suppression(all_results, registry=base_registry),
        notes=NOTES,
    )


def _pct(x: float | None) -> str:
    return "— (not computable)" if x is None else f"{x:.1%}"


def print_report(report: CoverageReport) -> None:
    print(f"runs merged: {', '.join(report.run_ids)}")
    print(
        f"registry: {report.registry_total_rows} rows -> "
        f"{report.registry_distinct_sources} distinct sources"
    )
    print(f"verified applicable (status != unresolved): {report.verified_applicable}")
    print()
    print(f"market_completion       = {_pct(report.market_completion)}")
    print(f"comparable_quote_yield  = {_pct(report.comparable_quote_yield)}")
    print(f"freshness               = {_pct(report.freshness)}")
    er = report.evidence_rate
    print(f"evidence_rate (all)      = {_pct(er.all_outcomes)}  [{er.all_count} outcomes]")
    print(f"evidence_rate (observed) = {_pct(er.observed_only)}  [{er.observed_count} outcomes]")
    ds = report.duplicate_suppression
    seeded = "—" if ds.registry_seeded is None else str(ds.registry_seeded)
    print(
        f"duplicate_suppression: registry_seeded={seeded} ({ds.registry_seeded_basis or 'n/a'}), "
        f"runtime_resolved={ds.runtime_resolved}"
    )
    print()
    for note in report.notes:
        print(f"NOTE: {note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m allquote.report")
    parser.add_argument("--json", action="store_true", help="print as JSON instead of text")
    args = parser.parse_args(argv)
    report = compute_report()
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
