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


def _detect(
    *,
    text: str = "",
    dom: str = "",
    captcha_structural_hits: list[str] | None = None,
    blocking_control_present: bool = False,
) -> gates.GateHit | None:
    return gates.detect(
        "http://example.invalid/quote",
        text,
        dom,
        captcha_structural_hits=captcha_structural_hits,
        blocking_control_present=blocking_control_present,
    )


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


def test_captcha_structural_hit_fires():
    # captcha_structural_hits carries plain descriptions of elements a live
    # page.evaluate already confirmed are actually rendered (see
    # allquote.browser_ops.scan_captcha_structural_hits) — gates.py itself
    # never regexes dom_snapshot for recaptcha/hcaptcha/turnstile markup.
    hit = _detect(captcha_structural_hits=["visible iframe: recaptcha/api2/anchor"])
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"
    assert hit.evidence_snippet == "visible iframe: recaptcha/api2/anchor"


def test_captcha_raw_dom_class_name_alone_does_not_fire():
    # This is the exact false-positive shape the fix removes: a class name
    # or script reference sitting in raw dom_snapshot with no confirmation
    # it's actually rendered must never be enough on its own.
    hit = _detect(dom='<div class="g-recaptcha" data-sitekey="x"></div>')
    assert hit is None


def test_captcha_script_src_in_dom_does_not_fire():
    # The actual bug from the first live run: a <script> tag loading the
    # reCAPTCHA v3 library is not a challenge.
    hit = _detect(
        dom='<script src="https://www.gstatic.com/recaptcha/releases/w_x/recaptcha__en.js" '
        'charset="utf-8"></script>'
    )
    assert hit is None


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
        "and complete.",
        blocking_control_present=True,
    )
    assert hit is not None
    assert hit.kind == "declaration_attestation"


def test_consent_or_terms_required_fixture_file():
    hit = _detect(text=_fixture_text("consent_wall.html"), blocking_control_present=True)
    assert hit is not None
    assert hit.kind == "consent_or_terms_required"


def test_payment_or_binding_step_paraphrase():
    hit = _detect(
        text="Enter your Visa or Mastercard details below, including the "
        "3-digit security code on the back, to activate coverage today.",
        blocking_control_present=True,
    )
    assert hit is not None
    assert hit.kind == "payment_or_binding_step"


def test_priority_captcha_wins_over_consent():
    # A page that has both a captcha and consent language should be
    # classified as captcha_or_bot_check — the higher-priority, more
    # safety-critical gate always wins over a lower-priority one.
    hit = _detect(
        text="By continuing you authorize us to run a credit check.",
        captcha_structural_hits=["visible element: .g-recaptcha"],
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
        "code on the back to activate your policy.",
        blocking_control_present=True,
    )
    assert hit is not None
    assert hit.kind == "payment_or_binding_step"


def test_payment_structural_card_field():
    hit = _detect(dom='<input name="cc-number" type="text">', blocking_control_present=True)
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


# --- consent/declaration require a blocking control, not just prose --------


def test_consent_prose_without_blocking_control_does_not_fire():
    # The Tangerine-promo-footer shape (footer scoping is a separate,
    # browser_ops-level fix — this is the second half: even prose that DID
    # make it into the scanned text must not fire without an accompanying
    # unchecked checkbox or required input).
    hit = _detect(text="By continuing you authorize us to run a credit check.")
    assert hit is None


def test_consent_prose_with_blocking_control_fires():
    hit = _detect(
        text="By continuing you authorize us to run a credit check.",
        blocking_control_present=True,
    )
    assert hit is not None
    assert hit.kind == "consent_or_terms_required"


def test_declaration_prose_without_blocking_control_does_not_fire():
    hit = _detect(text="To the best of my knowledge, all of the above is accurate.")
    assert hit is None


