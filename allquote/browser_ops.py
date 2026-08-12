"""browser-use custom actions + observation hooks. See PLAN.md Task 5.

Three integration points with browser-use 0.13.7, each grounded in what the
library actually does (confirmed by reading its source and, for the
sensitive_data wiring, by constructing a real Agent with a stub LLM and zero
API calls — see tests/test_browser_ops.py):

1. Sensitive values never reach the LLM as text. `fill_sensitive` resolves a
   value from the vault and writes it into the SAME mutable `sensitive_data`
   dict object passed to `Agent(sensitive_data=...)` — browser-use's own
   `MessageManager._filter_sensitive_data` (agent/message_manager/service.py)
   then substring-redacts that value out of every outgoing LLM message and
   out of serialized history, generically, for free. `-webkit-text-security`
   masks the SEPARATE vision channel (the per-step screenshot browser-use
   sends the LLM when use_vision=True is pixels, not text — sensitive_data
   filtering does not touch it).
2. Gate detection is deterministic, not LLM-decided. `make_step_hook` runs
   `allquote.gates.detect()` on every step using stable Playwright/CDP APIs
   (`scan_active_region`'s `page.evaluate`, `page.evaluate("() =>
   document.documentElement.outerHTML")` — this Page class requires arrow-
   function-format JS, confirmed by running it) — never browser-use's internal
   DOM serializer/`llm_representation()`, which is an interactive-elements
   listing for the model's own action loop, not a page-text transcript, and
   is undocumented, version-specific surface this module has no business
   coupling to. On a hit it calls `agent.stop()` directly; the LLM never
   decides to proceed past a gate. Detection is also skipped entirely for a
   step whose `document.readyState !== "complete"` — a mid-load DOM (a modal
   not yet attached, a script tag not yet run, a partially-parsed body) is a
   false-positive factory for every detector, not just CAPTCHA, and the next
   step re-checks once the page has actually settled. Text detectors never
   see `document.body.innerText` — `scan_active_region` scopes them to the
   nearest container of the visible, in-viewport interactive controls
   (excluding footer/nav/promo regions) and also reports whether an unchecked
   checkbox or required input sits in that same container, which
   consent_or_terms_required/declaration_attestation additionally require
   before firing (see allquote/gates.py's docstring — this is what stops
   footer promo fine print, e.g. an unrelated credit-card offer's "consent to
   a credit check", from ever being read as an in-flow consent gate). CAPTCHA
   detection additionally runs `_CAPTCHA_SCAN_JS`, a third `page.evaluate`
   call that requires BOTH a visible iframe (recaptcha/hcaptcha/turnstile
   challenge src) AND a rendered size consistent with an actual widget — this
   is what separates a real v2 checkbox (~304x78) from reCAPTCHA v3's
   mandatory `.grecaptcha-badge` attribution badge (~70x60,
   `data-size="invisible"`), which is present on the majority of commercial
   sites and is not a challenge. `_BOX_SCAN_JS` below uses the same
   non-zero-`getBoundingClientRect` visibility primitive for redaction boxes.
   This is what lets `gates.detect()` tell a presented challenge apart from a
   merely-loaded reCAPTCHA library (see allquote/gates.py's docstring);
   gates.py itself never regexes dom_snapshot for CAPTCHA markup, nor does it
   ever see unscoped page text.
3. The raw screenshot never touches disk. `capture_evidence_screenshot`
   captures to bytes in memory, computes redaction boxes from BOTH input
   values and rendered text (a quote-summary page can echo a sensitive value
   as plain text, which no input-value scan or CSS trick would catch), and
   hands bytes straight to `redact.redact_image` — there is no code path
   that writes the unredacted bytes anywhere. The screenshot is a viewport
   capture, so a text-based gate hit can be correctly scoped (point 2) and
   still be below the fold — `scroll_text_into_view` (called by
   allquote/executor.py before capture) is a best-effort attempt to find a
   GateHit's `matched_text` as live page text and scroll it on screen first;
   it returns False rather than raising when it can't (e.g. a structural
   hit's plain-language label was never real page prose), so the caller can
   say the artifact may not show it instead of implying that it does.
"""

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from browser_use import BrowserSession, Tools
from browser_use.agent.views import ActionResult
from browser_use.browser.events import TypeTextEvent

from allquote import gates, vault
from allquote.redact import SHAPE_PATTERNS, iter_profile_refs, redact_image, redact_text
from allquote.schemas import IntakeProfile

# --- fill_sensitive / fill_public / halt ------------------------------------


_STREET_NUMBER_PATTERN = re.compile(r"^(\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)\s+(.+)$")


def _split_street(value: str) -> tuple[str, str]:
    """Splits a real, already-resolved "123 Main Street" into
    (street_number, street_name) for sites that ask for them as two separate
    fields instead of one. Only ever runs on the real vaulted value -- never
    invents or guesses a number/name that isn't in the real address. Falls
    back to ("", whole value) for an address that doesn't start with a
    leading civic number, rather than guessing a split."""
    match = _STREET_NUMBER_PATTERN.match(value.strip())
    if not match:
        return "", value.strip()
    return match.group(1), match.group(2)


