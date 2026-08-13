"""Intake form surface + local server. See docs/DESIGN.md §1 (the "form"
surface) and docs/ARCHITECTURE.md data-flow rule 1 ("IntakeProfile is
collected once and stored WITHOUT sensitive fields; those go to the vault.
Profile carries vault references, not values.").

`generate()` writes `exports/intake.html`: a single-column form, sections
01-09 numbered in the left margin (one per IntakeProfile group, in schema
order), the five required groups open and the four optional groups behind
text toggles. It cannot submit itself over `file://` — `vault.put()` is a
live Python call — so `serve()` hosts that same file locally and answers
`POST /submit`.

`POST /submit` is the only place a raw sensitive value ever exists as text in
this process. It arrives in the request body, is handed straight to
`vault.put()` per field, and the local variables holding it are dropped
immediately after. Nothing here ever assigns it to a name that outlives that
call, prints it, or lets an exception message echo it back — see
`_IntakeHandler.log_message`/`log_error` and the generic error strings in
`do_POST`, and `tests/test_intake.py::test_server_never_logs_request_body`.
"""

import argparse
import json
import sys
import webbrowser
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin

from dotenv import load_dotenv
from pydantic import ValidationError

from allquote import redact, vault
from allquote.schemas import (
    CoverageBenchmark,
    IntakeAddress,
    IntakeConsent,
    IntakeContact,
    IntakeHistory,
    IntakeIdentity,
    IntakeLicence,
    IntakeProfile,
    IntakeUse,
    IntakeVehicle,
    sensitive_fields,
)

EXPORT_DIR = Path("exports")
OUTPUT_PATH = EXPORT_DIR / "intake.html"
PROFILE_PATH = Path("data/profile.json")
CONSENT_RECEIPT_ROUTE_ID = "intake"

# --- field spec: introspected from schemas.py, the single source of truth ------

_GROUP_DEFS: list[tuple[str, str, str, type, bool]] = [
    ("01", "identity", "Identity", IntakeIdentity, True),
    ("02", "licence", "Licence", IntakeLicence, True),
    ("03", "vehicle", "Vehicle", IntakeVehicle, True),
    ("04", "address", "Address", IntakeAddress, True),
    ("05", "coverage_benchmark", "Coverage benchmark", CoverageBenchmark, True),
    ("06", "consent", "Consent", IntakeConsent, False),
    ("07", "contact", "Contact", IntakeContact, False),
    ("08", "use", "Vehicle use", IntakeUse, False),
    ("09", "history", "Insurance history", IntakeHistory, False),
]

_ACRONYMS = {"vin", "dob", "g1", "g2", "fsa", "opcf", "ab", "km", "dcpd"}


def _humanize(key: str) -> str:
    words = [w.upper() if w.lower() in _ACRONYMS else w.lower() for w in key.split("_")]
    label = " ".join(words)
    return label[:1].upper() + label[1:] if label else label


def _unwrap_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (UnionType, Union):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _field_kind(annotation: Any) -> tuple[str, list[Any] | None]:
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is list:
        inner = _unwrap_optional(args[0]) if args else str
        if get_origin(inner) is Literal:
            return "checkbox-list", list(get_args(inner))
        return "list-text", None
    if origin is dict:
        value_type = _unwrap_optional(args[1]) if len(args) > 1 else None
        if get_origin(value_type) is Literal:
            return "keyvalue", list(get_args(value_type))
        return "keyvalue", None
    if origin is Literal:
        return "select", list(args)
    if annotation is bool:
        return "checkbox", None
    if annotation in (int, float):
        return "number", None
    if annotation is date:
        return "date", None
    if annotation is datetime:
        return "datetime", None
    return "text", None


def _numeric_bounds(info: Any) -> tuple[float | None, float | None]:
    lo = hi = None
    for constraint in info.metadata:
        if hasattr(constraint, "ge"):
            lo = constraint.ge
        elif hasattr(constraint, "gt"):
            lo = constraint.gt
        elif hasattr(constraint, "le"):
            hi = constraint.le
        elif hasattr(constraint, "lt"):
            hi = constraint.lt
    return lo, hi


def _group_spec(number: str, key: str, title: str, model: type, demo_critical: bool) -> dict:
    sensitive_names = sensitive_fields(model)
    fields = []
    for name, info in model.model_fields.items():
        field_key = info.alias or name
        kind, options = _field_kind(info.annotation)
        # A bool is never "required" in the sense a text/select/date field is —
        # an unchecked box is a valid, meaningful `False`, not a missing value.
        # schemas.py still requires the *key* be present for these (no
        # default), so the server side defaults it explicitly; see
        # _extract_group_kwargs.
        required = info.is_required() and kind != "checkbox"
        # A select whose Literal members are numbers (e.g. liability_limit,
        # the deductibles) must round-trip as JSON numbers, not strings — the
        # client casts using this flag.
        options_type = (
            "number"
            if kind == "select" and options and all(isinstance(o, (int, float)) for o in options)
            else None
        )
        min_value = max_value = None
        if kind == "number":
            min_value, max_value = _numeric_bounds(info)
        fields.append(
            {
                "name": name,
                "key": field_key,
                "label": _humanize(field_key),
                "kind": kind,
                "required": required,
                "sensitive": name in sensitive_names,
                "options": options,
                "optionsType": options_type,
                "min": min_value,
                "max": max_value,
            }
        )
    return {
        "number": number,
        "key": key,
        "title": title,
        "demo_critical": demo_critical,
        "model": model,
        "fields": fields,
    }


