import http.client
import io
import json
import sys
import threading
import urllib.request

from http.server import ThreadingHTTPServer

from allquote import intake

_VALID_PAYLOAD = {
    "identity": {
        "legal_name": "Fake Testperson",
        "preferred_language": "en",
        "date_of_birth": "1990-01-15",
        "gender": "unspecified",
        "marital_status": "single",
    },
    "licence": {
        "licence_number": "T1234-56789-01234",
        "province": "ON",
        "class": "G",
        "status": "valid",
        "driver_training_completed": True,
    },
    "vehicle": {
        "vin": "FAKEVEH0000000001",
        "model_year": 2022,
        "make": "Testmake",
        "model": "Testmodel",
        "ownership": "owned",
        "purchase_year_month": "2022-06",
    },
    "address": {
        "street": "123 Fake Test Street",
        "city": "Testville",
        "province": "ON",
        "postal_code": "M5V3A8",
        "fsa": "M5V",
        "residence_start_date": "2020-01-01",
        "is_garaging_location": True,
    },
    "coverage_benchmark": {
        "effective_date": "2026-08-09",
        "liability_limit": 2000000,
        "dcpd_included": True,
        "collision_deductible": 1000,
        "comprehensive_deductible": 1000,
        "telematics_opt_in": False,
    },
}


def test_group_specs_cover_all_nine_profile_groups_in_order():
    keys = [g["key"] for g in intake.GROUP_SPECS]
    assert keys == [
        "identity", "licence", "vehicle", "address", "coverage_benchmark",
        "consent", "contact", "use", "history",
    ]
    numbers = [g["number"] for g in intake.GROUP_SPECS]
    assert numbers == [f"{i:02d}" for i in range(1, 10)]
    assert sum(1 for g in intake.GROUP_SPECS if g["demo_critical"]) == 5
    assert sum(1 for g in intake.GROUP_SPECS if not g["demo_critical"]) == 4


def test_generated_html_has_five_open_and_four_toggled_sections(tmp_path):
    # Sections are rendered client-side from the embedded spec (see
    # allquote/intake.py's _TEMPLATE), so assert against that embedded JSON
    # rather than counting DOM strings that only exist once a browser runs
    # the renderer.
    out = intake.generate(output_path=tmp_path / "intake.html")
    html = out.read_text()
    for n in [f"{i:02d}" for i in range(1, 10)]:
        assert n in html
    assert "section-toggle" in html
    assert "encrypted at rest" in html

    marker = 'id="allquote-spec" type="application/json">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    spec = json.loads(html[start:end])
    assert sum(1 for g in spec if g["demo_critical"]) == 5
    assert sum(1 for g in spec if not g["demo_critical"]) == 4


def test_generated_html_has_all_13_optional_ab_benefit_rows(tmp_path):
    out = intake.generate(output_path=tmp_path / "intake.html")
    html = out.read_text()

    assert len(intake.OPTIONAL_AB_BENEFITS) == 13
    for key in intake.OPTIONAL_AB_BENEFITS:
        assert key in html, f"{key!r} missing from generated intake.html"
    assert "July 1, 2026" in html


def test_build_profile_from_submission_vaults_sensitive_fields_only(tmp_path):
    vault_path = tmp_path / "vault.enc"
    profile, vaulted = intake.build_profile_from_submission(
        _VALID_PAYLOAD, vault_path=vault_path, vault_key="test-key-not-real-intake-0001"
    )

    assert vaulted == sorted(
        {"legal_name", "date_of_birth", "licence_number", "vin", "street", "postal_code"}
    )
    dumped = profile.model_dump_json()
    for plaintext in ("Fake Testperson", "T1234-56789-01234", "FAKEVEH0000000001"):
        assert plaintext not in dumped
    assert profile.contact is None
    assert profile.history is None
    assert profile.completeness() == {
        "identity": True, "licence": True, "vehicle": True, "address": True,
        "coverage_benchmark": True, "consent": False, "contact": False,
        "use": False, "history": False,
    }


