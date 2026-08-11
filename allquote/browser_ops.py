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
   (`page.evaluate("() => document.body.innerText")`, `page.evaluate("() =>
   document.documentElement.outerHTML")` — this Page class requires arrow-
   function-format JS, confirmed by running it) — never browser-use's internal
   DOM serializer/`llm_representation()`, which is an interactive-elements
   listing for the model's own action loop, not a page-text transcript, and
   is undocumented, version-specific surface this module has no business
   coupling to. On a hit it calls `agent.stop()` directly; the LLM never
   decides to proceed past a gate.
3. The raw screenshot never touches disk. `capture_evidence_screenshot`
   captures to bytes in memory, computes redaction boxes from BOTH input
   values and rendered text (a quote-summary page can echo a sensitive value
   as plain text, which no input-value scan or CSS trick would catch), and
   hands bytes straight to `redact.redact_image` — there is no code path
   that writes the unredacted bytes anywhere.
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
            text = await page.evaluate("() => document.body.innerText")
        except Exception:
            return

        try:
            dom = await page.evaluate("() => document.documentElement.outerHTML")
        except Exception:
            return

        hit = gates.detect(url, text, dom)
        if hit is None:
            return

        redacted_hit = hit.model_copy(
            update={
                "evidence_snippet": redact_text(
                    hit.evidence_snippet, profile, vault_path=vault_path, vault_key=vault_key
                )
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