GROUP_SPECS: list[dict] = [_group_spec(*d) for d in _GROUP_DEFS]

# `date_of_birth` is a VaultRef in schemas.py (it's sensitive, so the schema
# only records that it's *vaulted*, not its shape) and so came out of
# _group_spec as a free-text field like the other sensitive strings. It's a
# calendar date like any other date field in this form — render it as one.
# Bounds aren't derivable from the schema either (VaultRef carries no date
# semantics at the type level): no one alive was born before 1900, and a
# birth date can't be in the future.
for _group in GROUP_SPECS:
    for _field in _group["fields"]:
        if _field["name"] == "date_of_birth":
            _field["kind"] = "date"
            _field["min"] = "1900-01-01"
            _field["max"] = date.today().isoformat()

# `purchase_year_month` is a plain `str` in schemas.py, constrained to YYYY-MM
# by IntakeVehicle's own validator rather than by the type system (there's no
# stdlib year-month type) — so, like date_of_birth above, it comes out of
# _group_spec as free text. Render it with the matching native picker instead.
for _group in GROUP_SPECS:
    for _field in _group["fields"]:
        if _field["name"] == "purchase_year_month":
            _field["kind"] = "month"
            _field["min"] = "1900-01"
            _field["max"] = "2027-12"

# `optional_ab_selections` is a free-form dict[str, Literal[...]] in the
# schema — the 13 optional accident benefit names aren't derivable from
# schemas.py, they come from the hackathon brief's Appendix. Single source
# of truth for both the rendered form (via GROUP_SPECS below) and any other
# code that needs the list — never hand-repeated in the HTML template.
OPTIONAL_AB_BENEFITS: list[str] = [
    "income_replacement",
    "non_earner",
    "caregiver",
    "lost_educational_expenses",
    "expenses_of_visitors",
    "housekeeping",
    "damage_to_personal_items",
    "death",
    "funeral",
    "dependant_care",
    "indexation",
    "supplementary_medical",
    "catastrophic",
]

for _group in GROUP_SPECS:
    if _group["key"] != "coverage_benchmark":
        continue
    for _field in _group["fields"]:
        if _field["name"] == "optional_ab_selections":
            _field["kind"] = "ab-toggle"
            _field["items"] = [
                {"key": k, "label": _humanize(k)} for k in OPTIONAL_AB_BENEFITS
            ]


def _spec_to_json() -> list[dict]:
    return [{k: v for k, v in spec.items() if k != "model"} for spec in GROUP_SPECS]


def _prefill_payload(profile: IntakeProfile | None) -> dict:
    """Built from an already-saved profile, shaped for the client: real
    values for non-sensitive fields (`values`), and — for sensitive fields —
    only the list of field KEYS that already have a vaulted value
    (`stored`), never the VaultRef token itself, let alone the plaintext it
    points to. This is the only thing GET /intake ever tells the browser
    about a sensitive field."""
    if profile is None:
        return {}
    dumped = profile.model_dump(mode="json", by_alias=True)
    prefill: dict[str, dict] = {}
    for spec in GROUP_SPECS:
        raw = dumped.get(spec["key"])
        if not raw:
            continue
        values: dict[str, Any] = {}
        stored: list[str] = []
        for field in spec["fields"]:
            key = field["key"]
            if key not in raw:
                continue
            value = raw[key]
            if field["sensitive"]:
                if not _is_empty_value(value):
                    stored.append(key)
            elif not _is_empty_value(value):
                values[key] = value
        if values or stored:
            prefill[spec["key"]] = {"values": values, "stored": stored}
    return prefill


# --- submission -> IntakeProfile, sensitive values -> vault ---------------------


def _extract_group_kwargs(
    spec: dict,
    raw: dict,
    vault_path: Path,
    vault_key: str | None,
    vaulted_out: list[str],
    existing_group: Any = None,
) -> dict:
    kwargs: dict[str, Any] = {}
    for field in spec["fields"]:
        key = field["key"]
        name = field["name"]

        if key not in raw:
            # schemas.py gives every checkbox field no default (it must be
            # present), but a checkbox that was never touched is a real,
            # meaningful `False` — never a missing value — so default it
            # rather than letting the model construction fail as "required".
            if field["kind"] == "checkbox":
                kwargs[name] = False
            continue
        value = raw[key]

        if not field["sensitive"]:
            kwargs[name] = value
            continue

        # The form never shows a sensitive field's plaintext to retype —
        # only a "stored" indicator (see _prefill_payload) — so a blank
        # submission here means "unchanged," not "erase," whenever a value
        # was already vaulted. `existing_group` carries the VaultRef(s) to
        # preserve; nothing here ever reads or needs the plaintext itself.
        existing_value = getattr(existing_group, name, None) if existing_group is not None else None

        if field["kind"] == "list-text":
            items = [v.strip() for v in (value or []) if isinstance(v, str) and v.strip()]
            if items:
                refs = [
                    vault.put(name, v, vault_path=vault_path, vault_key=vault_key) for v in items
                ]
                vaulted_out.append(name)
                kwargs[name] = refs
            elif existing_value:
                kwargs[name] = list(existing_value)
            else:
                kwargs[name] = []
        else:
            text = value.strip() if isinstance(value, str) else ""
            if text:
                kwargs[name] = vault.put(name, text, vault_path=vault_path, vault_key=vault_key)
                vaulted_out.append(name)
            elif existing_value:
                kwargs[name] = existing_value
            else:
                kwargs[name] = None
    return kwargs


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value is False
    if isinstance(value, (list, dict, str)):
        return len(value) == 0
    return False


