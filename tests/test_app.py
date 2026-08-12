import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

from allquote import app, intake, results_store
from tests.fixtures import build_intake_profile
from tests.test_report import _seed_registry, _seed_two_runs


def _noop_batch_runner(**kwargs):
    return kwargs.get("run_id", "unused")


def _wait_until(predicate, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _start_app(tmp_path, *, run_batch_fn=_noop_batch_runner):
    handler_cls = app._handler_class(
        db_path=tmp_path / "allquote.db",
        runs_root=tmp_path / "runs",
        evidence_root=tmp_path / "evidence",
        vault_path=tmp_path / "vault.enc",
        vault_key="test-app-key-not-real",
        profile_path=tmp_path / "profile.json",
        run_batch_fn=run_batch_fn,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def _stop(httpd, thread):
    httpd.shutdown()
    thread.join()
    httpd.server_close()


def _get(httpd, path):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


def test_root_redirects_to_results(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    httpd, thread = _start_app(tmp_path)
    try:
        resp, _ = _get(httpd, "/")
        assert resp.status == 302
        assert resp.getheader("Location") == "/results"
    finally:
        _stop(httpd, thread)


def test_results_page_renders_seeded_rows_with_no_banned_ranking_words(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    _seed_two_runs(tmp_path / "runs")
    httpd, thread = _start_app(tmp_path)
    try:
        resp, body = _get(httpd, "/results")
        html = body.decode("utf-8")
        assert resp.status == 200
        assert "Alpha Co" in html
        for banned in ("cheapest", "recommended", "winner", "savings", ">best<"):
            assert banned not in html.lower()
    finally:
        _stop(httpd, thread)


def test_run_page_renders(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    httpd, thread = _start_app(tmp_path)
    try:
        resp, body = _get(httpd, "/run")
        assert resp.status == 200
        assert b"Run console" in body
    finally:
        _stop(httpd, thread)


def test_intake_page_is_reused_not_rebuilt(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    httpd, thread = _start_app(tmp_path)
    try:
        resp, body = _get(httpd, "/intake")
        assert resp.status == 200
        assert b"Driver profile intake" in body
        assert body == intake.render_html().encode("utf-8")
    finally:
        _stop(httpd, thread)


def test_evidence_serves_file_and_blocks_path_traversal(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    evidence_dir = tmp_path / "evidence" / "route-a" / "attempt-1"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "evidence.png").write_bytes(b"\x89PNGfakebytes")
    (tmp_path / "secret-outside.txt").write_text("should never be reachable")

    httpd, thread = _start_app(tmp_path)
    try:
        resp, body = _get(httpd, "/evidence/route-a/attempt-1/evidence.png")
        assert resp.status == 200
        assert body == b"\x89PNGfakebytes"
        assert resp.getheader("Content-Type") == "image/png"

        resp2, _ = _get(httpd, "/evidence/../secret-outside.txt")
        assert resp2.status == 404

        resp3, _ = _get(httpd, "/evidence/does-not-exist.png")
        assert resp3.status == 404
    finally:
        _stop(httpd, thread)


def test_api_run_status_requires_run_id_and_404s_on_unknown_run(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    httpd, thread = _start_app(tmp_path)
    try:
        resp, body = _get(httpd, "/api/run/status")
        assert resp.status == 400

        resp2, body2 = _get(httpd, "/api/run/status?run_id=no-such-run")
        assert resp2.status == 404
    finally:
        _stop(httpd, thread)


def test_api_run_status_reports_seeded_run_progress(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    run_1, run_2 = _seed_two_runs(tmp_path / "runs")
    httpd, thread = _start_app(tmp_path)
    try:
        resp, body = _get(httpd, f"/api/run/status?run_id={run_1}")
        data = json.loads(body)
        assert resp.status == 200
        assert data["run_id"] == run_1
        assert data["total"] == 3  # alpha-co, beta-co, gamma-co
        assert data["resolved"] == 3  # 2 landed + 1 not_attempted
        assert data["finished"] is True
    finally:
        _stop(httpd, thread)


def test_run_start_without_profile_returns_400(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    httpd, thread = _start_app(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
        conn.request("POST", "/api/run/start")
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        assert resp.status == 400
        assert "profile" in data["error"]
    finally:
        _stop(httpd, thread)


def test_run_start_with_profile_delegates_to_injected_batch_runner(tmp_path):
    _seed_registry(tmp_path / "allquote.db")
    intake.save_profile(build_intake_profile(), path=tmp_path / "profile.json")

    called = threading.Event()
    captured = {}

    def fake_run_batch(**kwargs):
        captured.update(kwargs)
        called.set()
        return kwargs["run_id"]

    httpd, thread = _start_app(tmp_path, run_batch_fn=fake_run_batch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
        conn.request("POST", "/api/run/start")
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()

        assert resp.status == 200
        run_id = data["run_id"]
        assert called.wait(timeout=2)
        assert captured["run_id"] == run_id
        assert captured["profile"].identity is not None
        assert captured["runs_root"] == tmp_path / "runs"
    finally:
        _stop(httpd, thread)


def test_run_start_refuses_concurrent_run_then_allows_a_new_one_after_completion(tmp_path):
    # Four unintended full-registry batches hit live insurer sites because
    # repeated clicks each spawned a new batch. This is the regression test.
    _seed_registry(tmp_path / "allquote.db")
    intake.save_profile(build_intake_profile(), path=tmp_path / "profile.json")

    call_count = {"n": 0}
    started = threading.Event()
    release = threading.Event()

    def fake_run_batch(**kwargs):
        call_count["n"] += 1
        started.set()
        release.wait(timeout=5)
        return kwargs["run_id"]

    httpd, thread = _start_app(tmp_path, run_batch_fn=fake_run_batch)
    try:

        def post_start():
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
            conn.request("POST", "/api/run/start")
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
            return resp.status, data

        status1, data1 = post_start()
        assert status1 == 200
        assert data1["already_running"] is False
        run_id_1 = data1["run_id"]
        assert started.wait(timeout=2)

        # Second click while the first batch is still in flight: no second
        # batch spawned, same run_id handed back.
        status2, data2 = post_start()
        assert status2 == 200
        assert data2["already_running"] is True
        assert data2["run_id"] == run_id_1
        assert call_count["n"] == 1

        release.set()
        handler_cls = httpd.RequestHandlerClass
        assert _wait_until(lambda: handler_cls._active_run_id is None, timeout=5)

        # A third click, now that the first batch has actually finished,
        # must start a genuinely new run.
        started.clear()
        release.clear()
        status3, data3 = post_start()
        assert status3 == 200
        assert data3["already_running"] is False
        assert data3["run_id"] != run_id_1
        assert started.wait(timeout=2)
        assert call_count["n"] == 2
        release.set()
        assert _wait_until(lambda: handler_cls._active_run_id is None, timeout=5)
    finally:
        _stop(httpd, thread)
