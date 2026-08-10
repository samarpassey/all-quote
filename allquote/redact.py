"""Text and image redaction. See PLAN.md Task 3.

This is the only module allowed to write redacted evidence content to disk
(`safe_write_evidence`) — Task 4's `evidence.py` will enforce that it's the only
caller, but within this module's own scope there is no other public write path.

Shape-based redaction (licence/VIN/postal/phone/DOB patterns) is regex-based and
can over-redact benign look-alike strings — accepted tradeoff, never the reverse.
See docs/GUARDRAILS.md known limitations.
"""

import json
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from PIL import Image, ImageDraw

from allquote import vault
from allquote.schemas import IntakeProfile, VaultRef, sensitive_fields

# --- shape-based patterns (independent of any profile) -------------------------

_SHAPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "postal_code": re.compile(r"\b[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d\b"),
    "phone": re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    "licence_number": re.compile(r"\b[A-Za-z]\d{4}-?\d{5}-?\d{5}\b"),
    "vin": re.compile(r"\b[A-HJ-NPR-Za-hj-npr-z0-9]{17}\b"),
    "date_of_birth": re.compile(
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b"
    ),
}


def _apply_shape_patterns(text: str) -> str:
    redacted = text
    for label, pattern in _SHAPE_PATTERNS.items():
        redacted = pattern.sub(f"[REDACTED:{label}]", redacted)
    return redacted


def _looks_like_value(s: str) -> bool:
    return any(pattern.search(s) for pattern in _SHAPE_PATTERNS.values())


# --- profile-driven redaction ----------------------------------------------------

_PROFILE_GROUPS = ("identity", "contact", "address", "licence", "vehicle", "history")


def _iter_profile_refs(profile: IntakeProfile) -> Iterator[tuple[str, VaultRef]]:
    for group_name in _PROFILE_GROUPS:
        group = getattr(profile, group_name)
        if group is None:
            continue
        for field_name in sensitive_fields(type(group)):
            value = getattr(group, field_name)
            if value is None:
                continue
            if isinstance(value, list):
                for item in value:
                    yield field_name, item
            else:
                yield field_name, value


def _replace_literal(text: str, value: str, field_name: str) -> str:
    if not value:
        return text
    return re.sub(re.escape(value), f"[REDACTED:{field_name}]", text, flags=re.IGNORECASE)


def redact_text(
    text: str,
    profile: IntakeProfile,
    *,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
) -> str:
    redacted = _apply_shape_patterns(text)
    for field_name, ref in _iter_profile_refs(profile):
        value = vault.resolve(ref, vault_path=vault_path, vault_key=vault_key)
        redacted = _replace_literal(redacted, value, field_name)
    return redacted


# --- image redaction --------------------------------------------------------------


def redact_image(
    image_path: Path,
    boxes: list[tuple[int, int, int, int]],
    *,
    output_path: Path,
) -> Path:
    """Black-fill explicit (left, top, right, bottom) boxes. No OCR, no
    auto-detection — boxes are the caller's responsibility.
    """
    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    for box in boxes:
        draw.rectangle(box, fill="black")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    return output_path


# --- single public save path -----------------------------------------------------


class RedactionNotAppliedError(RuntimeError):
    """Raised when safe_write_evidence is called without the inputs needed to
    actually redact — never write unredacted content as a fallback."""


def safe_write_evidence(
    payload: str | Path,
    kind: Literal["text", "image"],
    destination: Path,
    *,
    profile: IntakeProfile | None = None,
    boxes: list[tuple[int, int, int, int]] | None = None,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
) -> Path:
    if kind == "text":
        if profile is None:
            raise RedactionNotAppliedError(
                "kind='text' requires profile to redact against"
            )
        redacted = redact_text(payload, profile, vault_path=vault_path, vault_key=vault_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(redacted)
    elif kind == "image":
        if boxes is None:
            raise RedactionNotAppliedError(
                "kind='image' requires boxes (pass [] explicitly if none apply)"
            )
        redact_image(payload, boxes, output_path=destination)
    else:
        raise ValueError(f"unknown kind {kind!r}")
    return destination


# --- consent + retention ----------------------------------------------------------


def write_consent_receipt(
    route_registry_id: str,
    fields_disclosed: list[str],
    timestamp: datetime,
    *,
    consent_dir: Path = vault.CONSENT_DIR,
) -> str:
    for entry in fields_disclosed:
        if _looks_like_value(entry):
            raise ValueError(
                f"fields_disclosed must contain field NAMES only, not values: "
                f"{entry!r} looks like an actual value"
            )

    receipt_id = uuid4().hex
    record = {
        "consent_receipt_id": receipt_id,
        "registry_id": route_registry_id,
        "fields_disclosed": list(fields_disclosed),
        "timestamp": timestamp.isoformat(),
    }
    consent_dir.mkdir(parents=True, exist_ok=True)
    (consent_dir / f"{receipt_id}.json").write_text(json.dumps(record, indent=2))
    return receipt_id