def _group_has_content(spec: dict, raw: dict) -> bool:
    """True if `raw` holds at least one value a user actually entered.

    Booleans, empty lists and empty strings are the values every optional
    group's untouched fields naturally collapse to (an unchecked checkbox, a
    never-typed-into textarea) — a group full of only those isn't "filled
    in", it's a section the user opened and then left alone, and must not be
    force-validated as if every one of its own required fields were owed.
    `datetime`-kind fields (e.g. consent_timestamp) are captured
    automatically regardless of user input, so they don't count either.
    """
    auto_keys = {f["key"] for f in spec["fields"] if f["kind"] == "datetime"}
    return any(
        not _is_empty_value(v) for k, v in raw.items() if k not in auto_keys
    )


def _build_group(
    spec: dict,
    payload: dict,
    vault_path: Path,
    vault_key: str | None,
    vaulted_out: list[str],
    existing_group: Any = None,
):
    raw = payload.get(spec["key"])
    if not raw or (not spec["demo_critical"] and not _group_has_content(spec, raw)):
        if spec["demo_critical"]:
            raise ValueError(f"missing required group {spec['key']!r}")
        return None
    if spec["key"] == "consent" and not raw.get("consent_timestamp"):
        raw = dict(raw)
        raw["consent_timestamp"] = datetime.now(timezone.utc).isoformat()
    kwargs = _extract_group_kwargs(spec, raw, vault_path, vault_key, vaulted_out, existing_group)
    return spec["model"](**kwargs)


def build_profile_from_submission(
    payload: Any,
    *,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
    existing_profile: IntakeProfile | None = None,
) -> tuple[IntakeProfile, list[str]]:
    """Build an IntakeProfile from a submitted JSON object. Every sensitive
    field's plaintext goes to `vault.put()` and only the returned VaultRef is
    kept; the caller gets back the profile plus the sorted list of sensitive
    field NAMES that were vaulted (never values) for the confirmation view
    and the consent receipt.

    `existing_profile`, when given, lets a blank sensitive field on a
    re-submission keep its previously vaulted value instead of being read as
    "delete this" — the form only ever shows a "stored" indicator for a
    sensitive field, never the plaintext to retype, so blank must mean
    unchanged.
    """
    if not isinstance(payload, dict):
        raise ValueError("submission payload must be a JSON object")

    vaulted: list[str] = []
    groups = {
        spec["key"]: _build_group(
            spec,
            payload,
            vault_path,
            vault_key,
            vaulted,
            existing_group=getattr(existing_profile, spec["key"], None) if existing_profile else None,
        )
        for spec in GROUP_SPECS
    }
    profile = IntakeProfile(**groups)
    return profile, sorted(set(vaulted))


def save_profile(profile: IntakeProfile, path: Path = PROFILE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2))
    return path


def load_profile(path: Path = PROFILE_PATH) -> IntakeProfile | None:
    if not path.exists():
        return None
    return IntakeProfile.model_validate_json(path.read_text())


# --- HTML generation --------------------------------------------------------------


def render_html(*, profile_path: Path = PROFILE_PATH) -> str:
    payload = json.dumps(_spec_to_json(), separators=(",", ":")).replace("</", "<\\/")
    prefill = json.dumps(
        _prefill_payload(load_profile(path=profile_path)), separators=(",", ":")
    ).replace("</", "<\\/")
    return (
        _TEMPLATE.replace("__ALLQUOTE_SPEC__", payload).replace("__ALLQUOTE_PREFILL__", prefill)
    )


def generate(output_path: Path = OUTPUT_PATH, *, profile_path: Path = PROFILE_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(profile_path=profile_path))
    return output_path


# --- local server -------------------------------------------------------------------