# field_name -> (real IntakeAddress field it's derived from, splitter).
# NOT a new vault entry and NOT added to vault.SENSITIVE_FIELD_NAMES (that
# set is strictly schemas.py-derived, the single source of truth for what's
# actually vaulted) -- these are resolve-time-only aliases for sites that
# split a single stored field into more than one form field. CAA's driver
# details step does this for street address.
_DERIVED_SENSITIVE_FIELDS: dict[str, tuple[str, Callable[[str], str]]] = {
    "street_number": ("street", lambda v: _split_street(v)[0]),
    "street_name": ("street", lambda v: _split_street(v)[1]),
}


def _resolve_sensitive_value(
    profile: IntakeProfile,
    field_name: str,
    *,
    vault_path: Path,
    vault_key: str | None,
) -> str:
    base_field_name, transform = _DERIVED_SENSITIVE_FIELDS.get(field_name, (field_name, None))
    for name, ref in iter_profile_refs(profile):
        if name == base_field_name:
            value = vault.resolve(ref, vault_path=vault_path, vault_key=vault_key)
            return transform(value) if transform else value
    raise KeyError(f"no vault-backed value for field_name {field_name!r} on this profile")


async def _mask_input_css(browser_session: BrowserSession, element_index: int) -> None:
    """Best-effort visual masking for the vision channel. Never raises —
    a failure here must not block the fill; redact_image's box-based
    redaction of the evidence screenshot is the authoritative protection,
    this is defense in depth for browser-use's own per-step vision capture.
    """
    try:
        node = await browser_session.get_dom_element_by_index(element_index)
        if node is None:
            return
        cdp_session = await browser_session.get_or_create_cdp_session()
        resolved = await cdp_session.cdp_client.send.DOM.resolveNode(
            params={"backendNodeId": node.backend_node_id}, session_id=cdp_session.session_id
        )
        object_id = resolved["object"]["objectId"]
        await cdp_session.cdp_client.send.Runtime.callFunctionOn(
            params={
                "objectId": object_id,
                "functionDeclaration": (
                    "function(){ this.style.setProperty('-webkit-text-security', 'disc'); }"
                ),
                "returnByValue": True,
            },
            session_id=cdp_session.session_id,
        )
    except Exception:
        pass


# --- fill_public identity-shaped-field guard --------------------------------
#
# fill_public used to accept whatever string the LLM supplied for ANY field,
# with the sensitive/non-sensitive split enforced by prompt instruction only.
# Confirmed in a live run: the model called fill_public("John", ...) /
# fill_public("Smith", ...) directly on real name fields on two live insurer
# sites, bypassing fill_sensitive (and the vault) entirely. This is the
# code-level backstop: fill_public inspects the target element's own
# name/id/autocomplete/placeholder/aria-label attributes plus its computed
# accessibility name (browser_session's EnhancedDOMTreeNode.ax_node.name,
# which already resolves an associated <label>, aria-labelledby, etc. the
# same way a screen reader would) and refuses to type into anything that
# looks identity-shaped, regardless of what the model intended to put there.
# Checked IN ORDER, first match wins -- an ordered list, not a dict, because
# "Street Name" and "Street Number" must be caught by their own specific
# rule BEFORE the generic "street" rule (which would suggest fill_sensitive
# field_name="street" -- the FULL combined address -- for what is actually a
# number-only or name-only input) and before the generic "legal_name" rule
# (which would otherwise also match the bare word "name" inside "Street
# Name" and wrongly suggest typing the person's own name into it).
_IDENTITY_SIGNAL_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "street_number",
        re.compile(
            r"\b(street|address|civic)\b.*\b(number|no)\b"
            r"|\b(number|no)\b.*\b(street|address|civic)\b"
            r"|\bhouse\s*number\b|\bcivic\s*number\b"
        ),
    ),
    ("street_name", re.compile(r"\b(street|address)\b.*\bname\b|\bname\b.*\b(street|address)\b")),
    ("street", re.compile(r"\b(address|street)\b")),
    ("legal_name", re.compile(r"\b(first|last|full|legal|given|middle|sur|user)?\s*name\b")),
    ("licence_number", re.compile(r"\blicen[cs]e\b")),
    ("date_of_birth", re.compile(r"\b(dob|birth\s*date|date\s*of\s*birth)\b")),
    ("mobile", re.compile(r"\b(phone|mobile|tel(ephone)?)\b")),
    ("email", re.compile(r"\bemail\b")),
    ("vin", re.compile(r"\bvin\b")),
]


