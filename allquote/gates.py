"""Deterministic gate detectors. See PLAN.md Task 5 / docs/GUARDRAILS.md.

A gate is anything that must terminate a browser executor run. Detectors are
pure functions over (page_url, page_text, dom_snapshot) — regex/keyword
only, no LLM call, no browser-use import, fully unit testable with
hand-written strings. This file contains no CAPTCHA-solving,
bot-detection-evasion, user-agent-spoofing, or auth-bypass code — not even a
stub, not even a comment describing one (CLAUDE.md, docs/GUARDRAILS.md).

`detect()` runs every gate kind in a fixed priority order (most safety-
critical first) and returns the first hit. Only a GateHit produced here may
select a gate-kind Status in allquote/executor.py — see that module's
halt-status rule: an LLM-invoked `halt()` can never choose its own status,
only a deterministic GateHit can.

evidence_snippet is returned RAW (not redacted) — redaction happens in the
caller (allquote/browser_ops.py's step hook), which has the profile needed
to call allquote.redact.redact_text. This module never imports allquote.vault
or allquote.redact.
"""

import re
from typing import Literal

from pydantic import BaseModel

GateKind = Literal[
    "captcha_or_bot_check",
    "login_or_account_required",
    "geo_or_region_block",
    "site_unavailable",
    "hard_ineligibility",
    "identity_verification",
    "declaration_attestation",
    "consent_or_terms_required",
    "payment_or_binding_step",
]


class GateHit(BaseModel):
    kind: GateKind
    evidence_snippet: str
    matched_selector_or_pattern: str


_Source = Literal["dom", "text"]

# Reusable axis fragments — generalized along the dimension that actually
# varies between insurers' copy, not a specific sentence. A pattern built
# from a fixed marketing sentence only proves a test can grep for text it
# planted; these are built from the vocabulary/structure that's actually
# stable across rewordings.
_LOGIN_VERB = r"(?:sign in|log in|create|register|set up)"
_LOGIN_NOUN = r"(?:an? )?(?:account|login|profile)"
_INELIG_NEGATION = r"(?:unable|not able|can'?t|cannot|unfortunately)"
_INELIG_OUTCOME = r"(?:quote|rate|coverage|offer)"
_INELIG_CUE = r"(?:not eligible|required? to continue|requirement to continue|does not meet|unable|not able|cannot)"
_VERIFY_WORD = r"(?:verify|verification|confirm your identity)"