class _IntakeHandler(BaseHTTPRequestHandler):
    server_version = "AllQuoteIntake/0.1"
    intake_html: bytes = b""
    vault_path: Path = vault.VAULT_PATH
    vault_key: str | None = None
    profile_path: Path = PROFILE_PATH

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Deliberately ignore `format`/`args` — for a request line they'd only
        # ever be method/path/status, but nothing here trusts that; only the
        # attributes below are ever written, never anything derived from the
        # request body.
        sys.stderr.write(f"{self.address_string()} {self.command} {self.path}\n")

    log_error = log_message

    def _send_json(self, status: int, obj: dict) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/intake.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(self.intake_html)))
            self.end_headers()
            self.wfile.write(self.intake_html)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/submit":
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return
        finally:
            del body

        try:
            existing_profile = load_profile(path=self.profile_path)
            profile, vaulted = build_profile_from_submission(
                payload,
                vault_path=self.vault_path,
                vault_key=self.vault_key,
                existing_profile=existing_profile,
            )
        except (ValidationError, ValueError, KeyError):
            # Deliberately generic: never fold the exception (which may quote
            # a submitted non-sensitive value) or the payload into a response.
            self._send_json(400, {"error": "profile validation failed — check required fields"})
            return
        except Exception:
            # Anything else (e.g. a vault key/store mismatch) must still
            # produce a clean response — an uncaught exception here would
            # fall through to socketserver's default handler, which prints a
            # traceback outside our log_message/log_error override.
            self._send_json(500, {"error": "internal error — profile was not saved"})
            return
        finally:
            del payload

        try:
            save_profile(profile, path=self.profile_path)
            receipt_id = redact.write_consent_receipt(
                CONSENT_RECEIPT_ROUTE_ID, vaulted, datetime.now(timezone.utc)
            )
        except Exception:
            self._send_json(500, {"error": "internal error — profile was not saved"})
            return

        self._send_json(
            200,
            {
                "fields_encrypted": vaulted,
                "completeness": profile.completeness(),
                "consent_receipt_id": receipt_id,
            },
        )


def _handler_class(
    *,
    intake_html: bytes,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
    profile_path: Path = PROFILE_PATH,
) -> type[_IntakeHandler]:
    return type(
        "BoundIntakeHandler",
        (_IntakeHandler,),
        {
            "intake_html": intake_html,
            "vault_path": vault_path,
            "vault_key": vault_key,
            "profile_path": profile_path,
        },
    )


def serve(
    host: str = "127.0.0.1",
    port: int = 8420,
    *,
    open_browser: bool = True,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
    profile_path: Path = PROFILE_PATH,
) -> None:
    html_path = generate(profile_path=profile_path)
    handler_cls = _handler_class(
        intake_html=html_path.read_bytes(),
        vault_path=vault_path,
        vault_key=vault_key,
        profile_path=profile_path,
    )
    httpd = ThreadingHTTPServer((host, port), handler_cls)
    url = f"http://{host}:{port}/"
    print(f"serving intake form at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m allquote.intake")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build")
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--port", type=int, default=8420)
    serve_parser.add_argument("--no-open", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "build":
        path = generate()
        print(f"wrote {path}")
    elif args.command == "serve":
        serve(port=args.port, open_browser=not args.no_open)
    return 0


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>All-Quote — Driver profile intake</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {
  /* Paper — surfaces, lightest to most recessed */
  --paper:        #F3F6EF;
  --band:         #E9EFE5;
  --sunken:       #E2E9DE;

  /* Ink — text, strongest to faintest */
  --ink-900:      #12180F;
  --ink-700:      #1A2016;
  --ink-500:      #55604F;
  --ink-400:      #767F71;
  --ink-300:      #8D958A;

  /* Rules — hairlines, never shadows */
  --rule:         #C6D0C0;
  --rule-strong:  #A8B5A2;

  /* Accent — exactly one */
  --stamp:        #8C2F39;

  /* Semantic layer — components reference roles, never raw values */
  --text-primary:   var(--ink-900);
  --text-body:      var(--ink-700);
  --text-label:     var(--ink-500);
  --text-caption:   var(--ink-400);
  --text-muted:     var(--ink-300);

  --surface:        var(--paper);
  --surface-alt:    var(--band);
  --surface-sunken: var(--sunken);

  --border:         var(--rule);
  --border-strong:  var(--rule-strong);
  --border-focus:   var(--stamp);

  --accent:         var(--stamp);
}

* { box-sizing: border-box; }

html, body {
  background: var(--surface);
  color: var(--text-body);
  margin: 0;
  padding: 0;
}

body {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-variant-numeric: tabular-nums;
  line-height: 1.35;
  font-size: 13px;
}

.page {
  max-width: 700px;
  margin: 0 auto;
  padding: 80px 40px 96px;
}

@media (max-width: 480px) {
  .page { padding: 40px 20px 64px; }
}

button { font-family: inherit; }

:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}

.eyebrow {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  line-height: 1.4;
  color: var(--text-muted);
}

/* -- masthead -- */

.masthead h1 {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.2;
  color: var(--text-primary);
  margin: 6px 0 6px;
}

.masthead .subtitle {
  color: var(--text-caption);
  font-size: 12px;
  letter-spacing: 0.01em;
  line-height: 1.4;
  margin: 0 0 14px;
}

.masthead .rule { border: none; border-top: 1px solid var(--border-strong); margin: 0 0 10px; }

.masthead .meta {
  color: var(--text-label);
  font-size: 12px;
  letter-spacing: 0.01em;
  line-height: 1.4;
}

/* -- form sections -- */

.form-section {
  display: grid;
  grid-template-columns: 40px 1fr;
  column-gap: 16px;
  margin: 0 0 56px;
}

@media (max-width: 480px) {
  .form-section { grid-template-columns: 1fr; row-gap: 6px; }
}

.section-num {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  line-height: 1.4;
  color: var(--text-muted);
  padding-top: 5px;
}

.section-body h2 {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
  line-height: 1.3;
  color: var(--text-primary);
  margin: 0 0 20px;
}

