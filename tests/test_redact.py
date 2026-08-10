from datetime import datetime, timezone

import pytest
from PIL import Image

from allquote import redact
from tests.fixtures import build_vaulted_profile


@pytest.fixture
def vaulted_profile(tmp_path):
    vault_path = tmp_path / "vault.enc"
    key = "test-key-not-real-redact-0001"
    profile, plaintext = build_vaulted_profile(vault_path, key)
    return profile, plaintext, vault_path, key


def test_redact_text_catches_postal_code_with_and_without_space(vaulted_profile):
    profile, _, vault_path, key = vaulted_profile
    for postal in ("K1A 0B1", "K1A0B1"):
        text = f"applicant postal code: {postal}"
        redacted = redact.redact_text(text, profile, vault_path=vault_path, vault_key=key)
        assert postal not in redacted
        assert "[REDACTED:postal_code]" in redacted


def test_redact_text_catches_phone_with_dashes_brackets_spaces(vaulted_profile):
    profile, _, vault_path, key = vaulted_profile
    for phone in ("416-555-0199", "(416) 555-0199", "416 555 0199", "4165550199"):
        text = f"callback number: {phone}"
        redacted = redact.redact_text(text, profile, vault_path=vault_path, vault_key=key)
        assert phone not in redacted
        assert "[REDACTED:phone]" in redacted


def test_redact_text_catches_licence_with_and_without_hyphens(vaulted_profile):
    profile, _, vault_path, key = vaulted_profile
    # Deliberately different from the profile's own stored licence value — proves
    # this is shape-based, not just literal substitution of a known value.
    for licence in ("S1234-56789-01234", "S12345678901234"):
        text = f"licence: {licence}"
        redacted = redact.redact_text(text, profile, vault_path=vault_path, vault_key=key)
        assert licence not in redacted
        assert "[REDACTED:licence_number]" in redacted


def test_redact_text_catches_dob_in_common_orderings(vaulted_profile):
    profile, _, vault_path, key = vaulted_profile
    for dob in ("1990-05-15", "15-05-1990", "05/15/1990", "1990/05/15"):
        text = f"date of birth: {dob}"
        redacted = redact.redact_text(text, profile, vault_path=vault_path, vault_key=key)
        assert dob not in redacted
        assert "[REDACTED:date_of_birth]" in redacted


def test_redact_text_resolves_and_strips_free_text_profile_values(vaulted_profile):
    profile, plaintext, vault_path, key = vaulted_profile
    text = (
        f"Applicant name: {plaintext['legal_name']}. "
        f"Email on file: {plaintext['email']}. "
        f"Street: {plaintext['street']}."
    )

    redacted = redact.redact_text(text, profile, vault_path=vault_path, vault_key=key)

    assert plaintext["legal_name"] not in redacted
    assert plaintext["email"] not in redacted
    assert plaintext["street"] not in redacted
    assert "[REDACTED:legal_name]" in redacted
    assert "[REDACTED:email]" in redacted
    assert "[REDACTED:street]" in redacted


def test_redact_image_blackens_only_given_box(tmp_path):
    src = tmp_path / "source.png"
    Image.new("RGB", (100, 100), color=(255, 255, 255)).save(src)

    dest = tmp_path / "redacted.png"
    box = (10, 10, 40, 40)
    redact.redact_image(src, [box], output_path=dest)

    out = Image.open(dest)
    assert out.getpixel((20, 20)) == (0, 0, 0)
    assert out.getpixel((5, 5)) == (255, 255, 255)
    assert out.getpixel((60, 60)) == (255, 255, 255)


def test_safe_write_evidence_raises_without_profile_for_text(tmp_path):
    dest = tmp_path / "out.txt"
    with pytest.raises(redact.RedactionNotAppliedError):
        redact.safe_write_evidence("some text", "text", dest)
    assert not dest.exists()


def test_safe_write_evidence_raises_without_boxes_for_image(tmp_path):
    src = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(src)
    dest = tmp_path / "out.png"
    with pytest.raises(redact.RedactionNotAppliedError):
        redact.safe_write_evidence(src, "image", dest)
    assert not dest.exists()


def test_safe_write_evidence_writes_redacted_text(vaulted_profile):
    profile, plaintext, vault_path, key = vaulted_profile
    dest = vault_path.parent / "evidence.txt"
    payload = f"licence on file: {plaintext['licence_number']}"

    redact.safe_write_evidence(
        payload, "text", dest, profile=profile, vault_path=vault_path, vault_key=key
    )

    written = dest.read_text()
    assert plaintext["licence_number"] not in written
    assert "[REDACTED:" in written


def test_write_consent_receipt_stores_field_names_only(tmp_path):
    consent_dir = tmp_path / "consent"

    receipt_id = redact.write_consent_receipt(
        "route-0001",
        ["make", "model", "model_year"],
        datetime(2026, 8, 9, tzinfo=timezone.utc),
        consent_dir=consent_dir,
    )

    files = list(consent_dir.glob("*.json"))
    assert len(files) == 1
    assert receipt_id in files[0].name
    assert "make" in files[0].read_text()


def test_write_consent_receipt_rejects_value_shaped_entries(tmp_path):
    consent_dir = tmp_path / "consent"
    with pytest.raises(ValueError):
        redact.write_consent_receipt(
            "route-0001",
            ["K1A 0B1"],
            datetime(2026, 8, 9, tzinfo=timezone.utc),
            consent_dir=consent_dir,
        )