# One entry per gate kind, in priority order (first hit wins). Each pattern
# is tagged with which extracted surface it runs against: "dom" is the raw
# HTML/DOM snapshot (for markup-shaped/structural signals — a recaptcha
# widget, a password input, a card-field name/autocomplete — which are
# preferred over prose where they exist, since real sites express these in
# markup, not copy that varies insurer to insurer), "text" is the
# rendered/visible page text (for phrase-based signals a human reading the
# page would notice).
_GATE_PATTERNS: dict[GateKind, list[tuple[_Source, re.Pattern[str]]]] = {
    "captcha_or_bot_check": [
        ("dom", re.compile(r"recaptcha", re.I)),
        ("dom", re.compile(r"hcaptcha", re.I)),
        ("dom", re.compile(r"cf-turnstile", re.I)),
        ("dom", re.compile(r"g-recaptcha", re.I)),
        ("text", re.compile(r"are you a robot", re.I)),
        ("text", re.compile(r"verify you(?:'re| are) human", re.I)),
        ("text", re.compile(r"\bcaptcha\b", re.I)),
    ],
    "login_or_account_required": [
        # verb-then-noun ("create an account", "set up a login") and
        # noun-then-verb ("account required", "profile creation") in either
        # order, rather than one fixed phrase.
        ("text", re.compile(rf"{_LOGIN_VERB}\b[^.]{{0,25}}\b{_LOGIN_NOUN}", re.I)),
        (
            "text",
            re.compile(
                rf"(?<!no )(?<!not )\b(?:account|login|profile)\b[^.]{{0,25}}\b(?:required|needed|{_LOGIN_VERB})",
                re.I,
            ),
        ),
        # structural: a password input gating the flow is a stronger, more
        # reliable signal than any prose paraphrase of "please log in".
        ("dom", re.compile(r"""type=["']password["']""", re.I)),
    ],
    "geo_or_region_block": [
        ("text", re.compile(r"not available in your (?:province|region|area)", re.I)),
        ("text", re.compile(r"outside our service area", re.I)),
        ("text", re.compile(r"we (?:currently )?do not operate in", re.I)),
        ("text", re.compile(r"(?:restricted|limited) to residents of", re.I)),
        ("text", re.compile(r"isn'?t available in your region", re.I)),
        ("text", re.compile(r"not (?:yet )?licensed to (?:sell|operate)", re.I)),
    ],
    "site_unavailable": [
        # keyword net over the vocabulary insurers actually use for outage/
        # downtime copy, not one memorized sentence — an HTTP 5xx status
        # (checked separately in detect(), the more reliable signal) also
        # resolves to this kind regardless of what the page body says.
        ("text", re.compile(r"\bmaintenance\b", re.I)),
        ("text", re.compile(r"\bunavailable\b", re.I)),
        ("text", re.compile(r"\boutage\b", re.I)),
        ("text", re.compile(r"\bupgrad(?:e|es|ed|ing)\b", re.I)),
        ("text", re.compile(r"\bpaused\b", re.I)),
        ("text", re.compile(r"try again later", re.I)),
        ("text", re.compile(r"back (?:soon|shortly)", re.I)),
        ("text", re.compile(r"internal server error", re.I)),
        ("text", re.compile(r"something went wrong", re.I)),
        ("text", re.compile(r"site is currently down", re.I)),
    ],
    "hard_ineligibility": [
        # negation-near-outcome, either order ("unable to ... quote" /
        # "quote ... isn't something we can offer"), plus Ontario licence-
        # class vocabulary (G1/G2) — but only when co-located with an
        # ineligibility/requirement cue, never a bare "G1"/"G2" alone: a
        # licence-class SELECT dropdown listing G1/G2/G as normal options
        # is routine intake, not a gate (see the negative fixture tests).
        ("text", re.compile(rf"{_INELIG_NEGATION}[^.]{{0,40}}{_INELIG_OUTCOME}", re.I)),
        ("text", re.compile(rf"{_INELIG_OUTCOME}[^.]{{0,40}}{_INELIG_NEGATION}", re.I)),
        ("text", re.compile(r"we do not insure", re.I)),
        ("text", re.compile(r"vehicle (?:is )?required to quote", re.I)),
        ("text", re.compile(rf"\bG[12]\b[^.]{{0,60}}{_INELIG_CUE}", re.I)),
        ("text", re.compile(rf"{_INELIG_CUE}[^.]{{0,60}}\bG[12]\b", re.I)),
    ],
    "identity_verification": [
        ("text", re.compile(r"driver'?s licen[cs]e number", re.I)),
        ("text", re.compile(r"\bmvr\b", re.I)),
        ("text", re.compile(r"motor vehicle record", re.I)),
        ("text", re.compile(r"we will pull your driving record", re.I)),
        ("text", re.compile(r"\bsocial insurance number\b|\bsin\b", re.I)),
        ("text", re.compile(r"verify your (?:identity|date of birth)", re.I)),
        ("text", re.compile(r"check your (?:history|driving history|record) with", re.I)),
        ("text", re.compile(r"motor vehicle authorities", re.I)),
        # structural, narrowly scoped: a licence-number field alone is
        # routine intake (every quote form has one — see happy_path_step2
        # and the false-positive test below), so this only fires when that
        # field co-occurs with explicit verification language nearby in the
        # DOM, not on the mere presence of the field.
        (
            "dom",
            re.compile(
                r"""(?:name|id)=["'][^"']*licen[cs]e[-_]?number[^"']*["'][\s\S]{0,300}"""
                rf"""{_VERIFY_WORD}|{_VERIFY_WORD}[\s\S]{{0,300}}"""
                r"""(?:name|id)=["'][^"']*licen[cs]e[-_]?number[^"']*["']""",
                re.I,
            ),
        ),
    ],
    "declaration_attestation": [
        ("text", re.compile(r"i declare that", re.I)),
        ("text", re.compile(r"i (?:hereby )?certify that", re.I)),
        ("text", re.compile(r"i hereby confirm", re.I)),
        ("text", re.compile(r"to the best of my knowledge", re.I)),
        ("text", re.compile(r"\bi attest\b", re.I)),
        ("text", re.compile(r"confirming,? under penalty of insurance fraud", re.I)),
        ("text", re.compile(r"you'?re confirming that", re.I)),
    ],
    "consent_or_terms_required": [
        ("text", re.compile(r"i consent to", re.I)),
        ("text", re.compile(r"i agree to the terms", re.I)),
        ("text", re.compile(r"consent to a credit check", re.I)),
        ("text", re.compile(r"privacy policy consent", re.I)),
        ("text", re.compile(r"authoriz(?:e|ing) (?:us )?to (?:run|obtain|pull)", re.I)),
        ("text", re.compile(r"(?:i have )?read and accept the terms", re.I)),
    ],
    "payment_or_binding_step": [
        # field vocabulary — what a payment form's own labels say — rather
        # than a marketing sentence describing the same step.
        ("text", re.compile(r"credit card", re.I)),
        ("text", re.compile(r"\bcvv\b|\bcvc\b", re.I)),
        ("text", re.compile(r"card number", re.I)),
        ("text", re.compile(r"security code", re.I)),
        ("text", re.compile(r"\bexpiry\b|\bexpiration date\b", re.I)),
        ("text", re.compile(r"billing address", re.I)),
        ("text", re.compile(r"purchase this policy", re.I)),
        ("text", re.compile(r"bind coverage", re.I)),
        # structural: real payment forms name/autocomplete their fields
        # this way regardless of visible copy.
        (
            "dom",
            re.compile(
                r"""(?:name|id|autocomplete)=["'](?:cc-number|cardnumber|card-number|"""
                r"""cc-csc|cc-cvv|cvv|cvc|cc-exp|exp-date)["']""",
                re.I,
            ),
        ),
        (
            "dom",
            re.compile(
                r"""billing[\s\S]{0,200}type=["']tel["']|type=["']tel["'][\s\S]{0,200}billing""",
                re.I,
            ),
        ),
    ],
}

