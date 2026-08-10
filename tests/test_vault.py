import base64
import hashlib
import io
import json

import pytest
from cryptography.fernet import Fernet, InvalidToken

from allquote import vault
from tests.fixtures import build_vaulted_profile


def _contains_value(obj, value: str) -> bool:
    if isinstance(obj, dict):
        return any(_contains_value(v, value) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_value(v, value) for v in obj)
    return obj == value


def test_round_trip_and_zero_plaintext_on_disk(tmp_path):
    vault_path = tmp_path / "vault.enc"
    key = "test-key-not-real-0001"
    secret = "FAKE-LICENCE-VALUE-0001"

    ref = vault.put("licence_number", secret, vault_path=vault_path, vault_key=key)
    assert vault.resolve(ref, vault_path=vault_path, vault_key=key) == secret

    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes()


def test_profile_serialization_never_leaks_plaintext(tmp_path):
    vault_path = tmp_path / "vault.enc"
    key = "test-key-not-real-0002"
    profile, plaintext = build_vaulted_profile(vault_path, key)

    dumped = profile.model_dump()
    dumped_json = profile.model_dump_json()

    for field_name, value in plaintext.items():
        assert value not in dumped_json, f"{field_name} plaintext leaked into model_dump_json()"
        assert not _contains_value(dumped, value), f"{field_name} plaintext leaked into model_dump()"


def test_missing_vault_key_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.delenv("VAULT_KEY", raising=False)
    with pytest.raises(RuntimeError):
        vault.put("licence_number", "FAKE-VALUE", vault_path=tmp_path / "vault.enc")


def test_placeholder_vault_key_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_KEY", "change-me-long-random-passphrase")
    with pytest.raises(RuntimeError):
        vault.put("licence_number", "FAKE-VALUE", vault_path=tmp_path / "vault.enc")


def test_put_rejects_unknown_field_name(tmp_path):
    with pytest.raises(ValueError):
        vault.put(
            "not_a_real_field", "value", vault_path=tmp_path / "vault.enc", vault_key="k"
        )


def test_resolve_unknown_token_raises_key_error(tmp_path):
    vault_path = tmp_path / "vault.enc"
    vault.put("licence_number", "FAKE-VALUE", vault_path=vault_path, vault_key="k")
    with pytest.raises(KeyError):
        vault.resolve("vault:licence_number:does-not-exist", vault_path=vault_path, vault_key="k")


def test_sensitive_field_names_includes_list_typed_history_fields():
    for name in ("accidents", "convictions", "suspensions", "cancellations"):
        assert name in vault.SENSITIVE_FIELD_NAMES


def test_put_accepts_list_typed_sensitive_field(tmp_path):
    vault_path = tmp_path / "vault.enc"
    key = "test-key-not-real-0003"
    note = "Fake accident note, not at fault"

    ref = vault.put("accidents", note, vault_path=vault_path, vault_key=key)

    assert vault.resolve(ref, vault_path=vault_path, vault_key=key) == note


def test_vault_file_is_actually_encrypted_not_just_plaintext_free(tmp_path):
    vault_path = tmp_path / "vault.enc"
    key = "test-key-not-real-0004"
    vault.put("licence_number", "FAKE-LICENCE-VALUE", vault_path=vault_path, vault_key=key)

    raw = vault_path.read_bytes()

    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)

    derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
    decrypted = Fernet(derived).decrypt(raw)
    store = json.loads(decrypted)
    assert any(entry["field_name"] == "licence_number" for entry in store.values())
    assert any(entry["value"] == "FAKE-LICENCE-VALUE" for entry in store.values())


def test_resolve_with_wrong_key_raises_not_silently_empty(tmp_path):
    vault_path = tmp_path / "vault.enc"
    ref = vault.put(
        "licence_number", "FAKE-LICENCE-VALUE", vault_path=vault_path, vault_key="key-a-not-real"
    )
    with pytest.raises(InvalidToken):
        vault.resolve(ref, vault_path=vault_path, vault_key="key-b-not-real")


def test_status_reports_field_names_without_values(tmp_path):
    vault_path = tmp_path / "vault.enc"
    key = "test-key-not-real-0005"
    vault.put("licence_number", "FAKE-VALUE-0005", vault_path=vault_path, vault_key=key)

    s = vault.status(vault_path=vault_path, vault_key=key)

    assert s["licence_number"] is True
    assert s["email"] is False
    assert "FAKE-VALUE-0005" not in json.dumps(s)


def test_delete_all_removes_vault_evidence_and_consent(tmp_path):
    vault_path = tmp_path / "vault.enc"
    evidence_dir = tmp_path / "evidence"
    consent_dir = tmp_path / "consent"
    key = "test-key-not-real-0006"

    vault.put("licence_number", "FAKE-VALUE-0006", vault_path=vault_path, vault_key=key)
    evidence_dir.mkdir()
    (evidence_dir / "artifact1.png").write_bytes(b"fake-image-bytes")
    consent_dir.mkdir()
    (consent_dir / "receipt1.json").write_text("{}")

    report = vault.delete_all(
        vault_path=vault_path, evidence_dir=evidence_dir, consent_dir=consent_dir
    )

    assert report == {"vault": 1, "evidence": 1, "consent": 1}
    assert not vault_path.exists()
    assert list(evidence_dir.rglob("*")) == []
    assert list(consent_dir.rglob("*")) == []


def test_cli_put_accepts_list_typed_field_via_stdin(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VAULT_KEY", "test-only-fake-cli-key-not-real")
    monkeypatch.setattr("sys.stdin", io.StringIO("Fake accident note for CLI test\n"))

    rc = vault.main(["put", "--field", "accidents"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "accidents ->" in out
    assert "Fake accident note for CLI test" not in out
    assert (tmp_path / "data" / "vault.enc").exists()


def test_cli_delete_all_requires_confirm_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VAULT_KEY", "test-only-fake-cli-key-not-real-2")
    monkeypatch.setattr("sys.stdin", io.StringIO("Fake value\n"))
    vault.main(["put", "--field", "licence_number"])

    rc = vault.main(["delete-all"])
    assert rc == 1
    assert (tmp_path / "data" / "vault.enc").exists()

    rc = vault.main(["delete-all", "--confirm"])
    assert rc == 0
    assert not (tmp_path / "data" / "vault.enc").exists()
