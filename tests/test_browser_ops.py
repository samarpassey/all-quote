"""Real-browser tests for allquote.browser_ops.

Zero LLM API calls: browser_use.Agent is either not constructed at all, or
(for the sensitive_data wiring test) constructed with a stub LLM whose
`ainvoke` raises if ever called, and `agent.run()` is never invoked. Every
navigation stays on 127.0.0.1 via tests/fixture_server.py.

Each test manages its own BrowserSession lifecycle (launch/stop) rather than
sharing one across the module — simpler and fully isolated, at the cost of
one browser launch per test (a few seconds each).
"""

import asyncio
import json
from pathlib import Path

import pytest
from browser_use import Agent, BrowserProfile, BrowserSession
from browser_use.llm.messages import UserMessage
from PIL import Image

from allquote import browser_ops, gates, vault
from allquote.redact import redact_text
from tests.fixtures import build_vaulted_profile


class _FakeLLM:
    model = "fake-model"
    provider = "fake"
    model_name = "fake-model"

    async def ainvoke(self, *args, **kwargs):
        raise RuntimeError("FakeLLM.ainvoke must never be called in this test suite")


class _FakeAgent:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


def _run(coro):
    return asyncio.run(coro)


async def _new_session():
    session = BrowserSession(browser_profile=BrowserProfile(headless=True))
    await session.start()
    return session


async def _index_for(session: BrowserSession, *, id_attr: str) -> int:
    # Populate the selector map (built lazily on first observation) before
    # looking the element up.
    await session.get_browser_state_summary(include_screenshot=False)
    index = await session.get_index_by_id(id_attr)
    if index is None:
        raise AssertionError(f"no element with id={id_attr!r} found in selector map")
    return index


# --- fill_sensitive / fill_public -------------------------------------------


def test_fill_sensitive_types_value_and_registers_in_sensitive_data(fixture_server, tmp_path):
    async def body():
        vault_path = tmp_path / "vault.enc"
        profile, plaintext = build_vaulted_profile(vault_path, "test-key")
        sensitive_data: dict[str, str] = {}
        tools = browser_ops.build_tools(profile, sensitive_data, vault_path=vault_path, vault_key="test-key")

        session = await _new_session()
        try:
            page = await session.must_get_current_page()
            await page.goto(fixture_server.url_for("happy_path_step2.html"))
            index = await _index_for(session, id_attr="licence_number")

            result = await tools.registry.execute_action(
                "fill_sensitive",
                {"field_name": "licence_number", "element_index": index},
                browser_session=session,
            )

            actual_value = await page.evaluate(
                "() => document.getElementById('licence_number').value"
            )
            assert actual_value == plaintext["licence_number"]
            assert sensitive_data["licence_number"] == plaintext["licence_number"]
            assert plaintext["licence_number"] not in (result.extracted_content or "")
        finally:
            await session.stop()

    _run(body())


def test_fill_sensitive_rejects_unknown_field_name(fixture_server, tmp_path):
    async def body():
        vault_path = tmp_path / "vault.enc"
        profile, _ = build_vaulted_profile(vault_path, "test-key")
        tools = browser_ops.build_tools(profile, {}, vault_path=vault_path, vault_key="test-key")

        session = await _new_session()
        try:
            page = await session.must_get_current_page()
            await page.goto(fixture_server.url_for("happy_path_step2.html"))
            index = await _index_for(session, id_attr="licence_number")
            with pytest.raises(RuntimeError):
                await tools.registry.execute_action(
                    "fill_sensitive",
                    {"field_name": "not_a_real_field", "element_index": index},
                    browser_session=session,
                )
        finally:
            await session.stop()

    _run(body())


def test_fill_public_types_value(fixture_server, tmp_path):
    async def body():
        vault_path = tmp_path / "vault.enc"
        profile, _ = build_vaulted_profile(vault_path, "test-key")
        tools = browser_ops.build_tools(profile, {}, vault_path=vault_path, vault_key="test-key")

        session = await _new_session()
        try:
            page = await session.must_get_current_page()
            await page.goto(fixture_server.url_for("happy_path_step1.html"))
            index = await _index_for(session, id_attr="make")
            await tools.registry.execute_action(
                "fill_public",
                {"value": "Testmake", "element_index": index},
                browser_session=session,
            )
            actual = await page.evaluate("() => document.getElementById('make').value")
            assert actual == "Testmake"
        finally:
            await session.stop()

    _run(body())


