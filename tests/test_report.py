import json
from datetime import datetime, timezone

from allquote import registry, report, results_store
from allquote.planner import PlannedRoute
from allquote.schemas import QuoteOutcome, QuoteResult, QuoteSource, Status
from tests.fixtures import build_market_record, build_normalized_quote, build_quote_result


def _qr(status: Status, registry_id: str, distinct_id: str) -> QuoteResult:
    return build_quote_result(
        source=QuoteSource(
            registry_id=registry_id,
            brand_or_program="X",
            legal_underwriter="X",
            insurer_group="X",
            licensed_intermediary=None,
            distinct_rate_source_id=distinct_id,
        ),
        outcome=QuoteOutcome(
            status=status,
            is_exact_quote=status in (Status.QUOTED_COMPARABLE, Status.QUOTED_NON_COMPARABLE),
            failure_reason=None,
            next_action=None,
        ),
    )


def _seed_registry(db_path) -> None:
    rows = [
        build_market_record(
            registry_id="route-a", legal_underwriter="Alpha Co",
            insurer_group="Alpha Group", brand_or_program="Alpha Direct",
        ),
        build_market_record(
            registry_id="seed-a", legal_underwriter="Alpha Co",  # non-primary duplicate
            insurer_group="Alpha Group", brand_or_program="Alpha Seed",
        ),
        build_market_record(
            registry_id="route-b", legal_underwriter="Beta Co",
            insurer_group="Beta Group", brand_or_program="Beta Direct",
        ),
        build_market_record(
            registry_id="route-c", legal_underwriter="Gamma Co",  # never gets a result
            insurer_group="Gamma Group", brand_or_program="Gamma Direct",
        ),
    ]
    seed_path = db_path.parent / "seed.json"
    seed_path.write_text(json.dumps([r.model_dump(mode="json") for r in rows]))
    registry.load_seed(seed_path=seed_path, db_path=db_path)


def _seed_two_runs(runs_root) -> tuple[str, str]:
    run_1, run_2 = "20260101T000000Z-aaaaaa", "20260102T000000Z-bbbbbb"
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    results_store.save_manifest(
        run_1,
        [
            PlannedRoute("alpha-co", "route-a", ("seed-a",), "contact", 1, "cheap"),
            PlannedRoute("beta-co", "route-b", (), "derived", None, "none"),
            PlannedRoute("gamma-co", "route-c", (), "contact", 3, "cheap"),
        ],
        started_at=started,
        runs_root=runs_root,
    )
    results_store.save_result(
        run_1, "alpha-co", 1,
        quote_result=_qr(Status.BLOCKED, "route-a", "alpha-co"),
        normalized_quote=build_normalized_quote(), origin="executed", runs_root=runs_root,
    )
    results_store.save_result(
        run_1, "beta-co", 1,
        quote_result=_qr(Status.QUOTED_COMPARABLE, "route-b", "beta-co"),
        normalized_quote=build_normalized_quote(), origin="derived", runs_root=runs_root,
    )
    results_store.mark_not_attempted(run_1, "gamma-co", "budget exhausted", runs_root=runs_root)

    # run_2 is a 1-route re-run that supersedes alpha-co's outcome from run_1.
    results_store.save_manifest(
        run_2,
        [PlannedRoute("alpha-co", "route-a", (), "contact", 1, "smart")],
        started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        runs_root=runs_root,
    )
    results_store.save_result(
        run_2, "alpha-co", 1,
        quote_result=_qr(Status.UNREACHABLE, "route-a", "alpha-co"),
        normalized_quote=build_normalized_quote(), origin="executed", runs_root=runs_root,
    )
    return run_1, run_2


def test_merge_runs_supersedes_overlapping_distinct_source(tmp_path):
    run_1, run_2 = _seed_two_runs(tmp_path / "runs")
    merged = report.merge_runs(runs_root=tmp_path / "runs")

    assert merged.run_ids == (run_1, run_2)
    # run_2 overwrote alpha-co's result from run_1.
    assert merged.payloads["alpha-co"]["quote_result"]["outcome"]["status"] == "unreachable"
    # beta-co was only ever in run_1 and survives untouched.
    assert merged.payloads["beta-co"]["quote_result"]["outcome"]["status"] == "quoted_comparable"
    # gamma-co's not_attempted marker carries no quote_result.
    assert "quote_result" not in merged.payloads["gamma-co"]


def test_not_attempted_never_overwrites_an_earlier_real_result(tmp_path):
    # A later run that ran out of budget before reaching a route must not
    # erase a real result an earlier run already produced for it.
    runs_root = tmp_path / "runs"
    run_1, run_2 = "20260101T000000Z-aaaaaa", "20260103T000000Z-cccccc"

    results_store.save_manifest(
        run_1,
        [PlannedRoute("alpha-co", "route-a", (), "contact", 1, "cheap")],
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        runs_root=runs_root,
    )
    results_store.save_result(
        run_1, "alpha-co", 1,
        quote_result=_qr(Status.MANUAL_HANDOFF, "route-a", "alpha-co"),
        normalized_quote=build_normalized_quote(), origin="executed", runs_root=runs_root,
    )

    results_store.save_manifest(
        run_2,
        [PlannedRoute("alpha-co", "route-a", (), "contact", 1, "cheap")],
        started_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        runs_root=runs_root,
    )
    results_store.mark_not_attempted(run_2, "alpha-co", "batch wall-clock budget exhausted", runs_root=runs_root)

    merged = report.merge_runs(runs_root=runs_root)
    assert "quote_result" in merged.payloads["alpha-co"]
    assert merged.payloads["alpha-co"]["quote_result"]["outcome"]["status"] == "manual_handoff"
    assert report.not_attempted_distinct_ids(merged) == []