def _humanize_tokens(raw: str) -> str:
    """camelCase / snake_case / kebab-case / trailing-digit -> space-separated
    lowercase words, so a word-boundary regex sees "vinNumber" as "vin
    number" and "address1" as "address 1" (both matching), without also
    matching "vin" inside unrelated words like "province" or "driving"
    (which have no such boundary and must NOT match)."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw)
    spaced = re.sub(r"(?<=[a-zA-Z])(?=[0-9])", " ", spaced)
    spaced = re.sub(r"[_\-]+", " ", spaced)
    return spaced.lower()


def _identity_signal_text(node: Any) -> str:
    # VALUES only, never the attribute KEY names — "name" is itself an HTML
    # attribute every form field has (e.g. <input name="make">), so
    # labelling values with their key ("name make") would make the literal
    # word "name" appear on every field and defeat this check entirely.
    parts: list[str] = []
    attributes = getattr(node, "attributes", None) or {}
    for key in ("name", "id", "autocomplete", "placeholder", "aria-label", "type"):
        value = attributes.get(key)
        if value:
            parts.append(str(value))
    ax_node = getattr(node, "ax_node", None)
    ax_name = getattr(ax_node, "name", None) if ax_node is not None else None
    if ax_name:
        parts.append(ax_name)
    return _humanize_tokens(" ".join(parts))


def _matched_identity_field(node: Any) -> str | None:
    """The fill_sensitive field name (including the street_number/street_name
    derived aliases) this element looks like, or None if it doesn't match
    any identity-shaped pattern. Checks _IDENTITY_SIGNAL_RULES in order --
    see that list's comment for why order matters here."""
    text = _identity_signal_text(node)
    for field_name, pattern in _IDENTITY_SIGNAL_RULES:
        if pattern.search(text):
            return field_name
    return None


async def _type_into_index(
    browser_session: BrowserSession,
    element_index: int,
    value: str,
    *,
    is_sensitive: bool,
    sensitive_key_name: str | None,
) -> ActionResult:
    """Reuses browser-use's own CDP-typing primitive (the same event its
    built-in `input_text` action dispatches — tools/service.py) rather than
    reimplementing element typing.
    """
    node = await browser_session.get_element_by_index(element_index)
    if node is None:
        return ActionResult(
            error=f"Element index {element_index} not available - page may have changed."
        )
    event = browser_session.event_bus.dispatch(
        TypeTextEvent(
            node=node,
            text=value,
            clear=True,
            is_sensitive=is_sensitive,
            sensitive_key_name=sensitive_key_name,
        )
    )
    await event
    await event.event_result(raise_if_any=True, raise_if_none=False)
    return ActionResult(
        extracted_content=f"filled {sensitive_key_name}" if is_sensitive else f"filled index {element_index}",
        include_in_memory=False,
    )


async def halt(gate_kind: str, reason: str) -> ActionResult:
    """LLM-invoked voluntary halt. Module-level (not a build_tools closure)
    since it needs neither `profile` nor `sensitive_data` — directly callable
    in tests without constructing a Tools instance.

    `gate_kind` is free text the model chooses — it is NEVER used to select a
    Status. Only a deterministic allquote.gates.GateHit produced by the step
    hook may do that. See allquote/executor.py's halt-status rule.
    """
    return ActionResult(
        is_done=True,
        success=False,
        extracted_content=json.dumps({"gate_kind": gate_kind, "reason": reason}),
    )


def build_tools(
    profile: IntakeProfile,
    sensitive_data: dict[str, str],
    *,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
) -> Tools:
    """Registers fill_sensitive / fill_public / halt as custom actions.

    `sensitive_data` must be the SAME dict object passed to
    `Agent(sensitive_data=...)` — fill_sensitive mutates it in place so
    browser-use's native message/history filtering picks up each value the
    moment it's resolved (see module docstring point 1).

    `vault_path`/`vault_key` default to the real vault (`vault.VAULT_PATH`,
    `VAULT_KEY` env var) for production use, and are overridable so tests can
    point at an isolated vault file — same pattern as every other function in
    `allquote.vault`/`allquote.redact`.
    """
    tools = Tools()

    @tools.action(
        "Fill a sensitive field (licence number, DOB, VIN, address, etc.) into the "
        "element at the given index. Pass only the field NAME — never the value, "
        "which you never see. If the site splits street address into two fields, "
        "use street_number and street_name instead of street. Raises if field_name "
        "is not a recognized sensitive field."
    )
    async def fill_sensitive(field_name: str, element_index: int, browser_session: BrowserSession) -> ActionResult:
        if field_name not in vault.SENSITIVE_FIELD_NAMES and field_name not in _DERIVED_SENSITIVE_FIELDS:
            raise ValueError(
                f"{field_name!r} is not a recognized sensitive field "
                f"(see allquote.vault.SENSITIVE_FIELD_NAMES, or street_number/street_name "
                f"for a site that splits street address into two fields)"
            )
        value = _resolve_sensitive_value(profile, field_name, vault_path=vault_path, vault_key=vault_key)
        sensitive_data[field_name] = value
        await _mask_input_css(browser_session, element_index)
        return await _type_into_index(
            browser_session, element_index, value, is_sensitive=True, sensitive_key_name=field_name
        )

    @tools.action(
        "Fill a non-sensitive value into the element at the given index. Refuses "
        "identity-shaped fields (name, licence, DOB, address, phone, email, VIN) — "
        "use fill_sensitive for those instead."
    )
    async def fill_public(value: str, element_index: int, browser_session: BrowserSession) -> ActionResult:
        node = await browser_session.get_dom_element_by_index(element_index)
        if node is not None:
            matched = _matched_identity_field(node)
            if matched is not None:
                raise ValueError(
                    f"element index {element_index} looks like an identity field "
                    f"({matched}, based on its name/label/autocomplete attribute) — "
                    f"fill_public refuses identity-shaped fields. Use "
                    f"fill_sensitive(field_name={matched!r}, element_index={element_index}) instead."
                )
        return await _type_into_index(
            browser_session, element_index, value, is_sensitive=False, sensitive_key_name=None
        )

    tools.action(
        "Stop the run immediately because this page requires something automation must "
        "never do on its own (consent, identity verification, a declaration, payment, "
        "a CAPTCHA, login). Describe what you saw in `reason` — never invent details."
    )(halt)

    return tools


