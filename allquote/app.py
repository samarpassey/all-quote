"""Unified stdlib server: RESULTS, RUN CONSOLE, and INTAKE (reused as-is
from intake.py, not rebuilt) on one origin. `make app` / `python -m
allquote.app` is the one command judges run; it serves on :8000 by default.

Stdlib only: http.server + ThreadingHTTPServer, no framework, no build step.
Reads run data through report.py / results_view.py / run_console_view.py's
single merged-data-path; the only write this module performs is handing an
intake submission to intake.py's own vault.put()/save_profile() (unchanged
from the existing intake server) and, when a run is started, delegating
entirely to batch.run_batch() -- this module launches nothing itself.
"""

import argparse
import json
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import ValidationError

from allquote import batch, intake, redact, registry, results_store, results_view, run_console_view, vault

DEFAULT_PORT = 8000
EVIDENCE_ROOT = Path("data/evidence")

BatchRunner = Callable[..., str]


def _content_type(name: str) -> str:
    if name.endswith(".png"):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".json"):
        return "application/json"
    return "text/plain; charset=utf-8"


class _AppHandler(BaseHTTPRequestHandler):
    server_version = "AllQuoteApp/0.1"

    db_path: Path = registry.DB_PATH
    runs_root: Path = results_store.RUNS_ROOT
    evidence_root: Path = EVIDENCE_ROOT
    vault_path: Path = vault.VAULT_PATH
    vault_key: str | None = None
    profile_path: Path = intake.PROFILE_PATH
    run_batch_fn: BatchRunner = staticmethod(batch.run_batch)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Same discipline as intake.py's handler: only method/path/status
        # from our own attributes, never anything derived from a request body.
        sys.stderr.write(f"{self.address_string()} {self.command} {self.path}\n")

    log_error = log_message

    def _send_json(self, status: int, obj: dict) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, status: int, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- GET routing --------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/results")
            self.end_headers()
            return
        if path == "/results":
            payload = results_view.build_results_payload(db_path=self.db_path, runs_root=self.runs_root)
            self._send_html(200, results_view.render_results_html(payload))
            return
        if path == "/run":
            latest = results_store.load_latest_run_id(runs_root=self.runs_root)
            self._send_html(200, run_console_view.render_run_console_html(latest_run_id=latest))
            return
        if path in ("/intake", "/intake.html"):
            self._send_html(200, intake.render_html())
            return
        if path == "/api/run/status":
            self._handle_run_status(parse_qs(parsed.query))
            return
        if path.startswith("/evidence/"):
            self._serve_evidence(unquote(path[len("/evidence/") :]))
            return
        self._send_json(404, {"error": "not found"})

    def _handle_run_status(self, query: dict[str, list[str]]) -> None:
        run_id = (query.get("run_id") or [None])[0]
        if not run_id:
            self._send_json(400, {"error": "run_id is required"})
            return
        try:
            status = run_console_view.build_run_status(run_id, runs_root=self.runs_root)
        except FileNotFoundError:
            self._send_json(404, {"error": "no such run"})
            return
        self._send_json(200, status)

    def _serve_evidence(self, rel_path: str) -> None:
        root = self.evidence_root.resolve()
        try:
            target = (root / rel_path).resolve()
        except (OSError, ValueError):
            self._send_json(404, {"error": "not found"})
            return
        within_root = target == root or root in target.parents
        if not within_root or not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _content_type(target.name))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- POST routing ---------------------------------------------------------

    def do_POST(self) -> None:
        if self.path == "/submit":
            self._handle_intake_submit()
            return
        if self.path == "/api/run/start":
            self._handle_run_start()
            return
        self._send_json(404, {"error": "not found"})

    def _handle_intake_submit(self) -> None:
        # Mirrors intake.py's own do_POST exactly (same functions, same
        # generic-error discipline) -- see that module's docstring for why.
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return
        finally:
            del body

        try:
            profile, vaulted = intake.build_profile_from_submission(
                payload, vault_path=self.vault_path, vault_key=self.vault_key
            )
        except (ValidationError, ValueError, KeyError):
            self._send_json(400, {"error": "profile validation failed — check required fields"})
            return
        except Exception:
            self._send_json(500, {"error": "internal error — profile was not saved"})
            return
        finally:
            del payload

        try:
            intake.save_profile(profile, path=self.profile_path)
            receipt_id = redact.write_consent_receipt(
                intake.CONSENT_RECEIPT_ROUTE_ID, vaulted, datetime.now(timezone.utc)
            )
        except Exception:
            self._send_json(500, {"error": "internal error — profile was not saved"})
            return

        self._send_json(
            200,
            {
                "fields_encrypted": vaulted,
                "completeness": profile.completeness(),
                "consent_receipt_id": receipt_id,
            },
        )

    def _handle_run_start(self) -> None:
        profile = intake.load_profile(path=self.profile_path)
        if profile is None:
            self._send_json(400, {"error": "no stored intake profile — visit /intake first"})
            return

        run_id = results_store.new_run_id()
        records = registry.list_records(db_path=self.db_path)
        run_batch_fn = self.run_batch_fn

        def _go() -> None:
            try:
                run_batch_fn(
                    records=records,
                    profile=profile,
                    run_id=run_id,
                    runs_root=self.runs_root,
                    vault_path=self.vault_path,
                    vault_key=self.vault_key,
                )
            except Exception as exc:  # noqa: BLE001 - background thread, must not crash the server
                sys.stderr.write(f"batch run {run_id} failed: {type(exc).__name__}\n")

        threading.Thread(target=_go, daemon=True).start()
        self._send_json(200, {"run_id": run_id})


def _handler_class(
    *,
    db_path: Path = registry.DB_PATH,
    runs_root: Path = results_store.RUNS_ROOT,
    evidence_root: Path = EVIDENCE_ROOT,
    vault_path: Path = vault.VAULT_PATH,
    vault_key: str | None = None,
    profile_path: Path = intake.PROFILE_PATH,
    run_batch_fn: BatchRunner = batch.run_batch,
) -> type[_AppHandler]:
    return type(
        "BoundAppHandler",
        (_AppHandler,),
        {
            "db_path": db_path,
            "runs_root": runs_root,
            "evidence_root": evidence_root,
            "vault_path": vault_path,
            "vault_key": vault_key,
            "profile_path": profile_path,
            "run_batch_fn": staticmethod(run_batch_fn),
        },
    )


def serve(
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = True,
    **bindings: Any,
) -> None:
    handler_cls = _handler_class(**bindings)
    httpd = ThreadingHTTPServer((host, port), handler_cls)
    url = f"http://{host}:{port}/"
    print(f"serving all-quote console at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m allquote.app")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)
    serve(port=args.port, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