def test_build_profile_from_submission_requires_demo_critical_groups(tmp_path):
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "vehicle"}
    try:
        intake.build_profile_from_submission(
            payload, vault_path=tmp_path / "vault.enc", vault_key="test-key-not-real-intake-0002"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for missing required group")


def test_save_and_load_profile_round_trips_vault_refs_only(tmp_path):
    vault_path = tmp_path / "vault.enc"
    profile, _ = intake.build_profile_from_submission(
        _VALID_PAYLOAD, vault_path=vault_path, vault_key="test-key-not-real-intake-0003"
    )
    profile_path = tmp_path / "profile.json"
    intake.save_profile(profile, path=profile_path)

    assert "Fake Testperson" not in profile_path.read_text()
    loaded = intake.load_profile(path=profile_path)
    assert loaded == profile


def test_checkbox_fields_are_never_required_and_default_false(tmp_path):
    for group in intake.GROUP_SPECS:
        for field in group["fields"]:
            if field["kind"] == "checkbox":
                assert field["required"] is False, (group["key"], field["name"])

    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    for field in ("dcpd_included", "telematics_opt_in"):
        del payload["coverage_benchmark"][field]
    del payload["licence"]["driver_training_completed"]
    del payload["address"]["is_garaging_location"]

    profile, _ = intake.build_profile_from_submission(
        payload, vault_path=tmp_path / "vault.enc", vault_key="test-key-not-real-intake-0008"
    )
    assert profile.coverage_benchmark.dcpd_included is False
    assert profile.coverage_benchmark.telematics_opt_in is False
    assert profile.licence.driver_training_completed is False
    assert profile.address.is_garaging_location is False


def test_optional_group_opened_but_left_empty_is_not_force_validated(tmp_path):
    # A group the user toggled open (so its checkboxes/lists are present as
    # their untouched defaults: False / [] / auto timestamp) but never
    # actually typed into must be treated the same as a group that was never
    # opened at all — not validated against its own required fields.
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["use"] = {"winter_tires": False, "anti_theft": False}

    profile, _ = intake.build_profile_from_submission(
        payload, vault_path=tmp_path / "vault.enc", vault_key="test-key-not-real-intake-0009"
    )
    assert profile.use is None


def test_optional_free_text_fields_accept_blank_and_store_none(tmp_path):
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    del payload["vehicle"]["vin"]  # no vehicle yet — must not require a VIN
    payload["contact"] = {
        "email": "fake@example.invalid",
        "mobile": "416-555-0100",
        # preferred_callback_window omitted — must accept blank
    }

    profile, vaulted = intake.build_profile_from_submission(
        payload, vault_path=tmp_path / "vault.enc", vault_key="test-key-not-real-intake-0010"
    )
    assert profile.vehicle.vin is None
    assert "vin" not in vaulted
    assert profile.contact.preferred_callback_window is None


def _start_server(tmp_path, vault_key):
    intake.generate(output_path=tmp_path / "intake.html")
    handler_cls = intake._handler_class(
        intake_html=(tmp_path / "intake.html").read_bytes(),
        vault_path=tmp_path / "vault.enc",
        vault_key=vault_key,
        profile_path=tmp_path / "profile.json",
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def test_post_submit_returns_encrypted_field_names_and_completeness(tmp_path):
    httpd, thread = _start_server(tmp_path, "test-key-not-real-intake-0004")
    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
        body = json.dumps(_VALID_PAYLOAD).encode()
        conn.request("POST", "/submit", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()

        assert resp.status == 200
        assert "legal_name" in data["fields_encrypted"]
        assert data["completeness"]["identity"] is True
        assert data["completeness"]["contact"] is False
        assert "consent_receipt_id" in data
        assert json.dumps(data).find("Fake Testperson") == -1
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()


def test_server_never_logs_request_body(tmp_path, monkeypatch):
    secret = "FAKE-SUPER-SECRET-BODY-MARKER-0001"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["identity"]["legal_name"] = secret

    httpd, thread = _start_server(tmp_path, "test-key-not-real-intake-0005")

    captured_out = io.StringIO()
    captured_err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)
    monkeypatch.setattr(sys, "stderr", captured_err)

    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
        body = json.dumps(payload).encode()
        conn.request("POST", "/submit", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        assert resp.status == 200
        assert "legal_name" in data["fields_encrypted"]
        assert secret not in json.dumps(data)
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()

    assert secret not in captured_out.getvalue()
    assert secret not in captured_err.getvalue()


def test_demo_critical_groups_only_submission_validates_and_stores(tmp_path):
    # _VALID_PAYLOAD has only the five demo-critical groups — no consent,
    # contact, use or history. This is the case IntakeProfile.completeness()
    # exists to support (a usable profile that's honest about what's still
    # missing) and it must never regress, so this goes through the real
    # server layer via urllib.request rather than calling Python functions
    # directly.
    httpd, thread = _start_server(tmp_path, "test-key-not-real-intake-0007")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/submit",
            data=json.dumps(_VALID_PAYLOAD).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            data = json.loads(resp.read())
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()

    assert status == 200
    assert data["completeness"] == {
        "identity": True, "licence": True, "vehicle": True, "address": True,
        "coverage_benchmark": True, "consent": False, "contact": False,
        "use": False, "history": False,
    }

    profile_path = tmp_path / "profile.json"
    assert profile_path.exists()
    stored = intake.load_profile(path=profile_path)
    assert stored.consent is None
    assert stored.contact is None
    assert stored.use is None
    assert stored.history is None
    assert stored.completeness()["identity"] is True


def test_optional_ab_selections_round_trip_into_stored_profile(tmp_path):
    submitted_ab = {
        "income_replacement": "included",
        "non_earner": "excluded",
        "caregiver": "unavailable",
        "lost_educational_expenses": "unknown",
        "expenses_of_visitors": "excluded",
        "housekeeping": "included",
        "damage_to_personal_items": "excluded",
        "death": "excluded",
        "funeral": "excluded",
        "dependant_care": "excluded",
        "indexation": "excluded",
        "supplementary_medical": "included",
        "catastrophic": "unknown",
    }
    assert set(submitted_ab) == set(intake.OPTIONAL_AB_BENEFITS)

    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["coverage_benchmark"]["optional_ab_selections"] = submitted_ab

    httpd, thread = _start_server(tmp_path, "test-key-not-real-intake-0011")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/submit",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            status = resp.status
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()

    assert status == 200
    stored = intake.load_profile(path=tmp_path / "profile.json")
    assert stored.coverage_benchmark.optional_ab_selections == submitted_ab


def test_server_never_logs_request_body_even_on_invalid_json(tmp_path, monkeypatch):
    secret = "FAKE-SUPER-SECRET-BODY-MARKER-0002"
    httpd, thread = _start_server(tmp_path, "test-key-not-real-intake-0006")

    captured_out = io.StringIO()
    captured_err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)
    monkeypatch.setattr(sys, "stderr", captured_err)

    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
        body = f'{{"not valid json, but contains {secret}'.encode()
        conn.request("POST", "/submit", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 400
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()

    assert secret not in captured_out.getvalue()
    assert secret not in captured_err.getvalue()
