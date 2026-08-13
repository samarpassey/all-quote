"""RUN CONSOLE view: start a batch, watch routes resolve as they land.
Polls a JSON endpoint (app.py's GET /api/run/status) — no websockets, per
the stack constraint. Read-only over results_store + registry; the actual
`batch.run_batch()` invocation and its background thread live in app.py,
since that's the one place in this app allowed to launch real executor
subprocesses.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from allquote import registry, results_store
from allquote.view_theme import THEME_CSS, nav_html


def build_run_status(run_id: str, *, runs_root: Path = results_store.RUNS_ROOT) -> dict:
    manifest = results_store.load_manifest(run_id, runs_root=runs_root)
    started_at = manifest["started_at"]
    brand_by_registry_id = {r.registry_id: r.brand_or_program for r in registry.list_records()}

    results_by_id = {r["distinct_rate_source_id"]: r for r in results_store.list_results(run_id, runs_root=runs_root)}

    routes = []
    resolved_count = 0
    for route in manifest["routes"]:
        distinct_id = route["distinct_rate_source_id"]
        payload = results_by_id.get(distinct_id)
        if payload is None:
            state, status, landed_at = "pending", None, None
        elif "quote_result" not in payload:
            state, status, landed_at = "not_attempted", None, None
            resolved_count += 1
        else:
            state = "landed"
            status = payload["quote_result"]["outcome"]["status"]
            landed_at = payload["quote_result"]["evidence"]["timestamp"]
            resolved_count += 1
        routes.append(
            {
                "distinct_rate_source_id": distinct_id,
                "registry_id": route["registry_id"],
                "brand_or_program": brand_by_registry_id.get(route["registry_id"], route["registry_id"]),
                "lane": route["lane"],
                "state": state,
                "status": status,
                "landed_at": landed_at,
            }
        )

    total = len(routes)
    return {
        "run_id": run_id,
        "started_at": started_at,
        "total": total,
        "resolved": resolved_count,
        "finished": resolved_count >= total,
        "now": datetime.now(timezone.utc).isoformat(),
        "routes": routes,
    }


def render_run_console_html(*, latest_run_id: str | None) -> str:
    return (
        _TEMPLATE.replace("__NAV__", nav_html("run"))
        .replace("__THEME_CSS__", THEME_CSS)
        .replace("__LATEST_RUN_ID__", json.dumps(latest_run_id))
    )


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>All-Quote — Run console</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
__THEME_CSS__
.run-controls { display: flex; align-items: center; gap: 16px; margin: 24px 0; }
.run-progress { font-size: 13px; color: var(--text-label); }
.run-finished-cta {
  margin: 0 0 32px 0; padding: 14px 18px; display: flex; align-items: center; justify-content: space-between;
  background: var(--pos-bg); border: 1px solid #BEE8CD; border-radius: var(--radius-md);
}
.run-finished-cta span.label { font-size: 13.5px; font-weight: 600; color: var(--pos-ink); }
.run-finished-cta a {
  display: inline-flex; align-items: center; gap: 6px; font-size: 13.5px; font-weight: 700;
  color: #fff; background: var(--pos-ink); text-decoration: none; padding: 8px 14px; border-radius: var(--radius-sm);
}
.run-finished-cta a:hover { opacity: 0.9; }
</style>
</head>
<body>
<div class="page">
  __NAV__
  <header class="masthead">
    <h1>Run console</h1>
    <div class="subtitle">Starts the batch planner and shows each route's terminal status as
      it lands. A full batch covers the whole registry and can run long — this is meant to be
      watched during a walkthrough, not waited on to completion.</div>
  </header>

  <div class="run-controls">
    <button type="button" class="btn btn-primary" id="start-btn">Start run &rarr;</button>
    <div class="run-progress" id="run-progress"></div>
  </div>

  <div class="run-finished-cta" id="run-finished-cta" hidden>
    <span class="label">Run finished</span>
    <a href="/results">View results &rarr;</a>
  </div>

  <section class="block">
    <div class="table-scroll">
      <table class="ledger">
        <thead>
          <tr><th>Brand</th><th>Lane</th><th>State</th><th>Status</th><th>Landed</th></tr>
        </thead>
        <tbody id="routes-body"></tbody>
      </table>
    </div>
    <div class="empty-note" id="routes-empty">no run started yet this session</div>
  </section>
</div>

<script>
(function () {
  "use strict";
  var LATEST_RUN_ID = __LATEST_RUN_ID__;
  var pollTimer = null;

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function stateLabel(r) {
    if (r.state === "pending") return "pending";
    if (r.state === "not_attempted") return "not attempted (budget)";
    return "landed";
  }

  function render(data) {
    document.getElementById("routes-empty").hidden = data.routes.length !== 0;
    document.getElementById("run-progress").textContent =
      "run " + data.run_id + " — " + data.resolved + " of " + data.total + " resolved" +
      (data.finished ? " — finished" : " — in progress");
    document.getElementById("run-finished-cta").hidden = !data.finished;

    var body = document.getElementById("routes-body");
    body.innerHTML = "";
    data.routes.forEach(function (r, i) {
      var band = (Math.floor(i / 2) % 2 === 0 ? "r" : "b") + (i % 2);
      var statusCell = r.status
        ? '<span class="status-pill"><span class="dot"></span>' + esc(r.status) + "</span>"
        : "—";
      var tr = document.createElement("tr");
      tr.className = band;
      tr.innerHTML =
        "<td>" + esc(r.brand_or_program) + "</td>" +
        "<td>" + esc(r.lane) + "</td>" +
        "<td>" + esc(stateLabel(r)) + "</td>" +
        "<td>" + statusCell + "</td>" +
        "<td>" + esc(r.landed_at || "—") + "</td>";
      body.appendChild(tr);
    });

    if (!data.finished) {
      pollTimer = setTimeout(function () { poll(data.run_id); }, 1500);
    }
  }

  function poll(runId) {
    fetch("/api/run/status?run_id=" + encodeURIComponent(runId))
      .then(function (res) { return res.json(); })
      .then(render)
      .catch(function () {
        document.getElementById("run-progress").textContent = "lost contact with the server — retrying";
        pollTimer = setTimeout(function () { poll(runId); }, 3000);
      });
  }

  document.getElementById("start-btn").addEventListener("click", function () {
    var btn = this;
    btn.disabled = true;
    if (pollTimer) clearTimeout(pollTimer);
    fetch("/api/run/start", { method: "POST" })
      .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
      .then(function (r) {
        btn.disabled = false;
        if (!r.ok) {
          document.getElementById("run-progress").textContent = "could not start: " + (r.data.error || "unknown error");
          return;
        }
        poll(r.data.run_id);
      })
      .catch(function () {
        btn.disabled = false;
        document.getElementById("run-progress").textContent = "could not reach the server";
      });
  });

  if (LATEST_RUN_ID) { poll(LATEST_RUN_ID); }
})();
</script>
</body>
</html>
"""