def test_blocking_control_requirement_does_not_affect_other_kinds():
    # The requirement is scoped to consent_or_terms_required and
    # declaration_attestation specifically -- every other kind must fire
    # exactly as before regardless of blocking_control_present.
    hit = _detect(text="We're not yet licensed to sell this product where you live.")
    assert hit is not None
    assert hit.kind == "geo_or_region_block"


# --- matched_text: the raw fragment used to scroll evidence into view ------


def test_matched_text_is_raw_unpadded_fragment():
    hit = _detect(text="Please provide your driver's licence number to continue.")
    assert hit is not None
    assert hit.matched_text.lower() == "driver's licence number"
    # evidence_snippet is padded with surrounding context; matched_text is not.
    assert len(hit.matched_text) <= len(hit.evidence_snippet)


def test_matched_text_for_dom_hit_equals_its_plain_label():
    hit = _detect(dom='<input type="password" name="pw">')
    assert hit is not None
    assert hit.matched_text == hit.evidence_snippet == "password input field present on the page"


def test_matched_text_for_captcha_structural_hit_equals_its_description():
    hit = _detect(captcha_structural_hits=["visible iframe: recaptcha/api2/anchor"])
    assert hit is not None
    assert hit.matched_text == "visible iframe: recaptcha/api2/anchor"


# --- evidence_snippet readability (raw-HTML-slice regression) ---------------


def test_dom_structural_hit_snippet_is_plain_not_html_slice():
    hit = _detect(dom='<input type="password" name="pw">')
    assert hit is not None
    assert "<" not in hit.evidence_snippet
    assert hit.evidence_snippet == "password input field present on the page"


def test_evidence_snippet_capped_at_200_chars():
    filler = "lorem ipsum dolor sit amet " * 6
    long_text = f"{filler}we are unable to provide a quote for this profile {filler}"
    hit = _detect(text=long_text)
    assert hit is not None
    assert hit.kind == "hard_ineligibility"
    assert len(hit.evidence_snippet) <= 200


# --- bot-wall detection: hard_ineligibility misclassification fix ----------
#
# Root cause (confirmed against the real Task 7 Phase 2 probe evidence at
# data/evidence/98a89c129648/attempt-1/ and data/evidence/4ed2deb6e253/attempt-1/):
# hard_ineligibility's negation-near-outcome pattern used a bare "rate"
# alternative with no \b word boundary, so "You are unable to access
# rates.ca" matched "unable ... rate" as a substring of the SITE'S OWN
# DOMAIN NAME, not any real ineligibility language. Both fixtures below are
# the literal wall text from those two captures, not a paraphrase — this is
# a regression test for an incident that actually happened, not a
# hypothetical.


def test_bot_wall_cloudflare_block_fixture_is_blocked_not_ineligible():
    hit = _detect(text=_fixture_text("bot_wall_cloudflare_rates_ca.html"))
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_bot_wall_surex_antibot_banner_fixture_is_blocked():
    # The real Surex probe run only reached `blocked` via a voluntary LLM
    # halt (no independent gate match) — this proves a deterministic
    # detector hit is now reachable for the same page text, which is
    # stronger evidence than the model naming it.
    hit = _detect(text=_fixture_text("bot_wall_surex_antibot.html"))
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_bot_wall_generalizes_to_unseen_cloudflare_challenge_wording():
    # Different real-world Cloudflare challenge copy from the two captures
    # above (the "checking your browser" interstitial, not the "you have
    # been blocked" wall) — proves the detector isn't just grepping the two
    # literal captures.
    hit = _detect(
        text="Checking your browser before accessing example.com. "
        "This process is automatic. Ray ID: 8f3a9c1b2d4e5f6a Performance & "
        "security by Cloudflare"
    )
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_genuine_ineligibility_fixture_still_returns_ineligible_not_blocked():
    # The existing hard_ineligibility fixture (real product-rule rejection
    # language) must be unaffected by the bot-wall additions or the \b fix.
    hit = _detect(text=_fixture_text("ineligible.html"))
    assert hit is not None
    assert hit.kind == "hard_ineligibility"


