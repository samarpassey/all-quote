"""Tests for allquote.executor.run_route(). Zero LLM API calls: run_route's
`agent_runner` parameter is always replaced with a scripted fake here, never
the real ChatAnthropic-backed one — which is never constructed, let alone
invoked. Every navigation stays on 127.0.0.1 via tests/fixture_server.py.
"""

import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from allquote import executor, gates, registry
from allquote.executor import AttemptOutcome
from allquote.schemas import Status
from tests.fixtures import build_market_record, build_vaulted_profile


def _seed_registry(db_path, record):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS market_records (registry_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    conn.execute(
        "INSERT INTO market_records (registry_id, payload) VALUES (?, ?)",
        (record.registry_id, record.model_dump_json()),
    )
    conn.commit()
    conn.close()


class _FakeAgent:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


async def _tick_hook(hook, url: str) -> None:
    await hook(SimpleNamespace(url=url), None, 1)


def _gate_page_driver_factory():
    """A scripted driver that just lets the (real) step hook observe
    whatever page run_route already navigated to, then returns an
    irrelevant "budget" outcome — irrelevant because run_route checks
    gate_box first, before ever looking at the outcome.
    """

    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        agent_box.append(_FakeAgent())
        await _tick_hook(hook, target_url)
        return AttemptOutcome(ended_via="budget", final_result=None, steps_used=1)

    return driver


def _benchmark_extraction(**overrides) -> dict:
    extraction = {
        "annual_premium": 1234.56,
        "is_firm_price": True,
        "liability_limit": 2_000_000,
        "dcpd_included": True,
        "collision_deductible": 1000,
        "comprehensive_deductible": 1000,
        "effective_date": "2026-08-15",
        "quote_reference_id": "SONNET-DEMO-0001",
    }
    extraction.update(overrides)
    return extraction


def _done_driver_factory(extraction: dict):
    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        agent_box.append(_FakeAgent())
        await _tick_hook(hook, target_url)
        return AttemptOutcome(ended_via="done", final_result=json.dumps(extraction), steps_used=1)

    return driver


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def market_record(tmp_path, fixture_server):
    record = build_market_record(
        registry_id="test-route-executor",
        quote_url=fixture_server.url_for("happy_path_step1.html"),
        public_phone_route=None,
    )
    db_path = tmp_path / "registry.db"
    _seed_registry(db_path, record)
    return record, db_path


@pytest.fixture
def vaulted_profile(tmp_path):
    vault_path = tmp_path / "vault.enc"
    profile, plaintext = build_vaulted_profile(vault_path, "test-key")
    return profile, plaintext, vault_path


# --- gate fixtures -> status mapping -----------------------------------------


@pytest.mark.parametrize(
    "fixture_name,expected_status",
    [
        ("consent_wall.html", Status.MANUAL_HANDOFF),
        ("identity_gate.html", Status.MANUAL_HANDOFF),
        ("captcha.html", Status.BLOCKED),
        ("maintenance.html", Status.UNREACHABLE),
        ("ineligible.html", Status.INELIGIBLE),
    ],
)
def test_gate_fixture_status_mapping(fixture_name, expected_status, tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for(fixture_name),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=_gate_page_driver_factory(),
        )

    result = _run(body())
    assert result.outcome.status == expected_status
    assert result.evidence.evidence_artifact


# --- success path -------------------------------------------------------------


def test_happy_path_quoted_comparable(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step3.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=_done_driver_factory(_benchmark_extraction()),
        )

    result = _run(body())
    assert result.outcome.status == Status.QUOTED_COMPARABLE
    assert result.outcome.is_exact_quote is True
    assert result.price.annual_premium == 1234.56
    assert result.coverage.variance_from_benchmark == []


def test_happy_path_quoted_non_comparable_on_deductible_mismatch(
    tmp_path, fixture_server, market_record, vaulted_profile
):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step3.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=_done_driver_factory(_benchmark_extraction(collision_deductible=500)),
        )

    result = _run(body())
    assert result.outcome.status == Status.QUOTED_NON_COMPARABLE
    assert any("collision_deductible" in v for v in result.coverage.variance_from_benchmark)


def test_estimate_only_when_not_a_firm_price(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step3.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=_done_driver_factory(_benchmark_extraction(is_firm_price=False)),
        )

    result = _run(body())
    assert result.outcome.status == Status.ESTIMATE_ONLY
    assert result.outcome.is_exact_quote is False


# --- halt-status rule ----------------------------------------------------------


def test_halt_without_independent_gate_maps_to_unreachable(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        agent_box.append(_FakeAgent())
        # Benign page -- the real hook finds nothing.
        await _tick_hook(hook, target_url)
        payload = json.dumps({"gate_kind": "captcha_or_bot_check", "reason": "looks suspicious to me"})
        return AttemptOutcome(ended_via="halt", final_result=payload, steps_used=1)

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step1.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=driver,
        )

    result = _run(body())
    assert result.outcome.status == Status.UNREACHABLE
    assert result.outcome.status != Status.BLOCKED
    assert "captcha_or_bot_check" in result.outcome.failure_reason


