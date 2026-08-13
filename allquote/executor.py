"""Browser executor: run_route() + CLI. See PLAN.md Task 5 / the approved plan
at .claude/plans (status mapping table, halt-status rule, provenance rule).

`run_route()` never returns Status.UNRESOLVED — that value is the registry's
seed/non-terminal "not yet attempted" marker (see docs/SCHEMAS.md Metrics).
A call to run_route() is by definition an attempt: every path out of it is
either a determination (quoted_*, estimate_only, ineligible, callback_required,
manual_handoff) or a bounded-attempt exhaustion that is itself terminal,
evidence-backed information (unreachable, blocked).

Only a `gates.GateHit` produced by the deterministic step hook may select a
gate-kind Status. An LLM-invoked `halt()` never chooses its own status: it
either rides along with a detector's already-deterministic hit on the same
page (detector wins), or — if the detector found nothing — degrades to the
fixed `unreachable` status with the model's reason kept as plain-text detail.
"""

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from browser_use import Agent, BrowserProfile, BrowserSession, ChatAnthropic
from dotenv import load_dotenv

from allquote import browser_ops, gates, registry, vault
from allquote.evidence import write_evidence_record
from allquote.redact import redact_text, safe_write_evidence
from allquote.schemas import (
    CoverageBenchmark,
    CoverageComparison,
    DiscountInfo,
    EvidenceInfo,
    EvidenceRecord,
    IntakeProfile,
    MarketRecord,
    PriceInfo,
    PrivacyInfo,
    QuoteOutcome,
    QuoteResult,
    QuoteSource,
    Status,
    ValidityInfo,
    sensitive_fields,
)

EVIDENCE_ROOT = Path("data/evidence")


def _default_max_steps() -> int:
    # Deferred to call time, not bound at import time — matches
    # allquote.vault._resolve_key()'s pattern. load_dotenv() only runs
    # inside main() (same convention as registry.py/vault.py/intake.py), so
    # a module-level constant read at import time would miss it.
    return int(os.environ.get("EXECUTOR_MAX_STEPS", "25"))


def _default_timeout_s() -> float:
    return float(os.environ.get("EXECUTOR_TIMEOUT_S", "240"))


# --- is_transient() ----------------------------------------------------------

_TRANSIENT_EXCEPTION_NAMES = {
    # browser-use/Playwright/CDP exception class names this module doesn't
    # import directly (kept by name to avoid a hard dependency on their
    # exact module paths, which move between versions).
    "TargetClosedError",
    "BrowserClosedError",
    "PlaywrightError",
    "CDPConnectionError",
}


def is_transient(exc: BaseException, *, http_status: int | None = None) -> bool:
    """True only for: connection error, DNS failure, timeout before first
    paint, HTTP 5xx, or browser crash — the bounded single-retry cases.
    Never true for a gate, CAPTCHA, ineligibility, or rejection; those never
    reach this classifier (gate hits are handled separately, unconditionally
    never retried, before any exception-based classification happens).
    """
    if http_status is not None and 500 <= http_status < 600:
        return True
    if isinstance(exc, (ConnectionError, socket.gaierror, TimeoutError)):
        return True
    return type(exc).__name__ in _TRANSIENT_EXCEPTION_NAMES


def nav_timeout_guess(timeout_s: float) -> float:
    """Bounded initial-navigation timeout, distinct from the overall attempt
    budget — this is what makes "timeout before first paint" (is_transient,
    retry-eligible) unambiguous from "the agent ran out of its 240s budget
    after the site loaded fine" (budget exhaustion, not retried). Both would
    otherwise raise the same TimeoutError with no way to tell them apart.
    """
    return min(30.0, timeout_s)


# --- evidence writing ---------------------------------------------------------


def _new_run_id() -> str:
    return uuid4().hex[:12]