.section-toggle {
  display: block;
  background: none;
  border: none;
  border-bottom: 1px solid transparent;
  padding: 0 0 3px;
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  line-height: 1.4;
  color: var(--text-label);
  cursor: pointer;
}

.section-toggle:hover { color: var(--text-body); }

.section-toggle.active {
  color: var(--text-body);
  border-bottom-color: var(--accent);
  margin-bottom: 20px;
}

.section-fields { margin-top: 4px; }
.section-fields[hidden] { display: none; }

.sensitive-note {
  font-size: 11px;
  color: var(--text-caption);
  letter-spacing: 0.01em;
  line-height: 1.45;
  margin: -8px 0 20px;
}

/* -- fields -- */

.field-row {
  position: relative;
  margin: 0 0 28px;
  padding-right: 20px;
}

.field-row--checkbox { padding-right: 0; }

.field-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.01em;
  line-height: 1.4;
  color: var(--text-label);
  margin-bottom: 6px;
}

.field-row:focus-within .field-label { color: var(--text-primary); }

.required-mark { color: var(--accent); margin-left: 2px; }

.lock {
  position: absolute;
  right: 0;
  top: 0;
  color: var(--accent);
  font-size: 13px;
  line-height: 1.4;
}

.field-row input[type="text"],
.field-row input[type="number"],
.field-row input[type="date"],
.field-row input[type="month"],
.field-row select,
.field-row textarea {
  display: block;
  width: 100%;
  font: inherit;
  font-size: 15px;
  color: var(--text-body);
  background: none;
  border: none;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  padding: 6px 0;
  transition: border-color 120ms;
}

.field-row textarea { resize: vertical; }

.field-row input[type="text"]:focus,
.field-row input[type="number"]:focus,
.field-row input[type="date"]:focus,
.field-row input[type="month"]:focus,
.field-row select:focus,
.field-row textarea:focus {
  outline: none;
  border-bottom: 2px solid var(--border-focus);
  padding-bottom: 5px;
}

.checkbox-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-body);
  margin: 0 20px 8px 0;
}

.checkbox-inline input[type="checkbox"] {
  appearance: none;
  -webkit-appearance: none;
  flex: 0 0 auto;
  width: 14px;
  height: 14px;
  margin: 0;
  border: 1px solid var(--border);
  border-radius: 0;
  background: var(--surface);
  position: relative;
  cursor: pointer;
}

.checkbox-inline input[type="checkbox"]:checked {
  background: var(--text-body);
  border-color: var(--text-body);
}

.checkbox-inline input[type="checkbox"]:checked::after {
  content: "";
  position: absolute;
  left: 4px;
  top: 1px;
  width: 3px;
  height: 7px;
  border: solid var(--surface);
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

.checkbox-inline input[type="checkbox"]:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 2px;
}

.checkbox-list { display: flex; flex-wrap: wrap; }

.field-help {
  font-size: 11px;
  color: var(--text-caption);
  letter-spacing: 0.01em;
  line-height: 1.45;
  margin-top: 4px;
}

.field-error {
  margin-top: 4px;
  font-size: 11px;
  letter-spacing: 0.01em;
  line-height: 1.45;
  color: var(--accent);
}

.field-row.has-error input[type="text"],
.field-row.has-error input[type="number"],
.field-row.has-error input[type="date"],
.field-row.has-error input[type="month"],
.field-row.has-error select {
  border-bottom-color: var(--accent);
}

/* -- optional accident benefits: 4-way text toggles -- */

.ab-note { margin: 0 0 16px; }

.ab-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 8px 0;
  border-bottom: 1px dotted var(--border);
}

.ab-label { font-size: 13px; color: var(--text-body); }

.toggle-group { display: flex; gap: 14px; flex: 0 0 auto; }

.toggle-option {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 2px 0;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  line-height: 1.4;
  color: var(--text-label);
  cursor: pointer;
}

.toggle-option:hover { color: var(--text-body); }

.toggle-option.active {
  color: var(--text-body);
  border-bottom-color: var(--accent);
}

/* -- submit + errors -- */

.submit-row {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--border-strong);
}

.submit-action {
  background: none;
  border: none;
  padding: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--text-primary);
  cursor: pointer;
}

.submit-action:hover { text-decoration: underline; }
.submit-action:disabled { color: var(--text-muted); cursor: default; text-decoration: none; }

.error-banner {
  margin-top: 12px;
  font-size: 11px;
  letter-spacing: 0.01em;
  line-height: 1.45;
  color: var(--accent);
}

/* -- confirmation -- */

.confirm-list { margin: 0 0 8px; }

.confirm-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px dotted var(--border);
  padding: 5px 0;
  font-size: 13px;
  color: var(--text-body);
}

.confirm-row .lock { position: static; margin-right: 8px; }
.confirm-row.confirm-empty { color: var(--text-muted); }
.confirm-state { color: var(--text-label); }