# --- CAPTCHA structural visibility scan --------------------------------------
#
# A presented CAPTCHA challenge vs. a merely-loaded CAPTCHA library looks
# identical to a substring search over raw HTML (both contain the string
# "recaptcha") but is trivially different to a live DOM: a challenge is an
# actually-rendered element. This mirrors _BOX_SCAN_JS's own visibility test
# (non-zero getBoundingClientRect) rather than inventing a second convention.
#
# A visible iframe alone is NOT enough: reCAPTCHA v3's mandatory
# ".grecaptcha-badge" attribution widget ("Protected by reCAPTCHA") is a
# real, visible, non-zero-sized iframe whose src also contains
# "recaptcha/api2/anchor" — it is score-based and invisible to the visitor,
# present on most commercial sites, and never presents a challenge. It is
# excluded three ways: by ancestor ".grecaptcha-badge" class, by a
# "data-size=\"invisible\"" attribute anywhere in its ancestor chain, and by
# a minimum rendered size (~304x78 for a real v2 checkbox vs. ~70x60 for the
# v3 badge) — any one of the three is enough to catch it, so a site that
# only satisfies one is still excluded.
_MIN_CAPTCHA_WIDTH = 250
_MIN_CAPTCHA_HEIGHT = 60

_CAPTCHA_SCAN_JS = rf"""
() => {{
    const hits = [];
    const visible = (el) => {{
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }};
    const isBadgeOrInvisible = (el) => {{
        let node = el;
        while (node) {{
            if (node.classList && node.classList.contains("grecaptcha-badge")) return true;
            if (node.getAttribute && node.getAttribute("data-size") === "invisible") return true;
            node = node.parentElement;
        }}
        return false;
    }};

    for (const frame of document.querySelectorAll("iframe[src]")) {{
        if (!visible(frame)) continue;
        if (isBadgeOrInvisible(frame)) continue;
        const rect = frame.getBoundingClientRect();
        if (rect.width < {_MIN_CAPTCHA_WIDTH} || rect.height < {_MIN_CAPTCHA_HEIGHT}) continue;
        const src = frame.src || "";
        if (/recaptcha\/api2\/(anchor|bframe)/i.test(src)) {{
            hits.push("visible iframe: recaptcha/api2/" + (/bframe/i.test(src) ? "bframe" : "anchor"));
        }} else if (/hcaptcha\.com\/captcha/i.test(src)) {{
            hits.push("visible iframe: hcaptcha.com/captcha");
        }} else if (/turnstile/i.test(src)) {{
            hits.push("visible iframe: turnstile challenge");
        }}
    }}

    const cfChallenge = document.querySelector("#cf-challenge-stage, #challenge-stage, .cf-turnstile-wrapper");
    if (cfChallenge && visible(cfChallenge)) {{
        hits.push("visible Cloudflare interstitial");
    }}

    return hits;
}}
"""


async def scan_captcha_structural_hits(page: Any) -> list[str]:
    """Returns plain-text descriptions of any visible CAPTCHA-shaped element
    on the current page — empty if none. Never raises: a dead/navigating
    page's evaluate() failing here must not block gate detection for the
    step, same rationale as the text/dom extraction in `make_step_hook`.
    """
    try:
        raw_result = await page.evaluate(_CAPTCHA_SCAN_JS)
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except Exception:
        return []
    return list(result) if result else []