def test_halt_with_independent_gate_detector_wins(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        agent_box.append(_FakeAgent())
        # captcha.html -- the real hook DOES find something here.
        await _tick_hook(hook, target_url)
        # Model also calls halt, naming a DIFFERENT gate_kind than what the
        # detector actually found -- the detector must win regardless.
        payload = json.dumps({"gate_kind": "login_or_account_required", "reason": "looked like a login wall"})
        return AttemptOutcome(ended_via="halt", final_result=payload, steps_used=1)

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("captcha.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=driver,
        )

    result = _run(body())
    assert result.outcome.status == Status.BLOCKED  # captcha_or_bot_check's mapping, not login's
    assert "captcha_or_bot_check" in result.outcome.failure_reason


# --- budget exhaustion ---------------------------------------------------------


def test_budget_exhaustion_maps_to_unreachable_not_success(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        agent_box.append(_FakeAgent())
        await _tick_hook(hook, target_url)
        return AttemptOutcome(ended_via="budget", final_result=None, steps_used=max_steps)

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step1.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=driver,
        )

    result = _run(body())
    assert result.outcome.status == Status.UNREACHABLE
    assert result.outcome.status not in (Status.QUOTED_COMPARABLE, Status.QUOTED_NON_COMPARABLE, Status.ESTIMATE_ONLY)


# --- retry / is_transient integration ------------------------------------------


def test_transient_failure_retries_and_second_attempt_succeeds(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile
    calls = {"n": 0}

    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("simulated transient failure on attempt 1")
        agent_box.append(_FakeAgent())
        await _tick_hook(hook, target_url)
        return AttemptOutcome(ended_via="done", final_result=json.dumps(_benchmark_extraction()), steps_used=1)

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step3.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=driver,
        )

    result = _run(body())
    assert calls["n"] == 2
    assert result.outcome.status == Status.QUOTED_COMPARABLE
    run_id_dir = list((tmp_path / "evidence").glob("*"))
    # Both attempt-1 and attempt-2 evidence subdirectories exist, and the
    # first attempt's artifacts were never overwritten by the retry.
    matching = [d for d in run_id_dir if (d / "attempt-1").exists() and (d / "attempt-2").exists()]
    assert matching, "expected a run directory with both attempt-1 and attempt-2 subdirectories"


def test_non_transient_failure_does_not_retry(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile
    calls = {"n": 0}

    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        calls["n"] += 1
        raise ValueError("not a transient failure")

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step1.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=driver,
        )

    result = _run(body())
    assert calls["n"] == 1  # never retried
    assert result.outcome.status == Status.UNREACHABLE


# --- quote_url is None / provenance --------------------------------------------


def test_no_quote_url_with_phone_route_is_callback_required_and_derived(tmp_path, fixture_server, vaulted_profile):
    record = build_market_record(
        registry_id="test-route-phone-only", quote_url=None, public_phone_route="1-800-555-0100"
    )
    db_path = tmp_path / "registry.db"
    _seed_registry(db_path, record)
    profile, _, vault_path = vaulted_profile

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
        )

    result = _run(body())
    assert result.outcome.status == Status.CALLBACK_REQUIRED
    assert "no page was loaded and no contact was made with this market" in result.outcome.failure_reason
    sidecar_path = result.evidence.evidence_artifact + ".evidence.json"
    with open(sidecar_path) as f:
        sidecar = json.load(f)
    assert sidecar["provenance"] == "derived"


def test_no_quote_url_no_phone_route_is_manual_handoff(tmp_path, vaulted_profile):
    record = build_market_record(registry_id="test-route-no-channel", quote_url=None, public_phone_route=None)
    db_path = tmp_path / "registry.db"
    _seed_registry(db_path, record)
    profile, _, vault_path = vaulted_profile

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
        )

    result = _run(body())
    assert result.outcome.status == Status.MANUAL_HANDOFF


def test_browser_attempt_evidence_is_observed_provenance(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step3.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=_done_driver_factory(_benchmark_extraction()),
        )

    result = _run(body())
    sidecar_path = result.evidence.evidence_artifact + ".evidence.json"
    with open(sidecar_path) as f:
        sidecar = json.load(f)
    assert sidecar["provenance"] == "observed"


# --- evidence-capture failure never destroys the result -----------------------


def test_screenshot_capture_failure_falls_back_and_preserves_status(
    tmp_path, fixture_server, market_record, vaulted_profile, monkeypatch
):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile

    async def raising_capture(*args, **kwargs):
        raise RuntimeError("session closed")

    monkeypatch.setattr("allquote.browser_ops.capture_evidence_screenshot", raising_capture)

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step3.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=_done_driver_factory(_benchmark_extraction()),
        )

    result = _run(body())
    assert result.outcome.status == Status.QUOTED_COMPARABLE
    assert result.evidence.evidence_artifact
    sidecar_path = result.evidence.evidence_artifact + ".evidence.json"
    with open(sidecar_path) as f:
        sidecar = json.load(f)
    assert sidecar["kind"] == "document"  # fell back from screenshot to a text record


