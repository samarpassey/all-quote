"""SQLite market registry. See PLAN.md Task 2 / docs/ARCHITECTURE.md.

Seeds from data/seed_registry.json into data/allquote.db (one JSON-payload row
per MarketRecord, keyed by registry_id), assigns a preliminary
distinct_rate_source_id by legal_underwriter alone. Task 8's normalizer
re-derives the authoritative (legal_underwriter, product_scope) key against
real QuoteResults per docs/ARCHITECTURE.md's dedupe model — this is a
registry-seed-time approximation, not the final word on dedupe.
Backs `make export-registry` / `make export`.
"""

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from allquote.schemas import MarketRecord, Status

DB_PATH = Path("data/allquote.db")
SEED_PATH = Path("data/seed_registry.json")
EXPORT_DIR = Path("exports")

_TABLE = "market_records"
_CSV_FIELDS = list(MarketRecord.model_fields.keys())


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_TABLE} "
        "(registry_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    return conn


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def assign_distinct_rate_source_ids(records: list[MarketRecord]) -> list[MarketRecord]:
    return [
        record.model_copy(update={"distinct_rate_source_id": _slugify(record.legal_underwriter)})
        for record in records
    ]


def load_seed(seed_path: Path = SEED_PATH, db_path: Path = DB_PATH) -> int:
    raw = json.loads(seed_path.read_text())
    records = assign_distinct_rate_source_ids(
        [MarketRecord.model_validate(row) for row in raw]
    )

    conn = _connect(db_path)
    try:
        inserted = 0
        for record in records:
            exists = conn.execute(
                f"SELECT 1 FROM {_TABLE} WHERE registry_id = ?", (record.registry_id,)
            ).fetchone()
            if exists is not None:
                continue
            fresh = record.model_copy(
                update={"status": Status.UNRESOLVED, "last_verified_at": None}
            )
            conn.execute(
                f"INSERT INTO {_TABLE} (registry_id, payload) VALUES (?, ?)",
                (fresh.registry_id, fresh.model_dump_json()),
            )
            inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def list_records(db_path: Path = DB_PATH) -> list[MarketRecord]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(f"SELECT payload FROM {_TABLE}").fetchall()
        return [MarketRecord.model_validate_json(payload) for (payload,) in rows]
    finally:
        conn.close()


@dataclass
class RegistryStats:
    total_rows: int
    by_status: dict[str, int]
    by_distribution_type: dict[str, int]
    distinct_rate_source_count: int


def stats(db_path: Path = DB_PATH) -> RegistryStats:
    records = list_records(db_path)
    distinct_ids = {r.distinct_rate_source_id for r in records if r.distinct_rate_source_id}
    return RegistryStats(
        total_rows=len(records),
        by_status=dict(Counter(r.status.value for r in records)),
        by_distribution_type=dict(Counter(r.distribution_type for r in records)),
        distinct_rate_source_count=len(distinct_ids),
    )


def _print_stats(s: RegistryStats) -> None:
    print(f"total_rows: {s.total_rows}")
    print(f"distinct_rate_source_count: {s.distinct_rate_source_count} (of {s.total_rows} rows)")
    print("by_status:")
    for status, count in sorted(s.by_status.items()):
        print(f"  {status}: {count}")
    print("by_distribution_type:")
    for dtype, count in sorted(s.by_distribution_type.items()):
        print(f"  {dtype}: {count}")


def export_csv(path: Path, db_path: Path = DB_PATH) -> int:
    records = list_records(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for record in records:
            row = record.model_dump(mode="json")
            row["requirements"] = ";".join(row["requirements"])
            writer.writerow(row)
    return len(records)


def export_json(path: Path, db_path: Path = DB_PATH) -> int:
    records = list_records(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([r.model_dump(mode="json") for r in records], indent=2))
    return len(records)


def export(
    with_report: bool = False, db_path: Path = DB_PATH, export_dir: Path = EXPORT_DIR
) -> None:
    csv_count = export_csv(export_dir / "registry.csv", db_path=db_path)
    json_count = export_json(export_dir / "registry.json", db_path=db_path)
    print(f"exported {csv_count} rows to {export_dir / 'registry.csv'}")
    print(f"exported {json_count} rows to {export_dir / 'registry.json'}")
    if with_report:
        print("run report skipped: Task 12 not implemented yet", file=sys.stderr)


def verify_many(
    registry_ids: list[str],
    source_url: str,
    verified_at: datetime | None = None,
    db_path: Path = DB_PATH,
) -> list[MarketRecord]:
    """Stamp last_verified_at (UTC now, unless given) + source_url on one or
    more registry rows in a single atomic call. Never touches status:
    verification means "this route exists and I checked it today," not
    "I got a quote." All-or-nothing — an unknown registry_id raises KeyError
    and no row is updated.
    """
    stamp = verified_at or datetime.now(timezone.utc)
    conn = _connect(db_path)
    try:
        payloads: dict[str, str] = {}
        missing: list[str] = []
        for registry_id in registry_ids:
            row = conn.execute(
                f"SELECT payload FROM {_TABLE} WHERE registry_id = ?", (registry_id,)
            ).fetchone()
            if row is None:
                missing.append(registry_id)
            else:
                payloads[registry_id] = row[0]
        if missing:
            raise KeyError(f"no registry row(s) with registry_id in {missing!r}")

        updated = []
        for registry_id in registry_ids:
            record = MarketRecord.model_validate_json(payloads[registry_id]).model_copy(
                update={"source_url": source_url, "last_verified_at": stamp}
            )
            conn.execute(
                f"UPDATE {_TABLE} SET payload = ? WHERE registry_id = ?",
                (record.model_dump_json(), registry_id),
            )
            updated.append(record)
        conn.commit()
        return updated
    finally:
        conn.close()


def verify(
    registry_id: str,
    source_url: str,
    verified_at: datetime | None = None,
    db_path: Path = DB_PATH,
) -> MarketRecord:
    return verify_many([registry_id], source_url, verified_at=verified_at, db_path=db_path)[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m allquote.registry")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("load")
    subparsers.add_parser("stats")
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--with-report", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument(
        "--registry-id", required=True, nargs="+", help="one or more registry_id values"
    )
    verify_parser.add_argument("--source-url", required=True)

    args = parser.parse_args(argv)
    if args.command == "load":
        print(f"loaded {load_seed()} new rows")
    elif args.command == "stats":
        _print_stats(stats())
    elif args.command == "export":
        export(with_report=args.with_report)
    elif args.command == "verify":
        updated = verify_many(args.registry_id, args.source_url)
        for record in updated:
            print(record.model_dump_json(indent=2))
        print(
            f"verified {len(updated)} route(s) at "
            f"{updated[0].last_verified_at.isoformat()} (status unchanged)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