def _write_derived_channel_evidence(
    record: MarketRecord,
    profile: IntakeProfile,
    run_id: str,
    *,
    evidence_root: Path,
    vault_path: Path,
    vault_key: str | None,
) -> EvidenceRecord:
    """The `quote_url is None` early-return: no page was loaded, no contact
    was made with the market — this evidence is derived from our own
    registry metadata, never `observed`.
    """
    evidence_dir = evidence_root / run_id
    destination = evidence_dir / "channel_unavailable.json"
    payload = json.dumps(
        {
            "registry_id": record.registry_id,
            "distribution_type": record.distribution_type,
            "public_phone_route": record.public_phone_route,
            "requirements": record.requirements,
        },
        indent=2,
    )
    safe_write_evidence(payload, "text", destination, profile=profile, vault_path=vault_path, vault_key=vault_key)
    return write_evidence_record(
        registry_id=record.registry_id,
        kind="document",
        timestamp=datetime.now(timezone.utc),
        source_url_or_phone=record.public_phone_route or record.source_url,
        artifact_path=destination,
        provenance="derived",
    )


def _write_run_start_evidence(record: MarketRecord, run_id: str, profile: IntakeProfile, *, evidence_root: Path) -> None:
    evidence_dir = evidence_root / run_id
    destination = evidence_dir / "run_start.json"
    payload = json.dumps(
        {
            "registry_id": record.registry_id,
            "consent_mode": (profile.consent.mode if profile.consent else None),
            "model": os.environ.get("EXECUTOR_MODEL"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        indent=2,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload)
    write_evidence_record(
        registry_id=record.registry_id,
        kind="document",
        timestamp=datetime.now(timezone.utc),
        source_url_or_phone=record.quote_url or "",
        artifact_path=destination,
        provenance="observed",
    )


async def _write_attempt_evidence(
    *,
    record: MarketRecord,
    profile: IntakeProfile,
    run_id: str,
    attempt_number: int,
    browser_session: BrowserSession | None,
    sensitive_data: dict[str, str],
    target_url: str,
    detail: dict[str, Any],
    evidence_root: Path,
    vault_path: Path,
    vault_key: str | None,
) -> EvidenceRecord:
    """Captures the evidence screenshot for this attempt. If the browser
    session is already dead (post-timeout, post-crash) the screenshot
    capture itself can raise — that must never destroy an otherwise-good
    QuoteResult, so on failure this falls back to a text EvidenceRecord
    documenting the capture failure and still returns something usable as
    `evidence_artifact`.
    """
    attempt_dir = evidence_root / run_id / f"attempt-{attempt_number}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = attempt_dir / "evidence.png"

    detail_text = json.dumps(detail, indent=2)
    detail_path = attempt_dir / "detail.json"
    safe_write_evidence(detail_text, "text", detail_path, profile=profile, vault_path=vault_path, vault_key=vault_key)

    fields_disclosed = list(sensitive_data.keys())

    if browser_session is not None:
        try:
            await browser_ops.capture_evidence_screenshot(browser_session, sensitive_data, screenshot_path)
            return write_evidence_record(
                registry_id=record.registry_id,
                kind="screenshot",
                timestamp=datetime.now(timezone.utc),
                source_url_or_phone=target_url,
                artifact_path=screenshot_path,
                provenance="observed",
                fields_disclosed=fields_disclosed,
            )
        except Exception as exc:
            failure_path = attempt_dir / "capture_failure.json"
            failure_text = json.dumps(
                {"screenshot_capture_failed": True, "exception_type": type(exc).__name__, "exception_message": str(exc)},
                indent=2,
            )
            safe_write_evidence(
                failure_text, "text", failure_path, profile=profile, vault_path=vault_path, vault_key=vault_key
            )
            return write_evidence_record(
                registry_id=record.registry_id,
                kind="document",
                timestamp=datetime.now(timezone.utc),
                source_url_or_phone=target_url,
                artifact_path=failure_path,
                provenance="observed",
                fields_disclosed=fields_disclosed,
            )

    return write_evidence_record(
        registry_id=record.registry_id,
        kind="document",
        timestamp=datetime.now(timezone.utc),
        source_url_or_phone=target_url,
        artifact_path=detail_path,
        provenance="observed",
        fields_disclosed=fields_disclosed,
    )


# --- QuoteResult builder -------------------------------------------------------


def _build_quote_result(
    record: MarketRecord,
    *,
    status: Status,
    is_exact_quote: bool,
    failure_reason: str | None,
    next_action: str | None,
    evidence: EvidenceRecord,
    confidence: Literal["high", "medium", "low"],
    price: PriceInfo | None = None,
    coverage_returned: dict[str, Any] | None = None,
    variance: list[str] | None = None,
    quote_reference_id: str | None = None,
    effective_date: date | None = None,
) -> QuoteResult:
    return QuoteResult(
        source=QuoteSource(
            registry_id=record.registry_id,
            brand_or_program=record.brand_or_program,
            legal_underwriter=record.legal_underwriter,
            insurer_group=record.insurer_group,
            licensed_intermediary=record.licensed_intermediary,
            distinct_rate_source_id=record.distinct_rate_source_id,
        ),
        outcome=QuoteOutcome(
            status=status,
            is_exact_quote=is_exact_quote,
            failure_reason=failure_reason,
            next_action=next_action,
        ),
        coverage=CoverageComparison(
            requested={},
            returned=coverage_returned or {},
            variance_from_benchmark=variance or [],
        ),
        discounts=DiscountInfo(),
        validity=ValidityInfo(
            quote_reference_id=quote_reference_id,
            effective_date=effective_date,
            expiry_date=None,
            verification_may_change_premium=not is_exact_quote,
        ),
        evidence=EvidenceInfo(
            timestamp=evidence.timestamp,
            source_url_or_phone=evidence.source_url_or_phone,
            evidence_artifact=evidence.artifact_path,
            evidence_hash=evidence.evidence_hash,
        ),
        confidence=confidence,
        privacy=PrivacyInfo(fields_disclosed=evidence.fields_disclosed, consent_receipt_id=None, retention_deadline=None),
        price=price,
    )


# --- gate -> status mapping ----------------------------------------------------

_GATE_STATUS: dict[gates.GateKind, Status] = {
    "captcha_or_bot_check": Status.BLOCKED,
    "login_or_account_required": Status.BLOCKED,
    "geo_or_region_block": Status.BLOCKED,
    "site_unavailable": Status.UNREACHABLE,
    "hard_ineligibility": Status.INELIGIBLE,
    "identity_verification": Status.MANUAL_HANDOFF,
    "declaration_attestation": Status.MANUAL_HANDOFF,
    "consent_or_terms_required": Status.MANUAL_HANDOFF,
    "payment_or_binding_step": Status.MANUAL_HANDOFF,
}


def _coverage_status(extraction: dict[str, Any], benchmark: CoverageBenchmark) -> tuple[Status, list[str]]:
    variance: list[str] = []
    if extraction.get("liability_limit") != benchmark.liability_limit:
        variance.append(
            f"liability_limit: requested {benchmark.liability_limit}, returned {extraction.get('liability_limit')}"
        )
    if extraction.get("dcpd_included") != benchmark.dcpd_included:
        variance.append(f"dcpd_included: requested {benchmark.dcpd_included}, returned {extraction.get('dcpd_included')}")
    if extraction.get("collision_deductible") != benchmark.collision_deductible:
        variance.append(
            f"collision_deductible: requested {benchmark.collision_deductible}, "
            f"returned {extraction.get('collision_deductible')}"
        )
    if extraction.get("comprehensive_deductible") != benchmark.comprehensive_deductible:
        variance.append(
            f"comprehensive_deductible: requested {benchmark.comprehensive_deductible}, "
            f"returned {extraction.get('comprehensive_deductible')}"
        )
    if not extraction.get("is_firm_price", True):
        return Status.ESTIMATE_ONLY, variance
    return (Status.QUOTED_NON_COMPARABLE if variance else Status.QUOTED_COMPARABLE), variance


# --- the real (LLM-driving) attempt runner — never exercised by tests --------


@dataclass
class AttemptOutcome:
    ended_via: Literal["done", "halt", "budget"]
    final_result: str | None
    steps_used: int


def _public_field_facts(profile: IntakeProfile) -> list[tuple[str, str]]:
    """Every non-sensitive IntakeProfile field that has a real value, as
    (dotted_name, value) pairs — the ONLY values fill_public may ever be
    asked to type. Sensitive fields (VaultRef-typed) are excluded by
    construction via schemas.sensitive_fields(), the same helper vault.py
    and intake.py use to draw the identical line, so this list can never
    accidentally include a vault token in place of a real fact.

    This exists because the agent was previously told WHICH categories of
    field to fill via fill_public (vehicle make/model/year, city, use type)
    but never given the actual values anywhere in its context — with no
    grounding, it fabricated plausible-sounding ones. This function is what
    closes that gap: the task prompt embeds its output verbatim.
    """
    groups: list[tuple[str, Any]] = [
        ("identity", profile.identity),
        ("licence", profile.licence),
        ("vehicle", profile.vehicle),
        ("address", profile.address),
        ("coverage_benchmark", profile.coverage_benchmark),
        ("contact", profile.contact),
        ("use", profile.use),
        ("history", profile.history),
    ]
    facts: list[tuple[str, str]] = []
    for group_name, submodel in groups:
        if submodel is None:
            continue
        sensitive_names = sensitive_fields(type(submodel))
        for field_name, info in type(submodel).model_fields.items():
            if field_name in sensitive_names:
                continue
            value = getattr(submodel, field_name)
            if value is None or value == [] or value == {}:
                continue
            key = info.alias or field_name
            facts.append((f"{group_name}.{key}", str(value)))
    return facts


def _build_task_prompt(
    target_url: str, profile: IntakeProfile, *, extra_task_instructions: str | None = None
) -> str:
    facts = _public_field_facts(profile)
    facts_block = "\n".join(f"  {name} = {value}" for name, value in facts) or "  (none on file)"
    extra_block = f"\n\n{extra_task_instructions}" if extra_task_instructions else ""
    return (
        f"You are filling out an Ontario private-passenger auto insurance quote form "
        f"starting at {target_url}.\n\n"
        "PROFILE FACTS — the ONLY values you may type into a non-sensitive field. Never "
        "invent, guess, or substitute a plausible-sounding value for anything not listed "
        "here, even to satisfy a field that appears required:\n"
        f"{facts_block}\n\n"
        "Use fill_public(value, element_index) for a non-sensitive field ONLY when the "
        "field is asking for one of the facts above — pass that exact value, never a "
        "paraphrase or a value you made up. If a non-sensitive field on the page has no "
        "matching fact above, leave it blank rather than fabricate one. fill_public will "
        "itself refuse identity-shaped fields (name, licence, date of birth, address, "
        "phone, email, VIN) even if you try — those always go through fill_sensitive.\n\n"
        "If a field is presented as clickable tiles, cards, or buttons representing "
        "discrete choices — not a text box or a native dropdown — use "
        "select_choice(label, element_index) to click the option matching a profile "
        "fact above, instead of trying to type into it.\n\n"
        "Use fill_sensitive(field_name, element_index) for sensitive fields — pass ONLY "
        "the field name (e.g. legal_name, licence_number, date_of_birth, vin, email, "
        "mobile, street, postal_code), never a value. If the site asks for street number "
        "and street name as two separate fields instead of one combined street field, use "
        "street_number and street_name instead of street. If it asks for first and last "
        "name as two separate fields instead of one combined name field, use first_name "
        "and last_name instead of legal_name. You never see the real value; it "
        "is injected automatically. Never fabricate a sensitive value yourself.\n\n"
        "If you encounter any of the following, call halt(gate_kind, reason) immediately "
        "and do not proceed past it: a request to log in or create an account; a CAPTCHA "
        "or bot check; a consent or terms checkbox requiring personal affirmation; a "
        "request to verify your identity, licence, or driving record; a declaration or "
        "attestation you must personally confirm; any payment or billing step.\n\n"
        "If you reach a page showing a final price for this quote, call done with "
        "success=True and text set to a JSON object (as a string) with keys: "
        "annual_premium (number), is_firm_price (true for a firm quote, false for an "
        "indicative estimate), liability_limit (number), dcpd_included (bool), "
        "collision_deductible (number), comprehensive_deductible (number), "
        "effective_date (YYYY-MM-DD or null), quote_reference_id (string or null). "
        "Only call done once you can see an actual price on the page — never fabricate one."
        f"{extra_block}"
    )


async def _default_agent_runner(
    *,
    browser_session: BrowserSession,
    tools: Any,
    sensitive_data: dict[str, str],
    hook: Any,
    agent_box: list[Any],
    target_url: str,
    max_steps: int,
    timeout_s: float,
    profile: IntakeProfile,
    extra_task_instructions: str | None = None,
) -> AttemptOutcome:
    llm = ChatAnthropic(model=os.environ["EXECUTOR_MODEL"])
    agent = Agent(
        task=_build_task_prompt(target_url, profile, extra_task_instructions=extra_task_instructions),
        llm=llm,
        tools=tools,
        browser_session=browser_session,
        use_vision=True,
        sensitive_data=sensitive_data,
        register_new_step_callback=hook,
    )
    agent_box.append(agent)
    history = await asyncio.wait_for(agent.run(max_steps=max_steps), timeout=timeout_s)
    steps_used = history.number_of_steps()
    if not history.is_done():
        return AttemptOutcome(ended_via="budget", final_result=None, steps_used=steps_used)
    action_names = history.action_names()
    ended_via = "halt" if action_names and action_names[-1] == "halt" else "done"
    return AttemptOutcome(ended_via=ended_via, final_result=history.final_result(), steps_used=steps_used)


# --- run_route ------------------------------------------------------------------


def _resolve_headless(headless: bool) -> bool:
    """HEADLESS env var overrides the passed-in default when set (any of
    "0"/"false"/"no"/"" means show a visible window); unset leaves `headless`
    untouched, so tests and the batch (which never set it) are unaffected."""
    raw = os.environ.get("HEADLESS")
    if raw is None:
        return headless
    return raw.strip().lower() not in ("0", "false", "no", "")


class _RetryAttempt(Exception):
    """Internal control-flow signal: this attempt failed transiently and is
    eligible for the single bounded retry. Never escapes run_route().
    """

    def __init__(self, exc: BaseException) -> None:
        super().__init__(str(exc))
        self.exc = exc


async def _run_single_attempt(
    *,
    record: MarketRecord,
    profile: IntakeProfile,
    run_id: str,
    attempt_number: int,
    target_url: str,
    max_steps: int,
    timeout_s: float,
    evidence_root: Path,
    vault_path: Path,
    vault_key: str | None,
    agent_runner: Any,
    headless: bool = True,
    max_attempts: int = 2,
    extra_task_instructions: str | None = None,
) -> QuoteResult:
    """Runs one browser attempt end to end and returns a terminal
    QuoteResult, or raises `_RetryAttempt` if (and only if) this was attempt
    1 and the failure was transient. The browser session for this attempt is
    ALWAYS stopped before this function returns or raises, via `finally` —
    no code path leaks a browser process.

    `keep_alive=True` here is load-bearing, not cosmetic: browser-use's own
    `Agent.run()` tears the browser down itself in its `finally` clause (via
    `Agent.close()` -> `browser_session.kill()`) unless the profile it was
    given has `keep_alive=True` — and it does this INSIDE `agent_runner()`,
    before control ever returns here. Without it, a gate hit (which calls
    `agent.stop()` from the step hook, which ends `agent.run()`'s loop) kills
    the session before the `write_evidence(detail)` call below ever runs,
    so `capture_evidence_screenshot` always fails with a dead CDP client —
    exactly the failure mode seen in a real run's capture_failure.json
    ("Root CDP client not initialized"). This function's own `finally:
    await browser_session.stop()` remains the single place responsible for
    teardown, and it only runs after evidence capture has already happened.
    """
    sensitive_data: dict[str, str] = {}
    gate_box: list[gates.GateHit] = []
    agent_box: list[Any] = []
    tools = browser_ops.build_tools(profile, sensitive_data, vault_path=vault_path, vault_key=vault_key)
    browser_session = BrowserSession(
        browser_profile=BrowserProfile(headless=_resolve_headless(headless), keep_alive=True)
    )
    started = time.monotonic()
    outcome: AttemptOutcome | None = None
    attempt_exception: BaseException | None = None

    async def write_evidence(detail: dict[str, Any]) -> EvidenceRecord:
        return await _write_attempt_evidence(
            record=record,
            profile=profile,
            run_id=run_id,
            attempt_number=attempt_number,
            browser_session=browser_session,
            sensitive_data=sensitive_data,
            target_url=target_url,
            detail=detail,
            evidence_root=evidence_root,
            vault_path=vault_path,
            vault_key=vault_key,
        )

    try:
        try:
            await browser_session.start()
            page = await browser_session.must_get_current_page()
            await page.goto(target_url)
            # Confirm the first page actually rendered before handing off to
            # the agent loop — this, not the overall budget wait_for inside
            # agent_runner, is what "timeout before first paint" means for
            # retry purposes; both would otherwise raise the same
            # TimeoutError with no way to tell them apart.
            await asyncio.wait_for(page.evaluate("() => document.readyState"), timeout=nav_timeout_guess(timeout_s))

            hook = browser_ops.make_step_hook(
                profile, gate_box, agent_box, browser_session, vault_path=vault_path, vault_key=vault_key
            )
            outcome = await agent_runner(
                browser_session=browser_session,
                tools=tools,
                sensitive_data=sensitive_data,
                hook=hook,
                agent_box=agent_box,
                target_url=target_url,
                max_steps=max_steps,
                timeout_s=timeout_s,
                profile=profile,
                extra_task_instructions=extra_task_instructions,
            )
        except Exception as exc:
            # Not BaseException: KeyboardInterrupt/SystemExit must propagate,
            # not be swallowed and reported as a market outcome.
            attempt_exception = exc

        detail: dict[str, Any] = {"attempt_number": attempt_number, "target_url": target_url}

        # A deterministic gate hit is authoritative regardless of how the
        # attempt otherwise ended (exception, budget, or a voluntary halt on
        # the same page) — checked first, before any other interpretation.
        # But it is only trustworthy if it still describes the page the run
        # actually ended on: a GateHit recorded early and never invalidated
        # by browser_ops.make_step_hook's own url-match check (e.g. because
        # the agent kept stepping past agent.stop() before it took effect)
        # would otherwise be reported with a screenshot of a completely
        # different page — a run must never report a gate detected on a
        # page it wasn't on when it stopped. current_url is None (fetch
        # failed) is treated the same as a mismatch: fail closed rather than
        # trust an unverifiable hit.
        gate_hit = gate_box[0] if gate_box else None
        if gate_hit is not None:
            current_url = await browser_ops.get_current_url(browser_session)
            if current_url != gate_hit.url:
                detail["discarded_stale_gate_hit"] = {
                    "kind": gate_hit.kind,
                    "recorded_url": gate_hit.url,
                    "recorded_step": gate_hit.step_number,
                    "final_url": current_url,
                }
                gate_hit = None

        if gate_hit is not None:
            hit = gate_hit
            status = _GATE_STATUS[hit.kind]
            # Best-effort: bring the matched text on screen before capture so
            # the evidence screenshot actually shows what the reason claims —
            # the screenshot is a viewport capture, and a correctly-scoped
            # active-region hit can still be below the fold. Never claim
            # corroboration we don't have.
            scrolled = await browser_ops.scroll_text_into_view(browser_session, hit.matched_text)
            reason = f"{hit.kind}: {hit.evidence_snippet}"
            if not scrolled:
                reason += (
                    " (evidence screenshot may not show this text — it could not be "
                    "located and scrolled into view before capture)"
                )
            if outcome is not None and outcome.ended_via == "halt" and outcome.final_result:
                reason += f" (model also called halt: {outcome.final_result})"
            detail["gate_kind"] = hit.kind
            detail["evidence_snippet"] = hit.evidence_snippet
            detail["scrolled_to_evidence"] = scrolled
            evidence = await write_evidence(detail)
            return _build_quote_result(
                record,
                status=status,
                is_exact_quote=False,
                failure_reason=reason,
                next_action="human review required" if status == Status.MANUAL_HANDOFF else None,
                evidence=evidence,
                confidence="low",
            )

        if attempt_exception is not None:
            elapsed = time.monotonic() - started
            transient = is_transient(attempt_exception)
            early_timeout = isinstance(attempt_exception, TimeoutError) and elapsed < nav_timeout_guess(timeout_s)
            detail["exception_type"] = type(attempt_exception).__name__
            detail["exception_message"] = str(attempt_exception)
            detail["elapsed_seconds"] = elapsed
            if (transient or early_timeout) and attempt_number < max_attempts:
                # Every attempt writes its own evidence, including one that
                # gets retried — the retry never overwrites this artifact.
                await write_evidence({**detail, "retrying": True})
                raise _RetryAttempt(attempt_exception)
            evidence = await write_evidence(detail)
            return _build_quote_result(
                record,
                status=Status.UNREACHABLE,
                is_exact_quote=False,
                failure_reason=(
                    f"unreachable: {type(attempt_exception).__name__}: {attempt_exception} "
                    f"(attempt {attempt_number}, {elapsed:.1f}s elapsed)"
                ),
                next_action="retry later",
                evidence=evidence,
                confidence="low",
            )

        assert outcome is not None  # no exception, no gate -> outcome is always set

        if outcome.ended_via == "budget":
            detail["steps_used"] = outcome.steps_used
            evidence = await write_evidence(detail)
            return _build_quote_result(
                record,
                status=Status.UNREACHABLE,
                is_exact_quote=False,
                failure_reason=f"budget exhausted: {outcome.steps_used} steps used, no determination reached",
                next_action="retry with a higher step/time budget",
                evidence=evidence,
                confidence="low",
            )

        if outcome.ended_via == "halt":
            # halt() with no corresponding GateHit (gate_box empty, already
            # checked above) — fixed unreachable status; the model's named
            # gate_kind is recorded as text only, never used to pick a status.
            reason = "unreachable (voluntary halt, no independent gate match)"
            payload: dict[str, Any] = {}
            if outcome.final_result:
                try:
                    payload = json.loads(outcome.final_result)
                except (json.JSONDecodeError, TypeError):
                    payload = {"reason": outcome.final_result}
            redacted_reason = redact_text(
                str(payload.get("reason", "")), profile, vault_path=vault_path, vault_key=vault_key
            )
            named_kind = payload.get("gate_kind", "unspecified")
            detail["halt_gate_kind_named_by_model"] = named_kind
            detail["halt_reason"] = redacted_reason
            evidence = await write_evidence(detail)
            return _build_quote_result(
                record,
                status=Status.UNREACHABLE,
                is_exact_quote=False,
                failure_reason=f"{reason}: model named gate_kind={named_kind!r}, reason={redacted_reason!r}",
                next_action="manual review of this run's evidence",
                evidence=evidence,
                confidence="low",
            )

        # ended_via == "done"
        try:
            extraction = json.loads(outcome.final_result) if outcome.final_result else {}
        except (json.JSONDecodeError, TypeError):
            detail["unparseable_final_result"] = True
            evidence = await write_evidence(detail)
            return _build_quote_result(
                record,
                status=Status.UNREACHABLE,
                is_exact_quote=False,
                failure_reason="agent called done but its result was not parseable structured data",
                next_action="manual review of this run's evidence",
                evidence=evidence,
                confidence="low",
            )

        status, variance = _coverage_status(extraction, profile.coverage_benchmark)
        detail["extraction"] = extraction
        evidence = await write_evidence(detail)
        price = None
        if extraction.get("annual_premium") is not None:
            price = PriceInfo(annual_premium=extraction["annual_premium"])
        effective_date_value = None
        if extraction.get("effective_date"):
            try:
                effective_date_value = date.fromisoformat(extraction["effective_date"])
            except ValueError:
                effective_date_value = None
        return _build_quote_result(
            record,
            status=status,
            is_exact_quote=status != Status.ESTIMATE_ONLY,
            failure_reason=None,
            next_action=None,
            evidence=evidence,
            confidence="high" if status == Status.QUOTED_COMPARABLE else "medium",
            price=price,
            coverage_returned=extraction,
            variance=variance,
            quote_reference_id=extraction.get("quote_reference_id"),
            effective_date=effective_date_value,
        )
    finally:
        await browser_session.stop()


async def run_route(
    market_id: str,
    profile: IntakeProfile,
    *,
    live: bool = False,
    fixture_url: str | None = None,
    live_url_override: str | None = None,
    max_steps: int | None = None,
    timeout_s: float | None = None,
    max_attempts: int = 2,
    extra_task_instructions: str | None = None,
    headless: bool = True,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
    db_path: Path = registry.DB_PATH,
    evidence_root: Path = EVIDENCE_ROOT,
    agent_runner: Any = _default_agent_runner,
) -> QuoteResult:
    """`live_url_override` starts a live run at a specific quote-flow URL
    instead of the registry row's `quote_url` (typically its marketing
    homepage) — the route is still looked up by `market_id` for every other
    purpose (evidence, dedupe, status write-back). `max_attempts` defaults to
    2 (the standing bounded-attempt policy: 1 attempt + 1 retry on transient
    technical error only, per CLAUDE.md); pass 1 to disable the retry for a
    diagnostic run where re-attempting would just re-burn the same budget on
    the same wall, not recover from a transient blip.
    """
    max_steps = max_steps if max_steps is not None else _default_max_steps()
    timeout_s = timeout_s if timeout_s is not None else _default_timeout_s()

    record = registry.get_record(market_id, db_path=db_path)
    if record is None:
        raise ValueError(f"no registry row for market_id {market_id!r}")

    run_id = _new_run_id()

    # Channel availability, not the registry's current status — a route is
    # attempted every time run_route is called for it, including re-runs of
    # a previously-terminal route.
    if record.quote_url is None:
        evidence = _write_derived_channel_evidence(
            record, profile, run_id, evidence_root=evidence_root, vault_path=vault_path, vault_key=vault_key
        )
        status = Status.CALLBACK_REQUIRED if record.public_phone_route else Status.MANUAL_HANDOFF
        return _build_quote_result(
            record,
            status=status,
            is_exact_quote=False,
            failure_reason=(
                "no automatable web channel on this registry row; no page was loaded "
                "and no contact was made with this market."
            ),
            next_action=("call " + record.public_phone_route if record.public_phone_route else "identify a channel"),
            evidence=evidence,
            confidence="low",
        )

    if live:
        target_url = live_url_override or record.quote_url
    else:
        if fixture_url is None:
            raise ValueError("fixture mode requires fixture_url")
        target_url = fixture_url

    _write_run_start_evidence(record, run_id, profile, evidence_root=evidence_root)

    last_exception: BaseException | None = None
    for attempt_number in range(1, max_attempts + 1):
        try:
            return await _run_single_attempt(
                record=record,
                profile=profile,
                run_id=run_id,
                attempt_number=attempt_number,
                target_url=target_url,
                max_steps=max_steps,
                timeout_s=timeout_s,
                evidence_root=evidence_root,
                vault_path=vault_path,
                vault_key=vault_key,
                agent_runner=agent_runner,
                headless=headless,
                max_attempts=max_attempts,
                extra_task_instructions=extra_task_instructions,
            )
        except _RetryAttempt as retry:
            last_exception = retry.exc
            continue

    # All attempts exhausted transiently.
    evidence = await _write_attempt_evidence(
        record=record,
        profile=profile,
        run_id=run_id,
        attempt_number=max_attempts,
        browser_session=None,
        sensitive_data={},
        target_url=target_url,
        detail={"both_attempts_transient": True, "last_exception": str(last_exception)},
        evidence_root=evidence_root,
        vault_path=vault_path,
        vault_key=vault_key,
    )
    return _build_quote_result(
        record,
        status=Status.UNREACHABLE,
        is_exact_quote=False,
        failure_reason=f"unreachable after {max_attempts} attempt(s): {last_exception}",
        next_action="retry later",
        evidence=evidence,
        confidence="low",
    )


# --- CLI -----------------------------------------------------------------------


def _load_profile_for_cli() -> IntakeProfile:
    from allquote import intake

    profile = intake.load_profile()
    if profile is None:
        raise RuntimeError(
            f"no stored intake profile at {intake.PROFILE_PATH} — submit the intake form "
            "first (make intake) before running the executor"
        )
    return profile


def _cmd_run(args: argparse.Namespace) -> int:
    if args.live:
        record = registry.get_record(args.market_id)
        if record is None or record.quote_url is None:
            print(f"cannot run --live: no quote_url on record for {args.market_id!r}", file=sys.stderr)
            return 1
        print(f"LIVE RUN target: {record.quote_url}")
        confirmation = input("Continue with a real run against this site? [y/N] ")
        if confirmation.strip().lower() != "y":
            print("aborted", file=sys.stderr)
            return 1

    profile = _load_profile_for_cli()
    result = asyncio.run(
        run_route(
            args.market_id,
            profile,
            live=args.live,
            fixture_url=args.fixture_url,
            max_steps=args.max_steps,
            timeout_s=args.timeout_seconds,
            headless=not args.headed,
        )
    )
    print(result.model_dump_json(indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m allquote.executor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--market-id", required=True)
    run_parser.add_argument("--live", action="store_true")
    run_parser.add_argument("--fixture-url", default=None, help="local fixture URL (non-live mode)")
    run_parser.add_argument("--max-steps", type=int, default=_default_max_steps())
    run_parser.add_argument("--timeout-seconds", type=float, default=_default_timeout_s())
    run_parser.add_argument(
        "--headed",
        action="store_true",
        help="show the browser window instead of running headless (default: headless, for demo runs)",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