# --- is_transient() -------------------------------------------------------------


def test_is_transient_true_cases():
    assert executor.is_transient(ConnectionError("refused"))
    assert executor.is_transient(ConnectionRefusedError())
    import socket

    assert executor.is_transient(socket.gaierror("dns failure"))
    assert executor.is_transient(TimeoutError("timed out"))
    assert executor.is_transient(RuntimeError("x"), http_status=500)
    assert executor.is_transient(RuntimeError("x"), http_status=503)
    assert executor.is_transient(RuntimeError("x"), http_status=599)


def test_is_transient_false_cases():
    assert not executor.is_transient(ValueError("bad input"))
    assert not executor.is_transient(KeyError("missing"))
    assert not executor.is_transient(RuntimeError("x"), http_status=404)
    assert not executor.is_transient(RuntimeError("x"), http_status=200)
    assert not executor.is_transient(RuntimeError("generic runtime error"))


# --- CLI: --live gating ---------------------------------------------------------


def test_live_requires_flag_and_confirmation(tmp_path, fixture_server, market_record, monkeypatch, capsys):
    record, db_path = market_record

    # Simulate declining the confirmation prompt.
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    called = {"run_route": False}

    async def fake_run_route(*args, **kwargs):
        called["run_route"] = True
        raise AssertionError("run_route should not be called after declining confirmation")

    monkeypatch.setattr(executor, "run_route", fake_run_route)
    monkeypatch.setattr(executor.registry, "get_record", lambda market_id, db_path=None: record)

    rc = executor.main(["run", "--market-id", record.registry_id, "--live"])
    assert rc == 1
    assert called["run_route"] is False


def test_non_live_never_touches_the_real_quote_url(tmp_path, fixture_server, market_record, vaulted_profile):
    record, db_path = market_record
    profile, _, vault_path = vaulted_profile
    navigated_urls = []

    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        navigated_urls.append(target_url)
        agent_box.append(_FakeAgent())
        await _tick_hook(hook, target_url)
        return AttemptOutcome(ended_via="done", final_result=json.dumps(_benchmark_extraction()), steps_used=1)

    fixture_target = fixture_server.url_for("happy_path_step3.html")

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_target,
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=tmp_path / "evidence",
            agent_runner=driver,
        )

    _run(body())
    assert navigated_urls == [fixture_target]
    assert all(url.startswith("http://127.0.0.1:") for url in navigated_urls)
    assert record.quote_url not in navigated_urls


# --- sentinel grep: no plaintext survives anywhere on disk ---------------------


def test_sentinel_never_survives_in_any_evidence_artifact(tmp_path, fixture_server, market_record, vaulted_profile):
    """Seeds a known fake licence number into the vault, fills it into a real
    page field (exercising the real CDP typing + redaction pipeline, not a
    shortcut), then recursively greps every file written under evidence_root
    (every EvidenceRecord JSON, every detail.json, the screenshot bytes) for
    that sentinel. It must appear in none of them.
    """
    record, db_path = market_record
    profile, plaintext, vault_path = vaulted_profile
    sentinel = plaintext["licence_number"]
    evidence_root = tmp_path / "evidence"

    async def driver(*, browser_session, tools, sensitive_data, hook, agent_box, target_url, max_steps, timeout_s):
        agent_box.append(_FakeAgent())
        await browser_session.get_browser_state_summary(include_screenshot=False)
        index = await browser_session.get_index_by_id("licence_number")
        await tools.registry.execute_action(
            "fill_sensitive", {"field_name": "licence_number", "element_index": index}, browser_session=browser_session
        )
        await _tick_hook(hook, target_url)
        return AttemptOutcome(ended_via="done", final_result=json.dumps(_benchmark_extraction()), steps_used=1)

    async def body():
        return await executor.run_route(
            record.registry_id,
            profile,
            live=False,
            fixture_url=fixture_server.url_for("happy_path_step2.html"),
            max_steps=3,
            timeout_s=10,
            vault_path=vault_path,
            vault_key="test-key",
            db_path=db_path,
            evidence_root=evidence_root,
            agent_runner=driver,
        )

    result = _run(body())
    assert result.outcome.status in (Status.QUOTED_COMPARABLE, Status.QUOTED_NON_COMPARABLE, Status.ESTIMATE_ONLY)

    sentinel_bytes = sentinel.encode()
    checked_files = 0
    for path in evidence_root.rglob("*"):
        if not path.is_file():
            continue
        checked_files += 1
        content = path.read_bytes()
        assert sentinel_bytes not in content, f"sentinel value leaked into {path}"
    assert checked_files > 0, "expected at least one evidence file to check"

    # And the QuoteResult itself, serialized, must not carry the sentinel.
    assert sentinel not in result.model_dump_json()
