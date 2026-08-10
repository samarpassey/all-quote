import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from allquote import registry
from allquote.schemas import Status
from tests.fixtures import build_market_record

FAKE_ROWS = [
    build_market_record(
        registry_id="direct-testco",
        legal_underwriter="Testco Insurance Company",
        brand_or_program="TestCo Direct",
        distribution_type="direct",
    ),
    build_market_record(
        registry_id="broker-testco",
        legal_underwriter="Testco Insurance Company",
        brand_or_program="TestCo Broker Program",
        distribution_type="broker",
    ),
    build_market_record(
        registry_id="agg-panel",
        legal_underwriter="Other Mutual Co.",
        brand_or_program="FakeAggregator Panel",
        distribution_type="aggregator",
    ),
]


def _write_seed(tmp_path: Path) -> Path:
    seed_path = tmp_path / "seed_registry.json"
    seed_path.write_text(json.dumps([r.model_dump(mode="json") for r in FAKE_ROWS]))
    return seed_path


def test_assign_distinct_rate_source_ids_collapses_shared_underwriter():
    updated = registry.assign_distinct_rate_source_ids(FAKE_ROWS)
    ids = {r.registry_id: r.distinct_rate_source_id for r in updated}
    assert ids["direct-testco"] == ids["broker-testco"]
    assert ids["agg-panel"] != ids["direct-testco"]


def test_load_seed_inserts_all_rows_as_unresolved(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"

    assert registry.load_seed(seed_path=seed_path, db_path=db_path) == 3

    records = registry.list_records(db_path=db_path)
    assert len(records) == 3
    assert all(r.status == Status.UNRESOLVED for r in records)
    assert all(r.last_verified_at is None for r in records)
    assert all(r.distinct_rate_source_id for r in records)


def test_load_seed_is_idempotent_and_does_not_clobber_verified_rows(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"
    registry.load_seed(seed_path=seed_path, db_path=db_path)

    registry.verify("direct-testco", "https://example.invalid/verified", db_path=db_path)

    assert registry.load_seed(seed_path=seed_path, db_path=db_path) == 0

    records = {r.registry_id: r for r in registry.list_records(db_path=db_path)}
    assert records["direct-testco"].last_verified_at is not None
    assert records["direct-testco"].source_url == "https://example.invalid/verified"


def test_stats_counts_status_distribution_and_distinct_sources(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"
    registry.load_seed(seed_path=seed_path, db_path=db_path)

    s = registry.stats(db_path=db_path)
    assert s.total_rows == 3
    assert s.by_status == {"unresolved": 3}
    assert s.by_distribution_type == {"direct": 1, "broker": 1, "aggregator": 1}
    assert s.distinct_rate_source_count == 2


def test_export_csv_and_json(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"
    registry.load_seed(seed_path=seed_path, db_path=db_path)

    export_dir = tmp_path / "exports"
    registry.export(db_path=db_path, export_dir=export_dir)

    csv_path = export_dir / "registry.csv"
    json_path = export_dir / "registry.json"
    assert csv_path.exists()
    assert json_path.exists()

    exported = json.loads(json_path.read_text())
    assert {row["registry_id"] for row in exported} == {r.registry_id for r in FAKE_ROWS}

    header = csv_path.read_text().splitlines()[0]
    assert "registry_id" in header
    assert "distinct_rate_source_id" in header


def test_verify_stamps_last_verified_at_and_source_url(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"
    registry.load_seed(seed_path=seed_path, db_path=db_path)

    fixed_time = datetime(2026, 8, 10, tzinfo=timezone.utc)
    updated = registry.verify(
        "direct-testco",
        "https://example.invalid/verified",
        verified_at=fixed_time,
        db_path=db_path,
    )
    assert updated.source_url == "https://example.invalid/verified"
    assert updated.last_verified_at == fixed_time


def test_verify_unknown_registry_id_raises(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"
    registry.load_seed(seed_path=seed_path, db_path=db_path)

    with pytest.raises(KeyError):
        registry.verify("does-not-exist", "https://example.invalid", db_path=db_path)


def test_verify_does_not_change_status(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"
    registry.load_seed(seed_path=seed_path, db_path=db_path)

    updated = registry.verify(
        "direct-testco", "https://example.invalid/verified", db_path=db_path
    )
    assert updated.status == Status.UNRESOLVED


def test_verify_many_stamps_all_given_ids(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"
    registry.load_seed(seed_path=seed_path, db_path=db_path)

    fixed_time = datetime(2026, 8, 10, tzinfo=timezone.utc)
    updated = registry.verify_many(
        ["direct-testco", "broker-testco", "agg-panel"],
        "https://example.invalid/verified",
        verified_at=fixed_time,
        db_path=db_path,
    )

    assert [r.registry_id for r in updated] == ["direct-testco", "broker-testco", "agg-panel"]
    assert all(r.source_url == "https://example.invalid/verified" for r in updated)
    assert all(r.last_verified_at == fixed_time for r in updated)
    assert all(r.status == Status.UNRESOLVED for r in updated)

    records = {r.registry_id: r for r in registry.list_records(db_path=db_path)}
    assert records["direct-testco"].last_verified_at == fixed_time
    assert records["broker-testco"].last_verified_at == fixed_time
    assert records["agg-panel"].last_verified_at == fixed_time


def test_verify_many_is_atomic_on_unknown_id(tmp_path):
    seed_path = _write_seed(tmp_path)
    db_path = tmp_path / "allquote.db"
    registry.load_seed(seed_path=seed_path, db_path=db_path)

    with pytest.raises(KeyError):
        registry.verify_many(
            ["direct-testco", "does-not-exist"],
            "https://example.invalid/verified",
            db_path=db_path,
        )

    # direct-testco must NOT have been stamped: an unknown id anywhere in the
    # batch aborts the whole call, never a partial write.
    records = {r.registry_id: r for r in registry.list_records(db_path=db_path)}
    assert records["direct-testco"].last_verified_at is None