# --- active-region scoping: text detectors never see the whole page --------
#
# document.body.innerText includes everything on the page — footer legal
# boilerplate, cross-sell promo blocks, unrelated fine print — exactly as
# readily as the actual in-flow form copy a gate is supposed to be about.
# That produced a real false positive: Tangerine Bank credit-card promo
# fine print in sonnet.ca's footer ("...must consent to a credit check...")
# matched consent_or_terms_required, nowhere near the form being filled in.
# `_ACTIVE_REGION_JS` finds the nearest common container of the visible,
# in-viewport interactive controls (input/select/textarea/button/[role=
# button]) — in practice a <form>, or the smallest ancestor spanning them —
# explicitly excluding <footer>/<nav>/[role=contentinfo] and common promo/
# disclaimer classes from the candidate set before computing that container.
# gates.detect()'s text patterns run against ITS innerText, never the whole
# page's.
#
# Zero candidates — a blank page, a JS app mid-hydration — is reported as
# `hasContainer: false`, never a fallback scan of document.body.innerText.
# document.readyState can report "complete" before a client-rendered app has
# painted anything (the app's own shell finished loading; nothing has
# hydrated yet), which is exactly how a page with zero real controls but an
# already-server-rendered footer produced a false positive even after
# scoping existed: the old fallback branch here scanned the whole page
# specifically BECAUSE there was nothing to scope to yet. `make_step_hook`
# now skips gate detection entirely for the step when `hasContainer` is
# false — same as the readyState skip: no container means nothing to gate
# on yet, not "fall back and scan anyway". (A container that isn't a <form>
# — e.g. checkbox-and-button siblings with no wrapping <form>, a common
# small-interstitial shape — legitimately can be document.body itself; that
# is not the bug this guards against and is left alone.)
_ACTIVE_REGION_JS = r"""
() => {
    const EXCLUDE_SELECTOR = 'footer, nav, [role="contentinfo"], .promo, .promotion, ' +
        '.disclaimer, .fine-print, .advertisement, .marketing, [class*="promo"], ' +
        '[class*="disclaimer"], [class*="advert"]';

    const viewportW = window.innerWidth || document.documentElement.clientWidth;
    const viewportH = window.innerHeight || document.documentElement.clientHeight;
    const inViewport = (rect) => (
        rect.width > 0 && rect.height > 0 &&
        rect.bottom > 0 && rect.top < viewportH &&
        rect.right > 0 && rect.left < viewportW
    );

    const isExcluded = (el) => {
        let node = el;
        while (node) {
            if (node.matches && node.matches(EXCLUDE_SELECTOR)) return true;
            node = node.parentElement;
        }
        return false;
    };

    const NO_CONTAINER = { hasContainer: false };

    const candidates = Array.from(
        document.querySelectorAll('input, select, textarea, button, [role="button"]')
    ).filter((el) => !isExcluded(el) && inViewport(el.getBoundingClientRect()));

    if (candidates.length === 0) {
        // Two different things look identical from "zero candidates" alone:
        // a genuine single-purpose informational/terminal page (no form was
        // ever going to exist — e.g. an ineligibility or maintenance
        // notice, where the whole body IS the content) vs. a JS app whose
        // shell chrome (footer/nav/promo) has already server-rendered but
        // whose actual form hasn't hydrated yet. Whether any excluded-chrome
        // element exists at all is what tells them apart: if one does, this
        // is the loading state, not a real terminal page — skip rather than
        // scan whatever boilerplate happens to already be on screen.
        const hasExcludedChrome = document.querySelector(EXCLUDE_SELECTOR) !== null;
        if (hasExcludedChrome) {
            return NO_CONTAINER;
        }
        return { hasContainer: true, text: document.body.innerText || "", hasBlockingControl: false };
    }

    // Prefer an explicit <form> that contains the majority of candidates.
    let container = null;
    for (const form of document.querySelectorAll("form")) {
        if (isExcluded(form)) continue;
        const containedCount = candidates.filter((el) => form.contains(el)).length;
        if (containedCount > candidates.length / 2) {
            container = form;
            break;
        }
    }

    if (!container) {
        // Lowest common ancestor of every candidate.
        let common = candidates[0];
        for (const el of candidates.slice(1)) {
            while (common && !common.contains(el)) {
                common = common.parentElement;
            }
        }
        container = common;
    }

    if (!container || isExcluded(container)) {
        container = document.querySelector("main") || document.body;
    }

    const hasUncheckedCheckbox = Array.from(
        container.querySelectorAll('input[type="checkbox"]')
    ).some((cb) => !cb.checked);
    const hasRequiredInput = container.querySelectorAll("input[required], select[required], textarea[required]").length > 0;

    return {
        hasContainer: true,
        text: container.innerText || "",
        hasBlockingControl: hasUncheckedCheckbox || hasRequiredInput,
    };
}
"""


