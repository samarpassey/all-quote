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


def _resolve_sensitive_value(
    profile: IntakeProfile,
    field_name: str,
    *,
    vault_path: Path,
    vault_key: str | None,
) -> str:
    for name, ref in iter_profile_refs(profile):
        if name == field_name:
            return vault.resolve(ref, vault_path=vault_path, vault_key=vault_key)
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
        "which you never see. Raises if field_name is not a recognized sensitive field."
    )
    async def fill_sensitive(field_name: str, element_index: int, browser_session: BrowserSession) -> ActionResult:
        if field_name not in vault.SENSITIVE_FIELD_NAMES:
            raise ValueError(
                f"{field_name!r} is not a recognized sensitive field "
                f"(see allquote.vault.SENSITIVE_FIELD_NAMES)"
            )
        value = _resolve_sensitive_value(profile, field_name, vault_path=vault_path, vault_key=vault_key)
        sensitive_data[field_name] = value
        await _mask_input_css(browser_session, element_index)
        return await _type_into_index(
            browser_session, element_index, value, is_sensitive=True, sensitive_key_name=field_name
        )

    @tools.action("Fill a non-sensitive value into the element at the given index.")
    async def fill_public(value: str, element_index: int, browser_session: BrowserSession) -> ActionResult:
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

    const candidates = Array.from(
        document.querySelectorAll('input, select, textarea, button, [role="button"]')
    ).filter((el) => !isExcluded(el) && inViewport(el.getBoundingClientRect()));

    if (candidates.length === 0) {
        // Nothing to scope to (e.g. a pure informational/error page) --
        // the whole body is the only reasonable region.
        return { text: document.body.innerText || "", hasBlockingControl: false };
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
        text: container.innerText || "",
        hasBlockingControl: hasUncheckedCheckbox || hasRequiredInput,
    };
}
"""


async def scan_active_region(page: Any) -> tuple[str, bool]:
    """Returns (active_region_text, has_blocking_control) — see
    `_ACTIVE_REGION_JS`. Falls back to (document.body.innerText, False) on
    any evaluate failure, same fail-open-to-full-page-text behaviour the
    caller already had before this scoping existed, rather than blocking
    detection outright on a transient evaluate error.
    """
    try:
        raw_result = await page.evaluate(_ACTIVE_REGION_JS)
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except Exception:
        try:
            fallback_text = await page.evaluate("() => document.body.innerText")
        except Exception:
            return "", False
        return fallback_text, False
    if not result:
        return "", False
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


# --- deterministic gate step hook -------------------------------------------


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
    docstring point 2). First hit wins: once `gate_box` is populated the hook
    is a no-op, and `agent.stop()` (via `agent_box`, populated by the caller
    right after `Agent(...)` construction) is called exactly once — the LLM
    never decides whether to proceed past a gate.

    `vault_path`/`vault_key` are needed here because redacting the evidence
    snippet (`redact_text`) resolves every sensitive field on `profile` to
    build its literal-substitution rules — same override pattern as
    `build_tools`.
    """

    async def _step_hook(browser_state_summary: Any, agent_output: Any, step_number: int) -> None:
        if gate_box:
            return

        url = getattr(browser_state_summary, "url", "")

        try:
            page = await browser_session.must_get_current_page()
            ready_state = await page.evaluate("() => document.readyState")
        except Exception:
            return

        if ready_state != "complete":
            # A mid-load DOM is a false-positive factory for every detector,
            # not just CAPTCHA — a modal not yet attached, a script not yet
            # run, a partially-parsed body. Skip this step; the callback
            # fires again on the next step once the page has settled.
            return

        active_text, blocking_control_present = await scan_active_region(page)

        try:
            dom = await page.evaluate("() => document.documentElement.outerHTML")
        except Exception:
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
            return

        redacted_hit = hit.model_copy(
            update={
                "evidence_snippet": redact_text(
                    hit.evidence_snippet, profile, vault_path=vault_path, vault_key=vault_key
                ),
                "matched_text": redact_text(hit.matched_text, profile, vault_path=vault_path, vault_key=vault_key),
            }
        )
        gate_box.append(redacted_hit)

        if agent_box:
            agent_box[0].stop()

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