def test_halt_never_maps_to_a_status_and_carries_reason():
    result = _run(browser_ops.halt("captcha_or_bot_check", "looks like a captcha"))
    assert result.is_done is True
    assert result.success is False
    payload = json.loads(result.extracted_content)
    assert payload["gate_kind"] == "captcha_or_bot_check"
    assert payload["reason"] == "looks like a captcha"


# --- sensitive_data construction-only wiring --------------------------------


def test_sensitive_data_is_the_same_object_agent_holds():
    # No browser, no run(), no API call — Agent construction only.
    sensitive_data: dict[str, str] = {}

    def my_hook(state, output, step):
        pass

    from browser_use import Tools

    agent = Agent(
        task="dummy task",
        llm=_FakeLLM(),
        tools=Tools(),
        sensitive_data=sensitive_data,
        use_vision=True,
        register_new_step_callback=my_hook,
    )

    # (a) identity, not equality. If this ever fails, the whole
    # fill_sensitive -> native-filtering design is broken and must be
    # revisited, not patched around silently.
    assert agent.sensitive_data is sensitive_data

    # (b)
    assert agent.register_new_step_callback is my_hook
    assert agent.settings.use_vision is True

    # (c) the real end-to-end proof: a value written after construction is
    # picked up by browser-use's own filter, not just referentially present.
    sensitive_data["licence_number"] = "SENTINEL-LICENCE-VALUE"
    message = UserMessage(content="the page shows SENTINEL-LICENCE-VALUE in a field")
    filtered = agent._message_manager._filter_sensitive_data(message)
    assert "SENTINEL-LICENCE-VALUE" not in filtered.content
    assert "<secret>licence_number</secret>" in filtered.content


# --- gate step hook ----------------------------------------------------------


class _StateStub:
    def __init__(self, url: str):
        self.url = url


def test_step_hook_calls_stop_exactly_once_and_redacts_snippet(fixture_server, tmp_path):
    async def body():
        vault_path = tmp_path / "vault.enc"
        profile, plaintext = build_vaulted_profile(vault_path, "test-key")
        session = await _new_session()
        try:
            page = await session.must_get_current_page()
            await page.goto(fixture_server.url_for("captcha.html"))

            gate_box: list[gates.GateHit] = []
            agent_box = [_FakeAgent()]
            hook = browser_ops.make_step_hook(
                profile, gate_box, agent_box, session, vault_path=vault_path, vault_key="test-key"
            )

            await hook(_StateStub(fixture_server.url_for("captcha.html")), None, 1)
            assert agent_box[0].stop_calls == 1
            assert len(gate_box) == 1
            assert gate_box[0].kind == "captcha_or_bot_check"

            # First hit wins: a second call (simulating another step) must
            # not process again or call stop() a second time.
            await hook(_StateStub(fixture_server.url_for("captcha.html")), None, 2)
            assert agent_box[0].stop_calls == 1
            assert len(gate_box) == 1
        finally:
            await session.stop()

    _run(body())


def test_step_hook_finds_nothing_on_benign_page(fixture_server, tmp_path):
    async def body():
        vault_path = tmp_path / "vault.enc"
        profile, _ = build_vaulted_profile(vault_path, "test-key")
        session = await _new_session()
        try:
            page = await session.must_get_current_page()
            await page.goto(fixture_server.url_for("happy_path_step1.html"))

            gate_box: list[gates.GateHit] = []
            agent_box = [_FakeAgent()]
            hook = browser_ops.make_step_hook(
                profile, gate_box, agent_box, session, vault_path=vault_path, vault_key="test-key"
            )
            await hook(_StateStub(fixture_server.url_for("happy_path_step1.html")), None, 1)

            assert gate_box == []
            assert agent_box[0].stop_calls == 0
        finally:
            await session.stop()

    _run(body())


