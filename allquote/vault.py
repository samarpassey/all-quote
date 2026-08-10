"""Fernet-encrypted vault for sensitive IntakeProfile values. See PLAN.md Task 3.

Only this module ever holds real sensitive values; everywhere else sees
`allquote.schemas.VaultRef` tokens. Plaintext is returned only by `resolve()`,
at explicit call sites — never logged, never returned in bulk.

Key derivation note: the Fernet key is derived from `VAULT_KEY` via a single
SHA-256 pass (see `_fernet`), not a proper password-KDF (PBKDF2/scrypt). That's
an accepted tradeoff for a personal single-user hackathon vault — see
docs/GUARDRAILS.md known limitations.
"""

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet

from allquote.schemas import (
    IntakeAddress,
    IntakeContact,
    IntakeHistory,
    IntakeIdentity,
    IntakeLicence,
    IntakeVehicle,
    VaultRef,
    sensitive_fields,
)

VAULT_PATH = Path("data/vault.enc")
EVIDENCE_DIR = Path("data/evidence")
CONSENT_DIR = Path("data/consent")

_PLACEHOLDER_KEY = "change-me-long-random-passphrase"

_INTAKE_SUBMODELS_WITH_VAULT_REFS = [
    IntakeIdentity,
    IntakeContact,
    IntakeAddress,
    IntakeLicence,
    IntakeVehicle,
    IntakeHistory,
]

SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset().union(
    *(sensitive_fields(model) for model in _INTAKE_SUBMODELS_WITH_VAULT_REFS)
)


def _resolve_key(vault_key: str | None = None) -> str:
    key = vault_key if vault_key is not None else os.environ.get("VAULT_KEY")
    if not key or key == _PLACEHOLDER_KEY:
        raise RuntimeError(
            "VAULT_KEY is not set (or still the placeholder value) — set a real "
            "passphrase in .env before using the vault."
        )
    return key


def _fernet(vault_key: str | None = None) -> Fernet:
    key = _resolve_key(vault_key)
    derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
    return Fernet(derived)


def _load_store(vault_path: Path, vault_key: str | None) -> dict[str, dict[str, str]]:
    if not vault_path.exists():
        return {}
    raw = _fernet(vault_key).decrypt(vault_path.read_bytes())
    return json.loads(raw)


def _save_store(
    store: dict[str, dict[str, str]], vault_path: Path, vault_key: str | None
) -> None:
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(store).encode()
    vault_path.write_bytes(_fernet(vault_key).encrypt(payload))


def put(
    field_name: str,
    value: str,
    *,
    vault_path: Path = VAULT_PATH,
    vault_key: str | None = None,
) -> VaultRef:
    if field_name not in SENSITIVE_FIELD_NAMES:
        raise ValueError(
            f"{field_name!r} is not a recognized sensitive field "
            f"(see allquote.vault.SENSITIVE_FIELD_NAMES)"
        )
    token = VaultRef(f"vault:{field_name}:{uuid4().hex}")
    store = _load_store(vault_path, vault_key)
    store[token] = {"field_name": field_name, "value": value}
    _save_store(store, vault_path, vault_key)
    return token


def resolve(
    ref: VaultRef, *, vault_path: Path = VAULT_PATH, vault_key: str | None = None
) -> str:
    store = _load_store(vault_path, vault_key)
    entry = store.get(str(ref))
    if entry is None:
        raise KeyError(f"no vault entry for token {ref!r}")
    return entry["value"]


def status(
    *, vault_path: Path = VAULT_PATH, vault_key: str | None = None
) -> dict[str, bool]:
    store = _load_store(vault_path, vault_key)
    present = {entry["field_name"] for entry in store.values()}
    return {name: name in present for name in sorted(SENSITIVE_FIELD_NAMES)}


def delete_all(
    *,
    vault_path: Path = VAULT_PATH,
    evidence_dir: Path = EVIDENCE_DIR,
    consent_dir: Path = CONSENT_DIR,
) -> dict[str, int]:
    report = {"vault": 0, "evidence": 0, "consent": 0}

    if vault_path.exists():
        vault_path.unlink()
        report["vault"] = 1

    for key, directory in (("evidence", evidence_dir), ("consent", consent_dir)):
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file():
                path.unlink()
                report[key] += 1

    return report


def _cmd_put(args: argparse.Namespace) -> int:
    value = sys.stdin.readline().rstrip("\n")
    if not value:
        print("no value read from stdin", file=sys.stderr)
        return 1
    token = put(args.field, value)
    print(f"stored {args.field} -> {token}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    for field_name, is_set in status().items():
        print(f"{field_name}: {'set' if is_set else 'not set'}")
    return 0


def _cmd_delete_all(args: argparse.Namespace) -> int:
    if not args.confirm:
        print("refusing to delete without --confirm", file=sys.stderr)
        return 1
    report = delete_all()
    for category, count in report.items():
        print(f"removed {count} {category} file(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m allquote.vault")
    subparsers = parser.add_subparsers(dest="command", required=True)

    put_parser = subparsers.add_parser("put")
    put_parser.add_argument(
        "--field", required=True, help="sensitive field name, e.g. licence_number"
    )

    subparsers.add_parser("status")

    delete_parser = subparsers.add_parser("delete-all")
    delete_parser.add_argument("--confirm", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "put":
        return _cmd_put(args)
    elif args.command == "status":
        return _cmd_status(args)
    elif args.command == "delete-all":
        return _cmd_delete_all(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
