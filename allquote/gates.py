"""Deterministic gate detectors. See PLAN.md Task 5 / docs/GUARDRAILS.md.

A gate is anything that must terminate a browser executor run. Detectors are
pure functions over (page_url, page_text, dom_snapshot, captcha_structural_hits)
— regex/keyword only, no LLM call, no browser-use import, fully unit testable
with hand-written strings. This file contains no CAPTCHA-solving,
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

Surface discipline: "text" patterns run ONLY against `page_text` (rendered
innerText — hidden/display:none content, script bodies, comments, and JSON
blobs are never part of it). "dom" patterns run ONLY against `dom_snapshot`
(raw outerHTML) and are reserved for markup-shaped/structural signals (an
input's type/name/autocomplete attribute) that are meaningless as prose. A
generic keyword substring search against raw HTML is neither of these — it
matches script `src` attributes, JSON payloads, and comments as readily as
real markup, which is exactly what produced a captcha_or_bot_check false
positive against a page that only loaded the reCAPTCHA v3 library (a
`<script src=".../recaptcha__en.js">` tag, never a presented challenge).
CAPTCHA detection therefore does not use a "dom" pattern at all: it is driven
by `captcha_structural_hits`, a list of plain-text descriptions of elements
`allquote.browser_ops` has already confirmed are actually visible on the live
page (non-zero bounding rect) via the same `page.evaluate` path used for
evidence-screenshot redaction boxes — see that module's `_CAPTCHA_SCAN_JS`.
This keeps gates.py itself free of any browser dependency: it just consumes
strings/lists that a caller with real page access computed and handed in.

Scoping discipline: `page_text` must be the caller's ACTIVE-REGION text (the
form/main content the run is currently on), never whole-page text. Footer
boilerplate, promo blocks, and unrelated fine print live in `page_text` just
as readily as a real in-flow gate does if the caller hands over
`document.body.innerText` wholesale — that produced a real false positive
(Tangerine Bank credit-card promo fine print in a footer matching
consent_or_terms_required). `allquote.browser_ops` computes this scoped text
live (nearest common container of the visible, in-viewport interactive
controls, excluding <footer>/<nav>/[role=contentinfo]/promo classes) before
calling `detect()` — this module has no way to enforce that itself, since it
never sees a live DOM, only whatever string it's handed.

`consent_or_terms_required` and `declaration_attestation` additionally
require `blocking_control_present=True` — prose alone ("we may run a credit
check" in a privacy notice) is disclosure, not a gate; the caller confirms
an actual unchecked checkbox or required input sits in the same active-region
container before these two kinds may fire at all.
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
    # The raw matched fragment (a regex's match.group(0), or the same plain
    # label as evidence_snippet for a structural/captcha hit that has no
    # underlying page prose). Unlike evidence_snippet, this is never padded
    # with surrounding context or truncated — it exists so a caller with
    # live page access (allquote.browser_ops) can search for this exact
    # short string as real page text and scroll it into view before
    # evidence capture, rather than the wider, harder-to-locate snippet.
    matched_text: str


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
# is a (surface, pattern, dom_label) triple: "text" runs against page_text
# (rendered/visible copy — for phrase-based signals a human reading the page
# would notice); "dom" runs against dom_snapshot (raw HTML — reserved for
# narrowly-scoped structural/attribute signals, preferred over prose where
# they exist since real sites express these in markup, not copy that varies
# insurer to insurer). `dom_label` is the plain-language description used as
# the evidence_snippet for a "dom" hit instead of a raw HTML slice (see
# module docstring and `detect()`) — it is unused (None) for "text" entries,
# which instead get a real surrounding-text snippet.
_GATE_PATTERNS: dict[GateKind, list[tuple[_Source, re.Pattern[str], str | None]]] = {
    "captcha_or_bot_check": [
        # Structural detection (a rendered widget/iframe) is handled entirely
        # via `captcha_structural_hits` in detect() — never a raw dom_snapshot
        # regex, which cannot tell a presented challenge from a loaded
        # library/script reference. Only visible-text phrasing lives here.
        ("text", re.compile(r"are you a robot", re.I), None),
        ("text", re.compile(r"verify you(?:'re| are) human", re.I), None),
        ("text", re.compile(r"unusual traffic from your (?:network|computer)", re.I), None),
        ("text", re.compile(r"\bcaptcha\b", re.I), None),
    ],
    "login_or_account_required": [
        # verb-then-noun ("create an account", "set up a login") and
        # noun-then-verb ("account required", "profile creation") in either
        # order, rather than one fixed phrase.
        ("text", re.compile(rf"{_LOGIN_VERB}\b[^.]{{0,25}}\b{_LOGIN_NOUN}", re.I), None),
        (
            "text",
            re.compile(
                rf"(?<!no )(?<!not )\b(?:account|login|profile)\b[^.]{{0,25}}\b(?:required|needed|{_LOGIN_VERB})",
                re.I,
            ),
            None,
        ),
        # structural: a password input gating the flow is a stronger, more
        # reliable signal than any prose paraphrase of "please log in".
        (
            "dom",
            re.compile(r"""type=["']password["']""", re.I),
            "password input field present on the page",
        ),
    ],
    "geo_or_region_block": [
        ("text", re.compile(r"not available in your (?:province|region|area)", re.I), None),
        ("text", re.compile(r"outside our service area", re.I), None),
        ("text", re.compile(r"we (?:currently )?do not operate in", re.I), None),
        ("text", re.compile(r"(?:restricted|limited) to residents of", re.I), None),
        ("text", re.compile(r"isn'?t available in your region", re.I), None),
        ("text", re.compile(r"not (?:yet )?licensed to (?:sell|operate)", re.I), None),
    ],
    "site_unavailable": [
        # keyword net over the vocabulary insurers actually use for outage/
        # downtime copy, not one memorized sentence — an HTTP 5xx status
        # (checked separately in detect(), the more reliable signal) also
        # resolves to this kind regardless of what the page body says.
        ("text", re.compile(r"\bmaintenance\b", re.I), None),
        ("text", re.compile(r"\bunavailable\b", re.I), None),
        ("text", re.compile(r"\boutage\b", re.I), None),
        ("text", re.compile(r"\bupgrad(?:e|es|ed|ing)\b", re.I), None),
        ("text", re.compile(r"\bpaused\b", re.I), None),
        ("text", re.compile(r"try again later", re.I), None),
        ("text", re.compile(r"back (?:soon|shortly)", re.I), None),
        ("text", re.compile(r"internal server error", re.I), None),
        ("text", re.compile(r"something went wrong", re.I), None),
        ("text", re.compile(r"site is currently down", re.I), None),
    ],
    "hard_ineligibility": [
        # negation-near-outcome, either order ("unable to ... quote" /
        # "quote ... isn't something we can offer"), plus Ontario licence-
        # class vocabulary (G1/G2) — but only when co-located with an
        # ineligibility/requirement cue, never a bare "G1"/"G2" alone: a
        # licence-class SELECT dropdown listing G1/G2/G as normal options
        # is routine intake, not a gate (see the negative fixture tests).
        ("text", re.compile(rf"{_INELIG_NEGATION}[^.]{{0,40}}{_INELIG_OUTCOME}", re.I), None),
        ("text", re.compile(rf"{_INELIG_OUTCOME}[^.]{{0,40}}{_INELIG_NEGATION}", re.I), None),
        ("text", re.compile(r"we do not insure", re.I), None),
        ("text", re.compile(r"vehicle (?:is )?required to quote", re.I), None),
        ("text", re.compile(rf"\bG[12]\b[^.]{{0,60}}{_INELIG_CUE}", re.I), None),
        ("text", re.compile(rf"{_INELIG_CUE}[^.]{{0,60}}\bG[12]\b", re.I), None),
    ],
    "identity_verification": [
        ("text", re.compile(r"driver'?s licen[cs]e number", re.I), None),
        ("text", re.compile(r"\bmvr\b", re.I), None),
        ("text", re.compile(r"motor vehicle record", re.I), None),
        ("text", re.compile(r"we will pull your driving record", re.I), None),
        ("text", re.compile(r"\bsocial insurance number\b|\bsin\b", re.I), None),
        ("text", re.compile(r"verify your (?:identity|date of birth)", re.I), None),
        ("text", re.compile(r"check your (?:history|driving history|record) with", re.I), None),
        ("text", re.compile(r"motor vehicle authorities", re.I), None),
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
            "licence-number field co-located with identity-verification language",
        ),
    ],
    "declaration_attestation": [
        ("text", re.compile(r"i declare that", re.I), None),
        ("text", re.compile(r"i (?:hereby )?certify that", re.I), None),
        ("text", re.compile(r"i hereby confirm", re.I), None),
        ("text", re.compile(r"to the best of my knowledge", re.I), None),
        ("text", re.compile(r"\bi attest\b", re.I), None),
        ("text", re.compile(r"confirming,? under penalty of insurance fraud", re.I), None),
        ("text", re.compile(r"you'?re confirming that", re.I), None),
    ],
    "consent_or_terms_required": [
        ("text", re.compile(r"i consent to", re.I), None),
        ("text", re.compile(r"i agree to the terms", re.I), None),
        ("text", re.compile(r"consent to a credit check", re.I), None),
        ("text", re.compile(r"privacy policy consent", re.I), None),
        ("text", re.compile(r"authoriz(?:e|ing) (?:us )?to (?:run|obtain|pull)", re.I), None),
        ("text", re.compile(r"(?:i have )?read and accept the terms", re.I), None),
    ],
    "payment_or_binding_step": [
        # field vocabulary — what a payment form's own labels say — rather
        # than a marketing sentence describing the same step.
        ("text", re.compile(r"credit card", re.I), None),
        ("text", re.compile(r"\bcvv\b|\bcvc\b", re.I), None),
        ("text", re.compile(r"card number", re.I), None),
        ("text", re.compile(r"security code", re.I), None),
        ("text", re.compile(r"\bexpiry\b|\bexpiration date\b", re.I), None),
        ("text", re.compile(r"billing address", re.I), None),
        ("text", re.compile(r"purchase this policy", re.I), None),
        ("text", re.compile(r"bind coverage", re.I), None),
        # structural: real payment forms name/autocomplete their fields
        # this way regardless of visible copy.
        (
            "dom",
            re.compile(
                r"""(?:name|id|autocomplete)=["'](?:cc-number|cardnumber|card-number|"""
                r"""cc-csc|cc-cvv|cvv|cvc|cc-exp|exp-date)["']""",
                re.I,
            ),
            "payment card field present (card number, CVV, or expiry)",
        ),
        (
            "dom",
            re.compile(
                r"""billing[\s\S]{0,200}type=["']tel["']|type=["']tel["'][\s\S]{0,200}billing""",
                re.I,
            ),
            "billing address field co-located with a phone-type input",
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

_MAX_SNIPPET_LEN = 200


def _snippet(text: str, match: re.Match[str], *, context: int = 90) -> str:
    start = max(0, match.start() - context)
    end = min(len(text), match.end() + context)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if len(snippet) > _MAX_SNIPPET_LEN:
        snippet = snippet[: _MAX_SNIPPET_LEN - 1].rstrip() + "…"
    return snippet


_BLOCKING_CONTROL_REQUIRED: frozenset[GateKind] = frozenset({"consent_or_terms_required", "declaration_attestation"})


def detect(
    page_url: str,
    page_text: str,
    dom_snapshot: str,
    *,
    http_status: int | None = None,
    captcha_structural_hits: list[str] | None = None,
    blocking_control_present: bool = False,
) -> GateHit | None:
    """Run every gate detector in priority order; return the first hit.

    `page_url` is accepted for signature symmetry with future URL-based
    detectors and evidence context, but no current detector keys on it.

    `page_text` MUST already be scoped to the active region, not the whole
    page — see the module docstring's "Scoping discipline" section.

    `http_status` is the current page's own response status, when the
    caller has it — a 5xx there is a more reliable site_unavailable signal
    than any prose match, since a maintenance/outage page's exact wording
    is unpredictable but its status code usually isn't. This is distinct
    from allquote.executor.is_transient()'s use of an initial-navigation
    5xx: that one governs the bounded-retry decision for the FIRST page of
    an attempt; this one is a mid-run content signal checked on every step,
    same as the text/dom patterns, and — like every other gate hit — is
    never retried.

    `captcha_structural_hits` is a list of plain-text descriptions (e.g.
    "visible iframe: recaptcha/api2/anchor") of CAPTCHA-shaped elements the
    caller has already confirmed are actually rendered on the live page —
    see the module docstring. An empty/absent list means no such element was
    found; it never means "not checked", since the caller always runs the
    scan when it has real page access (allquote.browser_ops).

    `blocking_control_present` is whether the caller found an unchecked
    checkbox or a required input inside the same active-region container as
    `page_text` — required for consent_or_terms_required and
    declaration_attestation to fire at all, regardless of which prose
    pattern would otherwise match (see module docstring).
    """
    captcha_structural_hits = captcha_structural_hits or []
    for kind in _PRIORITY:
        if kind == "site_unavailable" and http_status is not None and http_status >= 500:
            snippet = f"HTTP {http_status} response on this page"
            return GateHit(
                kind="site_unavailable",
                evidence_snippet=snippet,
                matched_selector_or_pattern="http_status>=500",
                matched_text=snippet,
            )
        if kind == "captcha_or_bot_check" and captcha_structural_hits:
            hit_description = captcha_structural_hits[0]
            return GateHit(
                kind="captcha_or_bot_check",
                evidence_snippet=hit_description[:_MAX_SNIPPET_LEN],
                matched_selector_or_pattern=hit_description,
                matched_text=hit_description,
            )
        if kind in _BLOCKING_CONTROL_REQUIRED and not blocking_control_present:
            # Prose without an actual blocking control nearby is disclosure
            # text, not a gate — skip this kind's patterns entirely rather
            # than firing on whichever phrase happens to match.
            continue
        for source, pattern, dom_label in _GATE_PATTERNS[kind]:
            haystack = dom_snapshot if source == "dom" else page_text
            match = pattern.search(haystack)
            if match is not None:
                # A "dom" hit is structural markup, not prose — record what
                # was matched in plain language rather than an HTML slice
                # (which can be an unreadable, arbitrarily-cut fragment of a
                # long attribute value or wide match window).
                snippet = dom_label if source == "dom" else _snippet(haystack, match)
                matched_text = dom_label if source == "dom" else match.group(0).strip()
                return GateHit(
                    kind=kind,
                    evidence_snippet=snippet,
                    matched_selector_or_pattern=pattern.pattern,
                    matched_text=matched_text,
                )
    return None