async def scan_active_region(page: Any) -> tuple[str, bool] | None:
    """Returns (active_region_text, has_blocking_control), or None when no
    meaningful active region exists yet — see `_ACTIVE_REGION_JS`. None
    means "skip gate detection for this step", exactly like the readyState
    check; it is NEVER a signal to fall back to document.body.innerText,
    which would silently undo the scoping this function exists to provide.
    A page.evaluate() failure is treated the same way, for the same reason.
    """
    try:
        raw_result = await page.evaluate(_ACTIVE_REGION_JS)
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except Exception:
        return None
    if not result or not result.get("hasContainer"):
        return None
    return result.get("text", "") or "", bool(result.get("hasBlockingControl"))


# --- scroll a gate's matched text into view before evidence capture --------
#
# The evidence screenshot is a viewport capture; a text-based gate hit can
# be scoped correctly (see above) and still not be currently on screen (a
# tall form where the matched checkbox is below the fold). Best-effort: find
# `matched_text` as live page text and scroll its element into view. Returns
# False (never raises) if it can't be found — e.g. a structural hit's plain-
# language label, which was never real page prose to begin with — so the
# caller can say so in the evidence reason rather than imply the screenshot
# shows it.
_SCROLL_TO_TEXT_JS = r"""
(needle) => {
    // Returns an object, not a bare boolean: this Page.evaluate() wrapper
    // stringifies a raw JS boolean via Python's str(bool) ("True"/"False"),
    // not JSON — bool("False") is truthy, so a bare true/false return would
    // make every call look like a hit. Every other page.evaluate() in this
    // module already returns an object/array for the same reason.
    const normalize = (s) => (s || "").replace(/\s+/g, " ").trim().toLowerCase();
    const target = normalize(needle);
    if (!target) return { found: false };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
        const content = normalize(node.textContent);
        if (content && content.includes(target)) {
            const el = node.parentElement;
            if (el) {
                el.scrollIntoView({ block: "center", inline: "nearest" });
                return { found: true };
            }
        }
    }
    return { found: false };
}
"""


async def scroll_text_into_view(browser_session: BrowserSession, needle: str) -> bool:
    clean = needle.strip().rstrip("…").strip()
    if not clean:
        return False
    try:
        page = await browser_session.must_get_current_page()
        raw_result = await page.evaluate(_SCROLL_TO_TEXT_JS, clean)
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except Exception:
        return False
    return bool(result.get("found")) if result else False


async def get_current_url(browser_session: BrowserSession) -> str | None:
    """Best-effort: the URL of whatever page the browser is CURRENTLY on.

    Used by allquote.executor at end-of-run to confirm a recorded GateHit's
    `.url` still matches the page the run actually ended on before trusting
    it — never raises; a dead/closed session or a failed evaluate() returns
    None, and the caller must treat that as "cannot confirm", not as a
    match (see executor.py's stale-hit discard: fail closed, never report a
    gate detected on a page the run wasn't on when it stopped).
    """
    try:
        page = await browser_session.must_get_current_page()
        raw = await page.evaluate("() => window.location.href")
        return raw if isinstance(raw, str) else None
    except Exception:
        return None


# --- deterministic gate step hook -------------------------------------------
#
# A byte-identical evidence screenshot across separate runs turned out to be
# a step-boundary race, not a caching bug: by the time the hook read the
# DOM, the agent had already clicked through to the next page, but the read
# landed on the OUTGOING document mid-navigation (readyState "complete" on
# the page about to be replaced, not the one actually current). Two checks
# below guard this, independent of and in addition to the existing
# readyState/active-region checks (which stay exactly as they were):
# comparing this step's URL to the previous step's (a navigation was
# observed since last time -> skip this transition step), and comparing the
# page handle's own live URL to what browser-use's state summary claims the
# current URL is (the two can independently race a navigation within a
# single step) — both must agree before readyState is even consulted, and
# readyState itself is read from the SAME evaluate() call as that live URL
# so it can never describe a different document than the one just checked.

_PAGE_STATE_JS = "() => ({ url: window.location.href, readyState: document.readyState })"

# --- TEMPORARY diagnostic instrumentation (remove once the stale-gate-hit
# investigation is closed) -- gated by an env var so it's a no-op in normal
# runs and in the existing test suite. Prints one line per step: step
# number, url, whether detection was skipped and why, and whether a GateHit
# was recorded on this call.
_GATE_DEBUG = bool(os.environ.get("ALLQUOTE_GATE_DEBUG"))


def _gate_debug(step_number: int, url: str, note: str) -> None:
    if _GATE_DEBUG:
        print(f"[gate_debug] step={step_number} url={url!r} {note}", flush=True)