# Priority order: most safety-critical / least ambiguous first. First match
# across all kinds wins.
_PRIORITY: list[GateKind] = [
    "captcha_or_bot_check",
    "login_or_account_required",
    "geo_or_region_block",
    "site_unavailable",
    "hard_ineligibility",
    "identity_verification",
    "declaration_attestation",
    "consent_or_terms_required",
    "payment_or_binding_step",
]


def _snippet(text: str, match: re.Match[str], *, context: int = 40) -> str:
    start = max(0, match.start() - context)
    end = min(len(text), match.end() + context)
    return text[start:end].strip()


def detect(
    page_url: str,
    page_text: str,
    dom_snapshot: str,
    *,
    http_status: int | None = None,
) -> GateHit | None:
    """Run every gate detector in priority order; return the first hit.

    `page_url` is accepted for signature symmetry with future URL-based
    detectors and evidence context, but no current detector keys on it.

    `http_status` is the current page's own response status, when the
    caller has it — a 5xx there is a more reliable site_unavailable signal
    than any prose match, since a maintenance/outage page's exact wording
    is unpredictable but its status code usually isn't. This is distinct
    from allquote.executor.is_transient()'s use of an initial-navigation
    5xx: that one governs the bounded-retry decision for the FIRST page of
    an attempt; this one is a mid-run content signal checked on every step,
    same as the text/dom patterns, and — like every other gate hit — is
    never retried.
    """
    for kind in _PRIORITY:
        if kind == "site_unavailable" and http_status is not None and http_status >= 500:
            return GateHit(
                kind="site_unavailable",
                evidence_snippet=f"HTTP {http_status} response on this page",
                matched_selector_or_pattern="http_status>=500",
            )
        for source, pattern in _GATE_PATTERNS[kind]:
            haystack = dom_snapshot if source == "dom" else page_text
            match = pattern.search(haystack)
            if match is not None:
                return GateHit(
                    kind=kind,
                    evidence_snippet=_snippet(haystack, match),
                    matched_selector_or_pattern=pattern.pattern,
                )
    return None
