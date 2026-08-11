"""Pure unit tests for allquote.gates. No browser, no server, no LLM —
gates.py is pure string-in/string-out, and this file proves it stays that
way (no browser_use import anywhere in gates.py).

Positive test strings here (and the tests/fixtures/*.html gate pages this
file also loads) are deliberately paraphrased away from gates.py's own
pattern list — every one of them was written, then run against the
detectors, then gates.py's patterns were widened to catch the real signal
in the paraphrase. A test whose input text is copy-pasted from the
detector's own pattern only proves the grep works, not that the detector
recognizes the real thing.
"""

from pathlib import Path

from allquote import gates

GATES_SRC = Path("allquote/gates.py").read_text()
FIXTURES_DIR = Path("tests/fixtures")


def _detect(*, text: str = "", dom: str = "") -> gates.GateHit | None:
    return gates.detect("http://example.invalid/quote", text, dom)


def _fixture_text(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


# --- negative cases (benign / must never gate) ------------------------------


def test_no_hit_on_benign_page():
    assert _detect(text="Please select your vehicle make and model.") is None


def test_no_hit_on_privacy_footer_mentioning_credit_and_driving_records():
    # Passive boilerplate disclosure ("as permitted by law, we may...") is
    # not the same as an in-flow, blocking gate — a false gate is worse
    # than a missed one, since it produces a confident wrong terminal
    # status with a screenshot attached.
    hit = _detect(text=_fixture_text("negative_landing_privacy_footer.html"))
    assert hit is None


def test_no_hit_on_quote_form_with_plain_tc_link():
    hit = _detect(text=_fixture_text("negative_quote_form_tc_link.html"))
    assert hit is None


def test_no_hit_on_help_page_about_commercial_ineligibility():
    # Off-topic ineligibility language (about commercial vehicles, not this
    # applicant's own personal-use profile) must not trigger hard_ineligibility.
    hit = _detect(text=_fixture_text("negative_help_page_commercial.html"))
    assert hit is None


# --- positive cases, paraphrased away from the detector's own wording -------


def test_captcha_dom_markup():
    # The recaptcha CSS class is the real-world signal itself (that's how a
    # real widget is identified), not an invented phrase — kept verbatim.
    hit = _detect(dom='<div class="g-recaptcha" data-sitekey="x"></div>')
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_captcha_fixture_file():
    hit = _detect(text=_fixture_text("captcha.html"), dom=_fixture_text("captcha.html"))
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_login_or_account_required_password_field():
    hit = _detect(dom='<input type="password" name="pw">')
    assert hit is not None
    assert hit.kind == "login_or_account_required"


def test_login_or_account_required_paraphrase():
    hit = _detect(text="You'll need to set up a login before we can show you pricing.")
    assert hit is not None
    assert hit.kind == "login_or_account_required"


def test_geo_or_region_block_paraphrase():
    hit = _detect(text="We're not yet licensed to sell this product where you live.")
    assert hit is not None
    assert hit.kind == "geo_or_region_block"


def test_site_unavailable_fixture_file():
    hit = _detect(text=_fixture_text("maintenance.html"))
    assert hit is not None
    assert hit.kind == "site_unavailable"


def test_hard_ineligibility_fixture_file():
    hit = _detect(text=_fixture_text("ineligible.html"))
    assert hit is not None
    assert hit.kind == "hard_ineligibility"
    assert "licence is required" in hit.evidence_snippet.lower()


def test_identity_verification_fixture_file():
    hit = _detect(text=_fixture_text("identity_gate.html"))
    assert hit is not None
    assert hit.kind == "identity_verification"


def test_declaration_attestation_paraphrase():
    hit = _detect(
        text="Submitting this application means you're confirming, under "
        "penalty of insurance fraud, that every answer above is accurate "
        "and complete."
    )
    assert hit is not None
    assert hit.kind == "declaration_attestation"


def test_consent_or_terms_required_fixture_file():
    hit = _detect(text=_fixture_text("consent_wall.html"))
    assert hit is not None
    assert hit.kind == "consent_or_terms_required"


def test_payment_or_binding_step_paraphrase():
    hit = _detect(
        text="Enter your Visa or Mastercard details below, including the "
        "3-digit security code on the back, to activate coverage today."
    )
    assert hit is not None
    assert hit.kind == "payment_or_binding_step"


def test_priority_captcha_wins_over_consent():
    # A page that has both a captcha and consent language should be
    # classified as captcha_or_bot_check — the higher-priority, more
    # safety-critical gate always wins over a lower-priority one.
    hit = _detect(
        text="By continuing you authorize us to run a credit check.",
        dom='<div class="g-recaptcha"></div>',
    )
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_priority_ineligibility_wins_over_identity_verification():
    hit = _detect(
        text="A G2 or full G licence is required to continue. We aren't "
        "able to provide a rate for a G1 licence at this time, and as part "
        "of standard underwriting we routinely check your history with "
        "provincial motor vehicle authorities."
    )
    assert hit is not None
    assert hit.kind == "hard_ineligibility"


def test_gate_hit_is_pydantic_model_with_expected_fields():
    hit = _detect(text=_fixture_text("ineligible.html"))
    assert hit is not None
    assert hit.matched_selector_or_pattern
    assert hit.evidence_snippet


def test_evidence_snippet_is_not_pre_redacted():
    # gates.py does not redact — that's the caller's job (browser_ops.py's
    # step hook, which has the profile needed to call redact_text). The
    # trigger phrase (not a raw sensitive value) should come back verbatim.
    hit = _detect(text=_fixture_text("identity_gate.html"))
    assert hit is not None
    assert "motor vehicle authorities" in hit.evidence_snippet.lower()


# --- generalization regression tests: novel wording, not the paraphrase ----
# already used above, plus the structural (DOM/HTTP-status) signals and the
# false-positive guards they require.


def test_login_generalizes_to_a_third_unseen_sentence():
    hit = _detect(
        text="A member profile is needed before we can display rates -- "
        "please register now."
    )
    assert hit is not None
    assert hit.kind == "login_or_account_required"


def test_login_does_not_fire_on_no_account_needed():
    # "No account needed" is a common, honest landing-page claim — the
    # opposite of a login gate. A pattern that only checks proximity
    # without checking for the negation would false-positive here.
    hit = _detect(text="Get a quote in minutes. No account needed.")
    assert hit is None


def test_geo_block_generalizes_to_limited_to_phrasing():
    hit = _detect(
        text="Coverage through this portal is currently limited to "
        "residents of Ontario and Alberta only."
    )
    assert hit is not None
    assert hit.kind == "geo_or_region_block"


def test_site_unavailable_generalizes_to_outage_wording():
    hit = _detect(
        text="We are experiencing a temporary outage while our team "
        "resolves an issue. Please try again later."
    )
    assert hit is not None
    assert hit.kind == "site_unavailable"


def test_site_unavailable_http_status_signal():
    hit = _detect(text="Nothing unusual here.", dom="<html></html>")
    assert hit is None
    hit = gates.detect("http://x", "Nothing unusual here.", "<html></html>", http_status=503)
    assert hit is not None
    assert hit.kind == "site_unavailable"


def test_site_unavailable_http_status_4xx_does_not_fire():
    hit = gates.detect("http://x", "Not found.", "<html></html>", http_status=404)
    assert hit is None


def test_payment_generalizes_to_field_vocabulary_sentence():
    hit = _detect(
        text="Please provide the card number, expiry date, and the 3-digit "
        "code on the back to activate your policy."
    )
    assert hit is not None
    assert hit.kind == "payment_or_binding_step"


def test_payment_structural_card_field():
    hit = _detect(dom='<input name="cc-number" type="text">')
    assert hit is not None
    assert hit.kind == "payment_or_binding_step"


def test_hard_ineligibility_g_class_generalizes_with_requirement_wording():
    hit = _detect(
        text="Unfortunately a G2 licence does not meet the requirement to "
        "continue with this online application."
    )
    assert hit is not None
    assert hit.kind == "hard_ineligibility"


def test_hard_ineligibility_bare_g_class_in_dropdown_does_not_fire():
    # A licence-class SELECT listing G1/G2/G as normal options is routine
    # intake, not an ineligibility statement — bare "G1"/"G2" alone must
    # never be sufficient on its own.
    dropdown = (
        '<select name="licence_class"><option>G1</option>'
        "<option>G2</option><option>G</option></select> "
        "Select your licence class"
    )
    hit = _detect(text=dropdown, dom=dropdown)
    assert hit is None


def test_identity_verification_structural_licence_field_near_verify_language():
    dom = (
        '<label>Verify your identity</label>'
        '<input id="licence_number" name="licence_number" type="text">'
    )
    hit = _detect(dom=dom)
    assert hit is not None
    assert hit.kind == "identity_verification"


def test_identity_verification_does_not_fire_on_routine_licence_field():
    # A licence-number field is a normal, expected part of every quote
    # form's intake (see docs/GUARDRAILS.md — filling it in is routine, not
    # itself a checkpoint). Only co-occurrence with explicit verification
    # language should fire this gate, never the bare field.
    hit = _detect(text=_fixture_text("happy_path_step2.html"), dom=_fixture_text("happy_path_step2.html"))
    assert hit is None


def test_gates_module_has_no_browser_use_import():
    assert "browser_use" not in GATES_SRC


def test_gates_module_has_no_captcha_solving_code():
    banned_terms = [
        "solve_captcha",
        "captcha_solver",
        "2captcha",
        "anti-captcha",
        "bypass_captcha",
        "captcha_bypass",
        "audio_challenge",
    ]
    lowered = GATES_SRC.lower()
    for term in banned_terms:
        assert term not in lowered, f"gates.py must not contain {term!r}"