def make_step_hook(
    profile: IntakeProfile,
    gate_box: list[gates.GateHit],
    agent_box: list[Any],
    browser_session: BrowserSession,
    *,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
) -> Callable[..., Any]:
    """Returns the callback passed as `Agent(register_new_step_callback=...)`.

    Runs `gates.detect()` on every step using stable Playwright/CDP text
    extraction (never browser-use's internal DOM serializer — see module
    docstring point 2). `gate_box` holds at most one entry, but "first hit
    wins" no longer means "first hit forever": a recorded GateHit carries
    the URL and step number it was detected on (see `gates.GateHit.url` /
    `.step_number`), and is only a no-op reason to skip THIS step if the
    current URL still matches it — nothing new to learn about a page we've
    already recorded. If the URL has since changed, that old hit describes a
    page the browser is no longer on; it is discarded (not trusted) and
    detection runs fresh against whatever page is current now. This is what
    stops a hit from becoming permanently sticky and blind to every
    subsequent page regardless of what's actually on it — the bug behind a
    stale hit surviving multiple real page transitions and being reported
    with a screenshot of a page it was never observed on. `agent.stop()`
    (via `agent_box`, populated by the caller right after `Agent(...)`
    construction) is called every time a hit is freshly recorded — once for
    the original hit, and again if a later, different page produces its own
    — never on a step that's merely re-confirming an already-recorded hit.
    The LLM never decides whether to proceed past a gate.

    `vault_path`/`vault_key` are needed here because redacting the evidence
    snippet (`redact_text`) resolves every sensitive field on `profile` to
    build its literal-substitution rules — same override pattern as
    `build_tools`.
    """

    previous_url: str | None = None
    # TEMPORARY (see _GATE_DEBUG above): the step agent.stop() was last
    # called at, so every step processed afterward is visible in the log —
    # if the real agent keeps stepping well past a halt, that's a second,
    # separate bug this makes visible instead of masking.
    stop_called_at_step: int | None = None

    async def _step_hook(browser_state_summary: Any, agent_output: Any, step_number: int) -> None:
        nonlocal previous_url, stop_called_at_step
        url = getattr(browser_state_summary, "url", "")

        if stop_called_at_step is not None:
            _gate_debug(
                step_number,
                url,
                f"NOTE: agent.stop() was called at step {stop_called_at_step} "
                f"({step_number - stop_called_at_step} step(s) ago) — still being asked to process step {step_number}",
            )

        if gate_box:
            recorded = gate_box[0]
            if recorded.url == url:
                _gate_debug(
                    step_number, url, f"skipped: hit already recorded on this url (kind={recorded.kind!r})"
                )
                return
            _gate_debug(
                step_number,
                url,
                f"stale hit discarded: recorded at step={recorded.step_number} url={recorded.url!r} "
                f"kind={recorded.kind!r} — current url differs, re-detecting fresh",
            )
            gate_box.clear()

        # (1) A navigation was observed since the last step -- reading the
        # DOM right now risks landing on the outgoing page while the new
        # one is still loading. previous_url is updated regardless of
        # whether this step is skipped, so the check is always against the
        # immediately preceding step, and a stable run of same-URL steps
        # naturally clears it after one skip.
        navigated_since_last_step = previous_url is not None and url != previous_url
        previous_url = url
        if navigated_since_last_step:
            _gate_debug(step_number, url, "skipped: navigated_since_last_step (transition step)")
            return

        try:
            page = await browser_session.must_get_current_page()
            raw_page_state = await page.evaluate(_PAGE_STATE_JS)
            page_state = json.loads(raw_page_state) if isinstance(raw_page_state, str) else raw_page_state
        except Exception as exc:
            _gate_debug(step_number, url, f"skipped: page_state evaluate() raised {type(exc).__name__}: {exc}")
            return

        live_url = (page_state or {}).get("url", "")
        ready_state = (page_state or {}).get("readyState", "")

        # (2) Within this single step, the page handle's own live URL and
        # what browser-use's state summary says the current URL is can
        # still disagree (each was captured at a slightly different time) —
        # that's navigation in flight too, caught independently of (1).
        if live_url != url:
            _gate_debug(step_number, url, f"skipped: live_url {live_url!r} != browser_state_summary.url {url!r}")
            return

        if ready_state != "complete":
            # A mid-load DOM is a false-positive factory for every detector,
            # not just CAPTCHA — a modal not yet attached, a script not yet
            # run, a partially-parsed body. Skip this step; the callback
            # fires again on the next step once the page has settled.
            _gate_debug(step_number, url, f"skipped: readyState={ready_state!r} != complete")
            return

        region = await scan_active_region(page)
        if region is None:
            # readyState alone is not enough: a client-rendered app can
            # report "complete" before it has hydrated anything (no form,
            # no visible interactive controls yet — a blank page). No
            # active region means nothing can be gating us; skip detection
            # entirely for this step rather than falling back to whatever
            # boilerplate the shell has already server-rendered (a footer's
            # promo text, in the case this guards against). The next step
            # re-checks once the page has actually rendered a form.
            _gate_debug(step_number, url, "skipped: scan_active_region returned None (no container)")
            return
        active_text, blocking_control_present = region

        try:
            dom = await page.evaluate("() => document.documentElement.outerHTML")
        except Exception as exc:
            _gate_debug(step_number, url, f"skipped: outerHTML evaluate() raised {type(exc).__name__}: {exc}")
            return

        captcha_structural_hits = await scan_captcha_structural_hits(page)

        hit = gates.detect(
            url,
            active_text,
            dom,
            captcha_structural_hits=captcha_structural_hits,
            blocking_control_present=blocking_control_present,
        )
        if hit is None:
            _gate_debug(step_number, url, "detection ran: no GateHit (page is clean)")
            return

        redacted_hit = hit.model_copy(
            update={
                "evidence_snippet": redact_text(
                    hit.evidence_snippet, profile, vault_path=vault_path, vault_key=vault_key
                ),
                "matched_text": redact_text(hit.matched_text, profile, vault_path=vault_path, vault_key=vault_key),
                "url": url,
                "step_number": step_number,
            }
        )
        gate_box.append(redacted_hit)
        _gate_debug(
            step_number,
            url,
            f"GateHit RECORDED: kind={redacted_hit.kind!r} matched_text={redacted_hit.matched_text!r}",
        )

        if agent_box:
            agent_box[0].stop()
            stop_called_at_step = step_number
            _gate_debug(step_number, url, f"agent.stop() called at step {step_number}")

    return _step_hook