def test_not_attempted_fills_a_gap_when_nothing_earlier_exists(tmp_path):
    runs_root = tmp_path / "runs"
    run_1 = "20260101T000000Z-aaaaaa"
    results_store.save_manifest(
        run_1,
        [PlannedRoute("alpha-co", "route-a", (), "contact", 1, "cheap")],
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        runs_root=runs_root,
    )
    results_store.mark_not_attempted(run_1, "alpha-co", "batch wall-clock budget exhausted", runs_root=runs_root)

    merged = report.merge_runs(runs_root=runs_root)
    assert "quote_result" not in merged.payloads["alpha-co"]
    assert report.not_attempted_distinct_ids(merged) == ["alpha-co"]


def test_merge_runs_collects_notes_across_manifests_in_order(tmp_path):
    runs_root = tmp_path / "runs"
    results_store.save_manifest(
        "20260101T000000Z-aaaaaa", [],
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc), runs_root=runs_root,
        notes=["first note"],
    )
    results_store.save_manifest(
        "20260102T000000Z-bbbbbb", [],
        started_at=datetime(2026, 1, 2, tzinfo=timezone.utc), runs_root=runs_root,
        notes=["second note", "third note"],
    )
    merged = report.merge_runs(runs_root=runs_root)
    assert merged.notes == ("first note", "second note", "third note")


def test_build_registry_snapshot_only_touches_primary_rows_never_last_verified_at(tmp_path):
    db_path = tmp_path / "allquote.db"
    _seed_registry(db_path)
    _seed_two_runs(tmp_path / "runs")

    base = registry.list_records(db_path=db_path)
    merged = report.merge_runs(runs_root=tmp_path / "runs")
    snapshot = report.build_registry_snapshot(base, merged)
    by_id = {r.registry_id: r for r in snapshot}

    assert by_id["route-a"].status == Status.UNREACHABLE  # overridden from run_2
    assert by_id["route-b"].status == Status.QUOTED_COMPARABLE  # overridden from run_1
    assert by_id["seed-a"].status == Status.UNRESOLVED  # non-primary duplicate: untouched
    assert by_id["route-c"].status == Status.UNRESOLVED  # not_attempted: untouched
    # last_verified_at is never synthesized from a run timestamp.
    assert all(r.last_verified_at is None for r in snapshot)


def test_compute_report_end_to_end(tmp_path):
    db_path = tmp_path / "allquote.db"
    _seed_registry(db_path)
    _seed_two_runs(tmp_path / "runs")

    r = report.compute_report(db_path=db_path, runs_root=tmp_path / "runs")

    assert r.registry_total_rows == 4
    assert r.registry_distinct_sources == 3  # alpha-co, beta-co, gamma-co
    assert r.verified_applicable == 2  # alpha-co (unreachable), beta-co (quoted_comparable)

    # market_completion: both verified-applicable rows have evidence-backed
    # terminal status -> 2/2.
    assert r.market_completion == 1.0
    # comparable_quote_yield: only beta-co is quoted_comparable -> 1/2.
    assert r.comparable_quote_yield == 0.5
    # freshness: denominator is non-zero (2) but nothing was ever stamped by
    # registry.verify() -> a real, honest 0.0, distinct from None.
    assert r.freshness == 0.0
    assert r.freshness is not None

    assert r.evidence_rate.all_count == 2
    assert r.evidence_rate.all_outcomes == 1.0
    assert r.evidence_rate.observed_count == 1  # only alpha-co's origin != "derived"
    assert r.evidence_rate.observed_only == 1.0

    assert r.duplicate_suppression.registry_seeded == 1  # 4 rows -> 3 distinct sources
    assert r.duplicate_suppression.runtime_resolved == 0


def test_compute_report_zero_denominator_is_none_not_zero(tmp_path):
    db_path = tmp_path / "allquote.db"
    _seed_registry(db_path)
    # no runs at all: every registry row stays unresolved.

    r = report.compute_report(db_path=db_path, runs_root=tmp_path / "runs")

    assert r.verified_applicable == 0
    assert r.market_completion is None
    assert r.comparable_quote_yield is None
    assert r.freshness is None
    assert r.evidence_rate.all_outcomes is None
    assert r.evidence_rate.observed_only is None
    # duplicate_suppression.registry_seeded is a pure registry-shape fact,
    # independent of run history, so it is still a real number here.
    assert r.duplicate_suppression.registry_seeded == 1