def test_step_hook_survives_evaluate_failure_without_crashing():
    # A dead/navigating page's page.evaluate() raises — the hook must skip
    # gate detection for that step, not propagate the exception (which
    # would kill the run).
    class _DeadPage:
        async def evaluate(self, *_args, **_kwargs):
            raise RuntimeError("Target closed")

    class _DeadSession:
        async def must_get_current_page(self):
            return _DeadPage()

    async def body():
        from tests.fixtures import build_intake_profile

        profile = build_intake_profile()
        gate_box: list[gates.GateHit] = []
        agent_box = [_FakeAgent()]
        hook = browser_ops.make_step_hook(profile, gate_box, agent_box, _DeadSession())
        # Must not raise.
        await hook(_StateStub("http://example.invalid"), None, 1)
        assert gate_box == []
        assert agent_box[0].stop_calls == 0

    _run(body())


# --- evidence screenshot -----------------------------------------------------


def test_screenshot_capture_never_writes_raw_bytes_and_boxes_are_black(fixture_server, tmp_path):
    async def body():
        vault_path = tmp_path / "vault.enc"
        profile, plaintext = build_vaulted_profile(
            vault_path, "test-key", postal_code="M5V3A8"
        )
        sentinel = "M5V 3A8"  # deliberately different formatting than stored
        fixture_server.set_placeholder(
            "/summary_plaintext.html", "__SENTINEL_POSTAL__", sentinel
        )

        session = await _new_session()
        try:
            page = await session.must_get_current_page()
            await page.goto(fixture_server.url_for("summary_plaintext.html"))

            # Independent oracle: the sentinel cell's own bounding rect,
            # computed separately from whatever capture_evidence_screenshot
            # does internally.
            oracle_rect_raw = await page.evaluate(
                "() => document.getElementById('postal_code_cell').getBoundingClientRect().toJSON()"
            )
            oracle_rect = json.loads(oracle_rect_raw) if isinstance(oracle_rect_raw, str) else oracle_rect_raw
            device_pixel_ratio_raw = await page.evaluate("() => window.devicePixelRatio")
            device_pixel_ratio = float(device_pixel_ratio_raw)

            destination = tmp_path / "evidence" / "quote_summary.png"
            sensitive_data = {"postal_code": sentinel}

            calls = []
            original_redact_image = browser_ops.redact_image

            def spy_redact_image(image_source, boxes, *, output_path):
                calls.append((image_source, boxes, output_path))
                return original_redact_image(image_source, boxes, output_path=output_path)

            browser_ops.redact_image = spy_redact_image
            try:
                result_path = await browser_ops.capture_evidence_screenshot(
                    session, sensitive_data, destination
                )
            finally:
                browser_ops.redact_image = original_redact_image

            # capture_evidence_screenshot passed bytes straight through —
            # never a Path pointing at something we wrote ourselves first.
            assert len(calls) == 1
            image_source, boxes, output_path = calls[0]
            assert isinstance(image_source, bytes)
            assert output_path == destination

            # Only the one expected file exists in the destination dir — no
            # sibling raw/temp screenshot was ever written to disk.
            files = list(destination.parent.iterdir())
            assert files == [destination]

            assert boxes, "expected at least one redaction box for the sentinel text"
            oracle_box = (
                oracle_rect["left"] * device_pixel_ratio,
                oracle_rect["top"] * device_pixel_ratio,
                oracle_rect["right"] * device_pixel_ratio,
                oracle_rect["bottom"] * device_pixel_ratio,
            )
            assert any(_boxes_intersect(box, oracle_box) for box in boxes), (
                f"no computed box {boxes} intersects the sentinel's own rect {oracle_box}"
            )

            img = Image.open(result_path)
            for box in boxes:
                assert _box_is_entirely_black(img, box)
        finally:
            await session.stop()

    _run(body())


def _boxes_intersect(a: tuple[int, int, int, int], b: tuple[float, float, float, float]) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def _box_is_entirely_black(img: Image.Image, box: tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = box
    left, top = max(0, left), max(0, top)
    right, bottom = min(img.width, right), min(img.height, bottom)
    if right <= left or bottom <= top:
        return False
    cropped = img.crop((left, top, right, bottom))
    return cropped.getbbox() is None or all(
        pixel == (0, 0, 0) for pixel in cropped.convert("RGB").getdata()
    )


# --- no off-localhost / no LLM calls ----------------------------------------


def test_fixture_server_only_ever_serves_localhost(fixture_server):
    assert fixture_server.base_url.startswith("http://127.0.0.1:")