# --- evidence screenshot: capture to bytes, redact, write ------------------

_BOX_SCAN_JS = """
(patternSources, literalValues) => {
    const patterns = patternSources.map((src) => new RegExp(src, "gi"));
    const boxes = [];

    const pushRect = (rect) => {
        if (rect.width > 0 && rect.height > 0) {
            boxes.push({
                left: rect.left, top: rect.top,
                right: rect.right, bottom: rect.bottom,
            });
        }
    };

    // 1) input/textarea values matching a resolved sensitive value.
    const fields = document.querySelectorAll("input, textarea");
    for (const field of fields) {
        const value = field.value || "";
        if (!value) continue;
        for (const literal of literalValues) {
            if (literal && value.includes(literal)) {
                pushRect(field.getBoundingClientRect());
                break;
            }
        }
    }

    // 2) rendered text nodes matching a shape pattern or a literal value —
    // catches quote-summary/review pages that echo a sensitive value as
    // plain body text, which no input scan or CSS trick would find.
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
        const content = node.textContent || "";
        if (!content.trim()) continue;

        const matches = [];
        for (const pattern of patterns) {
            pattern.lastIndex = 0;
            let m;
            while ((m = pattern.exec(content)) !== null) {
                matches.push([m.index, m.index + m[0].length]);
                if (m[0].length === 0) pattern.lastIndex++;
            }
        }
        for (const literal of literalValues) {
            if (!literal) continue;
            let start = content.indexOf(literal);
            while (start !== -1) {
                matches.push([start, start + literal.length]);
                start = content.indexOf(literal, start + literal.length);
            }
        }

        for (const [start, end] of matches) {
            const range = document.createRange();
            range.setStart(node, start);
            range.setEnd(node, end);
            for (const rect of range.getClientRects()) {
                pushRect(rect);
            }
        }
    }

    return { boxes, devicePixelRatio: window.devicePixelRatio || 1 };
}
"""


async def capture_evidence_screenshot(
    browser_session: BrowserSession,
    sensitive_data: dict[str, str],
    destination: Path,
) -> Path:
    """Captures the current page to bytes (never disk), computes redaction
    boxes from both input values and rendered text, and writes only the
    redacted copy via `redact.redact_image`. The raw bytes variable is never
    passed to any disk-writing call.
    """
    raw_bytes: bytes = await browser_session.take_screenshot()

    pattern_sources = [pattern.pattern for pattern in SHAPE_PATTERNS.values()]
    literal_values = [v for v in sensitive_data.values() if v]

    boxes: list[tuple[int, int, int, int]] = []
    try:
        page = await browser_session.must_get_current_page()
        # page.evaluate(page_function, *args) itself wraps page_function in
        # one more `(...)( args )` invocation — passing args this way (not
        # by pre-building our own IIFE string) is what that method's own
        # calling convention requires; confirmed by running it.
        raw_result = await page.evaluate(_BOX_SCAN_JS, pattern_sources, literal_values)
        # This Page.evaluate() JSON-stringifies object/array results into a
        # plain string rather than returning them parsed — confirmed by
        # running it (see tests/test_browser_ops.py).
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
        scale = result.get("devicePixelRatio", 1) or 1
        for box in result.get("boxes", []):
            boxes.append(
                (
                    round(box["left"] * scale),
                    round(box["top"] * scale),
                    round(box["right"] * scale),
                    round(box["bottom"] * scale),
                )
            )
    except Exception:
        # Best-effort box computation: if it fails, fall through with
        # whatever boxes we already had (possibly none) rather than raising
        # out of evidence capture — redact_image still redacts what it has.
        pass

    return redact_image(raw_bytes, boxes, output_path=destination)