def test_page_with_both_ineligibility_and_bot_wall_phrasing_returns_blocked():
    # Ordering proof: captcha_or_bot_check is priority-first, so when a page
    # contains both an ineligibility phrase and bot-wall phrasing, the wall
    # wins — an access-control wall is a fact about the page; an
    # ineligibility is a fact about the profile, and we never got far enough
    # for a profile judgement to have occurred.
    hit = _detect(
        text="A G2 or full G licence is required to continue. We aren't "
        "able to provide a rate for a G1 licence at this time. Sorry, you "
        "have been blocked: this website is using a security service to "
        "protect itself."
    )
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_ineligibility_outcome_word_boundary_does_not_match_domain_substring():
    # Isolates the root-cause fix from the new bot-wall patterns: on its
    # own, with none of the new bot-wall vocabulary present, "unable to
    # access rates.ca" must not fire hard_ineligibility (or anything else)
    # via a bare, unbounded "rate" substring match.
    hit = _detect(text="You are unable to access rates.ca right now, please try again.")
    assert hit is None


def test_ineligibility_outcome_word_boundary_still_matches_whole_word():
    # The \b fix must not remove genuine whole-word matches.
    hit = _detect(text="Unfortunately we are unable to provide a rate for this vehicle.")
    assert hit is not None
    assert hit.kind == "hard_ineligibility"


# --- Fix A: human-check phrasing miss (belairdirect live probe) -----------


def test_belairdirect_human_check_fixture_fires_captcha_or_bot_check():
    # Literal captured text from data/evidence/13dfdbf3211c/attempt-1/ — the
    # live run this detector missed. "confirm you are human" and "verifies
    # that you are not a bot" were both uncovered by the old
    # "verify you're/you are human"-only pattern.
    hit = _detect(text=_fixture_text("bot_wall_belairdirect_human_check.html"))
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_human_check_generalizes_to_prove_variant():
    # Different verb than either the original pattern or the literal
    # belairdirect capture — proves the fix isn't just grepping that one page.
    hit = _detect(text="Before you continue, prove you are human by completing the puzzle below.")
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


def test_human_check_still_fires_on_original_verify_wording():
    # Regression: the pattern this replaces must keep working.
    hit = _detect(text="Please verify you're human before we show your quote.")
    assert hit is not None
    assert hit.kind == "captcha_or_bot_check"


# --- Fix B: payment_or_binding_step requires a blocking control -----------


def test_td_credit_eligibility_marketing_fixture_does_not_fire():
    # Literal captured text from data/evidence/2da8222b1aec/attempt-1/ — a
    # plain TD Insurance homepage with existing-customer discount-eligibility
    # copy naming "personal credit card" / "line of credit". No payment form
    # anywhere on the page, so blocking_control_present is (correctly) False.
    hit = _detect(text=_fixture_text("negative_td_credit_eligibility_marketing.html"))
    assert hit is None


def test_payment_prose_without_blocking_control_does_not_fire():
    hit = _detect(text="Enter your Visa or Mastercard details below, including the 3-digit security code.")
    assert hit is None


def test_payment_prose_with_blocking_control_fires():
    hit = _detect(
        text="Enter your Visa or Mastercard details below, including the 3-digit security code.",
        blocking_control_present=True,
    )
    assert hit is not None
    assert hit.kind == "payment_or_binding_step"


def test_payment_structural_card_field_requires_blocking_control():
    # The dom-pattern path is subject to the same rule now: a bare card-field
    # attribute with no caller-confirmed required input does not fire.
    hit = _detect(dom='<input name="cc-number" type="text">')
    assert hit is None
    hit = _detect(dom='<input name="cc-number" type="text">', blocking_control_present=True)
    assert hit is not None
    assert hit.kind == "payment_or_binding_step"


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