section.block { margin: 0 0 48px; }
section.block > h2 {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  line-height: 1.4;
  color: var(--text-muted);
  margin: 0 0 16px;
}
</style>
</head>
<body>
<div class="page" id="page-root">

  <header class="masthead">
    <div class="eyebrow">PERSONAL USE — DISCOVERY INTAKE</div>
    <h1>Driver profile intake</h1>
    <div class="subtitle">Captured once. Licence, DOB, VIN, address, email and
      phone are encrypted before anything else in this app can see them.</div>
    <hr class="rule">
    <div class="meta">not insurance advice · nothing here is sent to any insurer</div>
  </header>

  <div id="form-root"></div>

  <div class="submit-row">
    <button type="button" id="submit-action" class="submit-action">Save profile &rarr;</button>
    <div class="error-banner" id="error-banner" hidden></div>
  </div>

  <div class="submit-row">
    <button type="button" id="find-quotes-action" class="submit-action">Find quotes &rarr;</button>
    <div class="field-help">starts a run against the saved profile — save first if you changed anything above</div>
    <div class="error-banner" id="find-quotes-error" hidden></div>
  </div>

</div>

<script id="allquote-spec" type="application/json">__ALLQUOTE_SPEC__</script>
<script id="allquote-prefill" type="application/json">__ALLQUOTE_PREFILL__</script>
<script>
(function () {
  "use strict";

  var SPEC = JSON.parse(document.getElementById("allquote-spec").textContent);
  var PREFILL = JSON.parse(document.getElementById("allquote-prefill").textContent);
  var SPEC_BY_KEY = {};
  SPEC.forEach(function (s) { SPEC_BY_KEY[s.key] = s; });

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fieldId(groupKey, fieldKey) { return "f_" + groupKey + "__" + fieldKey; }

  var firstSensitiveKey = null;
  for (var i = 0; i < SPEC.length; i++) {
    if (SPEC[i].fields.some(function (f) { return f.sensitive; })) {
      firstSensitiveKey = SPEC[i].key;
      break;
    }
  }

  function isStored(field, groupKey) {
    if (!field.sensitive) return false;
    var groupPrefill = PREFILL[groupKey];
    return !!(groupPrefill && (groupPrefill.stored || []).indexOf(field.key) !== -1);
  }

  function renderField(field, groupKey) {
    if (field.kind === "datetime") return "";

    var id = fieldId(groupKey, field.key);
    var reqMark = field.required ? '<span class="required-mark">*</span>' : "";
    var lock = field.sensitive ? '<span class="lock" aria-hidden="true">&#9111;</span>' : "";
    var storedNote = isStored(field, groupKey)
      ? '<div class="field-help">&#8226;&#8226;&#8226;&#8226; stored — leave blank to keep it</div>'
      : "";

    if (field.kind === "checkbox") {
      // Booleans are never "required" — an unchecked box is a meaningful
      // false, not a missing value — so no reqMark, no required attribute.
      return '<div class="field-row field-row--checkbox">' +
        '<label class="checkbox-inline"><input type="checkbox" id="' + id + '"> ' +
        esc(field.label) + '</label></div>';
    }

    if (field.kind === "ab-toggle") {
      var note = '<div class="field-help ab-note">optional since July 1, 2026 — only ' +
        'medical, rehabilitation and attendant care remain mandatory.</div>';
      var rows = (field.items || []).map(function (item) {
        var toggles = (field.options || []).map(function (v) {
          var isDefault = v === "excluded";
          return '<button type="button" class="toggle-option' + (isDefault ? " active" : "") +
            '" data-value="' + esc(v) + '">' + esc(v) + '</button>';
        }).join("");
        return '<div class="ab-row"><span class="ab-label">' + esc(item.label) + '</span>' +
          '<div class="toggle-group" data-abgroup="' + id + '" data-item="' + esc(item.key) +
          '">' + toggles + '</div></div>';
      }).join("");
      return '<div class="field-row field-row--ab">' +
        '<label class="field-label">' + esc(field.label) + '</label>' +
        note + '<div class="ab-list">' + rows + '</div></div>';
    }

    var labelHtml = '<label class="field-label" for="' + id + '">' + esc(field.label) + reqMark + '</label>' + lock;
    var control = "";

    if (field.kind === "select") {
      var opts = '<option value="">— select —</option>' +
        (field.options || []).map(function (o) {
          return '<option value="' + esc(o) + '">' + esc(o) + '</option>';
        }).join("");
      control = '<select id="' + id + '"' + (field.required ? " required" : "") + '>' + opts + '</select>';
    } else if (field.kind === "checkbox-list") {
      control = '<div class="checkbox-list">' + (field.options || []).map(function (o) {
        return '<label class="checkbox-inline"><input type="checkbox" value="' + esc(o) +
          '" data-cbgroup="' + id + '"> ' + esc(o) + '</label>';
      }).join("") + '</div>';
    } else if (field.kind === "list-text") {
      control = '<textarea id="' + id + '" rows="3" placeholder="one per line"></textarea>';
    } else if (field.kind === "number") {
      var bounds = (field.min !== null && field.min !== undefined ? ' min="' + field.min + '"' : "") +
        (field.max !== null && field.max !== undefined ? ' max="' + field.max + '"' : "");
      control = '<input type="number" step="any" id="' + id + '"' + bounds + (field.required ? " required" : "") + '>';
    } else if (field.kind === "date" || field.kind === "month") {
      var dateBounds = (field.min !== null && field.min !== undefined ? ' min="' + field.min + '"' : "") +
        (field.max !== null && field.max !== undefined ? ' max="' + field.max + '"' : "");
      control = '<input type="' + field.kind + '" id="' + id + '"' + dateBounds + (field.required ? " required" : "") + '>';
    } else {
      control = '<input type="text" autocomplete="off" id="' + id + '"' + (field.required ? " required" : "") + '>';
    }

    return '<div class="field-row" id="row-' + id + '">' + labelHtml + control + storedNote +
      '<div class="field-error" id="err-' + id + '" hidden></div></div>';
  }

  function groupHasPrefill(groupKey) {
    var groupPrefill = PREFILL[groupKey];
    if (!groupPrefill) return false;
    return Object.keys(groupPrefill.values || {}).length > 0 || (groupPrefill.stored || []).length > 0;
  }

  function renderSection(spec, isFirstSensitive) {
    var body = spec.fields.map(function (f) { return renderField(f, spec.key); }).join("");
    var note = isFirstSensitive
      ? '<div class="sensitive-note">encrypted at rest — never written to logs, prompts or screenshots</div>'
      : "";

    // An optional group with a saved value is opened by default — the
    // point of prefill is to show what is already on file, not to hide it
    // behind a "+ Add" toggle the user has to know to click.
    var open = spec.demo_critical || groupHasPrefill(spec.key);

    var header = spec.demo_critical
      ? '<h2>' + esc(spec.title) + '</h2>'
      : '<button type="button" class="section-toggle' + (open ? " active" : "") +
        '" data-group="' + spec.key + '">' + (open ? "&minus; " : "+ Add ") +
        esc(spec.title.toLowerCase()) + '</button>';

    var fieldsAttrs = 'id="fields-' + spec.key + '"' + (open ? "" : " hidden");

    return '<section class="form-section" data-group="' + spec.key + '">' +
      '<div class="section-num">' + esc(spec.number) + '</div>' +
      '<div class="section-body">' + header +
      '<div class="section-fields" ' + fieldsAttrs + '>' + note + body + '</div>' +
      '</div></section>';
  }

  var root = document.getElementById("form-root");
  SPEC.forEach(function (spec) {
    root.insertAdjacentHTML("beforeend", renderSection(spec, spec.key === firstSensitiveKey));
  });

  function applyPrefillValue(field, groupKey, value) {
    var id = fieldId(groupKey, field.key);
    if (field.kind === "checkbox") {
      document.getElementById(id).checked = !!value;
    } else if (field.kind === "checkbox-list") {
      var wanted = {};
      (value || []).forEach(function (v) { wanted[v] = true; });
      document.querySelectorAll('[data-cbgroup="' + id + '"]').forEach(function (cb) {
        cb.checked = !!wanted[cb.value];
      });
    } else if (field.kind === "list-text") {
      document.getElementById(id).value = (value || []).join("\n");
    } else if (field.kind === "ab-toggle") {
      (field.items || []).forEach(function (item) {
        var v = (value || {})[item.key];
        if (!v) return;
        var itemGroup = document.querySelector(
          '.toggle-group[data-abgroup="' + id + '"][data-item="' + item.key + '"]'
        );
        if (!itemGroup) return;
        itemGroup.querySelectorAll(".toggle-option").forEach(function (b) {
          b.classList.toggle("active", b.getAttribute("data-value") === v);
        });
      });
    } else {
      var input = document.getElementById(id);
      if (input) input.value = value;
    }
  }

  // Every non-sensitive value already on file, applied straight onto the
  // rendered inputs — sensitive fields are never touched here, they only
  // ever get the "stored" note rendered above (see isStored/renderField).
  SPEC.forEach(function (spec) {
    var groupPrefill = PREFILL[spec.key];
    if (!groupPrefill) return;
    var values = groupPrefill.values || {};
    spec.fields.forEach(function (f) {
      if (f.sensitive || f.kind === "datetime") return;
      if (!(f.key in values)) return;
      applyPrefillValue(f, spec.key, values[f.key]);
    });
  });

  document.addEventListener("click", function (e) {
    var toggleOption = e.target.closest(".toggle-option");
    if (toggleOption) {
      var group = toggleOption.closest(".toggle-group");
      group.querySelectorAll(".toggle-option").forEach(function (b) {
        b.classList.remove("active");
      });
      toggleOption.classList.add("active");
      return;
    }

    var btn = e.target.closest(".section-toggle");
    if (!btn) return;
    var key = btn.getAttribute("data-group");
    var fields = document.getElementById("fields-" + key);
    fields.hidden = !fields.hidden;
    var open = !fields.hidden;
    btn.classList.toggle("active", open);
    btn.textContent = (open ? "− " : "+ Add ") + SPEC_BY_KEY[key].title.toLowerCase();
  });

  function fieldValue(field, groupKey) {
    if (field.kind === "datetime") return new Date().toISOString();

    var id = fieldId(groupKey, field.key);

    if (field.kind === "checkbox") {
      return document.getElementById(id).checked;
    }
    if (field.kind === "checkbox-list") {
      return Array.prototype.slice
        .call(document.querySelectorAll('[data-cbgroup="' + id + '"]:checked'))
        .map(function (cb) { return cb.value; });
    }
    if (field.kind === "list-text") {
      return document.getElementById(id).value
        .split("\n").map(function (s) { return s.trim(); }).filter(Boolean);
    }
    if (field.kind === "ab-toggle") {
      var obj = {};
      (field.items || []).forEach(function (item) {
        var itemGroup = document.querySelector(
          '.toggle-group[data-abgroup="' + id + '"][data-item="' + item.key + '"]'
        );
        var active = itemGroup ? itemGroup.querySelector(".toggle-option.active") : null;
        obj[item.key] = active ? active.getAttribute("data-value") : "excluded";
      });
      return obj;
    }

    var input = document.getElementById(id);
    if (input.value === "") return undefined;
    var isNumeric = field.kind === "number" || field.optionsType === "number";
    return isNumeric ? Number(input.value) : input.value;
  }

  function collectPayload() {
    var payload = {};
    SPEC.forEach(function (spec) {
      var fieldsEl = document.getElementById("fields-" + spec.key);
      var open = spec.demo_critical || !fieldsEl.hidden;
      if (!open) return;
      var g = {};
      spec.fields.forEach(function (f) {
        var v = fieldValue(f, spec.key);
        if (v === undefined) return;
        g[f.key] = v;
      });
      payload[spec.key] = g;
    });
    return payload;
  }

  function showError(msg) {
    var banner = document.getElementById("error-banner");
    banner.textContent = msg;
    banner.hidden = false;
  }

  function requiredMessage(field) {
    if (field.kind === "select") return "choose " + field.label.toLowerCase();
    if (field.kind === "date") return field.label.toLowerCase() + " needs a date";
    if (field.kind === "month") return field.label.toLowerCase() + " needs a month, like 2022-06";
    return field.label.toLowerCase() + " needs a value";
  }

  function clearFieldErrors() {
    document.querySelectorAll(".field-error").forEach(function (el) {
      el.hidden = true;
      el.textContent = "";
    });
    document.querySelectorAll(".field-row.has-error").forEach(function (el) {
      el.classList.remove("has-error");
    });
  }

  function validateForm() {
    clearFieldErrors();
    var firstErrorRow = null;

    SPEC.forEach(function (spec) {
      var fieldsEl = document.getElementById("fields-" + spec.key);
      var open = spec.demo_critical || !fieldsEl.hidden;
      if (!open) return;

      spec.fields.forEach(function (f) {
        if (!f.required) return;
        var v = fieldValue(f, spec.key);
        var missing = v === undefined || v === "" || (Array.isArray(v) && v.length === 0);
        if (!missing) return;

        var id = fieldId(spec.key, f.key);
        var row = document.getElementById("row-" + id);
        var err = document.getElementById("err-" + id);
        if (row) row.classList.add("has-error");
        if (err) {
          err.textContent = requiredMessage(f);
          err.hidden = false;
        }
        if (!firstErrorRow) firstErrorRow = row;
      });
    });

    if (firstErrorRow) {
      firstErrorRow.scrollIntoView({ block: "center" });
      return false;
    }
    return true;
  }

  function showConfirmation(result) {
    var fieldsHtml = result.fields_encrypted.length
      ? result.fields_encrypted.map(function (n) {
          return '<div class="confirm-row"><span><span class="lock">&#9111;</span>' +
            esc(n) + '</span></div>';
        }).join("")
      : '<div class="confirm-row confirm-empty">no sensitive fields captured</div>';

    var completenessHtml = SPEC.map(function (spec) {
      var done = !!result.completeness[spec.key];
      var glyph = done ? "■" : "·";
      var state = done ? "captured" : "not provided";
      return '<div class="confirm-row"><span>' + glyph + ' ' + esc(spec.title) +
        '</span><span class="confirm-state">' + state + '</span></div>';
    }).join("");

    document.getElementById("page-root").innerHTML =
      '<header class="masthead">' +
        '<div class="eyebrow">CONFIRMED</div>' +
        '<h1>Profile saved</h1>' +
        '<div class="masthead subtitle">consent receipt ' + esc(result.consent_receipt_id) + '</div>' +
        '<hr class="rule">' +
      '</header>' +
      '<section class="block"><h2>Encrypted fields</h2><div class="confirm-list">' + fieldsHtml + '</div></section>' +
      '<section class="block"><h2>Completeness by group</h2><div class="confirm-list">' + completenessHtml + '</div></section>';
  }

  document.getElementById("submit-action").addEventListener("click", function () {
    document.getElementById("error-banner").hidden = true;
    if (!validateForm()) return;

    var btn = this;
    btn.disabled = true;

    fetch("/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectPayload())
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (r) {
      if (!r.ok) {
        showError(r.data.error || "submission failed");
        btn.disabled = false;
        return;
      }
      showConfirmation(r.data);
    }).catch(function () {
      showError("could not reach the intake server");
      btn.disabled = false;
    });
  });

  document.getElementById("find-quotes-action").addEventListener("click", function () {
    var btn = this;
    var err = document.getElementById("find-quotes-error");
    err.hidden = true;
    btn.disabled = true;

    fetch("/api/run/start", { method: "POST" }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (r) {
      if (!r.ok) {
        err.textContent = r.data.error || "could not start a run";
        err.hidden = false;
        btn.disabled = false;
        return;
      }
      window.location.href = "/run";
    }).catch(function () {
      err.textContent = "could not reach the server";
      err.hidden = false;
      btn.disabled = false;
    });
  });
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
