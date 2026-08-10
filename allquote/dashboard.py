"""Static HTML dashboard. See PLAN.md Task 6 (revised).

Reads the registry from SQLite (plus any persisted QuoteResults, if a
`quote_results` table exists yet — normalize.py / Task 8 has not landed, so
today that list is always empty) and writes a single self-contained
`exports/dashboard.html`: data embedded as a JSON literal, vanilla JS only,
no CDN, no framework, no build step. Opens offline from file://.

`make dashboard` calls `main()`, which regenerates the file and opens it.
"""

import argparse
import json
import sqlite3
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from allquote import metrics
from allquote.registry import DB_PATH, list_records
from allquote.schemas import MarketRecord, QuoteResult

EXPORT_DIR = Path("exports")
OUTPUT_PATH = EXPORT_DIR / "dashboard.html"


def list_results(db_path: Path = DB_PATH) -> list[QuoteResult]:
    """Read QuoteResults from a `quote_results` table, if one exists yet.

    No writer for this table exists yet (Task 8 / normalize.py is a stub),
    so this returns [] until it does.
    """
    conn = sqlite3.connect(db_path)
    try:
        try:
            rows = conn.execute("SELECT payload FROM quote_results").fetchall()
        except sqlite3.OperationalError:
            return []
        return [QuoteResult.model_validate_json(payload) for (payload,) in rows]
    finally:
        conn.close()


def _verified_in_window(registry: list[MarketRecord]) -> int:
    start, end = metrics.HACKATHON_WINDOW
    return sum(
        1 for r in registry if r.last_verified_at is not None and start <= r.last_verified_at <= end
    )


def build_data(
    registry: list[MarketRecord], results: list[QuoteResult], generated_at: datetime
) -> dict:
    distinct_ids = {r.distinct_rate_source_id for r in registry if r.distinct_rate_source_id}
    verified_applicable = [r for r in registry if r.status.value != "unresolved"]

    return {
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "registry": [r.model_dump(mode="json") for r in registry],
        "results": [r.model_dump(mode="json") for r in results],
        "summary": {
            "routes_mapped": len(registry),
            "distinct_rate_sources": len(distinct_ids),
            "duplicates_suppressed": metrics.duplicate_suppression(results),
            "verified_in_window": _verified_in_window(registry),
            "verified_applicable_sources": len(verified_applicable),
            "market_completion": metrics.market_completion(results, registry),
        },
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, indent=None, separators=(",", ":")).replace("</", "<\\/")
    return _TEMPLATE.replace("__ALLQUOTE_DATA__", payload)


def generate(db_path: Path = DB_PATH, output_path: Path = OUTPUT_PATH) -> Path:
    registry = list_records(db_path=db_path)
    results = list_results(db_path=db_path)
    data = build_data(registry, results, datetime.now(timezone.utc))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(data))
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m allquote.dashboard")
    parser.add_argument("--no-open", action="store_true", help="skip opening the file in a browser")
    args = parser.parse_args(argv)

    path = generate()
    print(f"wrote {path}")
    if not args.no_open:
        webbrowser.open(f"file://{path.resolve()}")
    return 0


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ontario Auto — Market Registry</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {
  --paper: #F3F6EF;
  --band: #E5EDE1;
  --ink: #1A2016;
  --ink-2: #55604F;
  --ink-3: #8D958A;
  --rule: #C6D0C0;
  --stamp: #8C2F39;
}

* { box-sizing: border-box; }

html, body {
  background: var(--paper);
  color: var(--ink);
  margin: 0;
  padding: 0;
}

body {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-variant-numeric: tabular-nums;
  line-height: 1.5;
  font-size: 13px;
}

.page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 56px 56px 96px;
}

@media (max-width: 900px) {
  .page { padding: 32px 20px 64px; }
}

a { color: var(--ink); }

button {
  font-family: inherit;
  font-size: inherit;
  color: var(--ink-2);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}

:focus-visible {
  outline: 2px solid var(--stamp);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}

.eyebrow {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--ink-3);
}

/* -- masthead -- */

.masthead h1 {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  margin: 0 0 6px;
}

.masthead .subtitle {
  color: var(--ink-3);
  font-size: 12px;
  margin: 0 0 14px;
}

.masthead .rule { border: none; border-top: 1px solid var(--rule); margin: 0 0 10px; }

.masthead .meta {
  color: var(--ink-2);
  font-size: 12px;
}

/* -- ledger summary -- */

.ledger-summary {
  display: flex;
  flex-wrap: wrap;
  margin: 40px 0;
}

.ledger-summary .figure {
  flex: 1 1 180px;
  padding: 0 24px;
  border-left: 1px solid var(--rule);
}

.ledger-summary .figure:first-child { padding-left: 0; border-left: none; }

.ledger-summary .num {
  font-size: 30px;
  font-weight: 500;
  display: block;
}

.ledger-summary .num.na { color: var(--ink-3); }

.ledger-summary .label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--ink-3);
  margin-top: 4px;
  display: block;
}

.ledger-summary .sub {
  font-size: 11px;
  color: var(--ink-3);
  margin-top: 6px;
  display: block;
}

/* -- section shell -- */

section.block { margin: 48px 0; }
section.block > h2 {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--ink-3);
  margin: 0 0 16px;
}

/* -- status ledger bar -- */

.status-bar {
  display: flex;
  width: 100%;
  height: 22px;
  border: 1px solid var(--rule);
}

.status-bar .seg { height: 100%; }

.status-legend {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 6px 20px;
}

.status-legend .row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px dotted var(--rule);
  padding: 2px 0;
}

.status-legend .swatch {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 8px;
  vertical-align: middle;
}

.status-legend .count { color: var(--ink-2); }

/* -- filters -- */

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  margin-bottom: 16px;
}

.filters .group { display: flex; flex-wrap: wrap; gap: 0 14px; align-items: baseline; }

.filters .group-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--ink-3);
  margin-right: 4px;
}

.filter-toggle {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-2);
  padding: 2px 0;
  border-bottom: 2px solid transparent;
}

.filter-toggle.active {
  color: var(--ink);
  border-bottom-color: var(--stamp);
}

.filter-toggle:hover { color: var(--ink); }

/* -- tables: green-bar ledger -- */

.table-scroll { overflow-x: auto; }

table.ledger {
  width: 100%;
  border-collapse: collapse;
  line-height: 1.35;
  font-size: 13px;
}

table.ledger th {
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  padding: 6px 10px;
  border-bottom: 1px solid var(--rule);
  white-space: nowrap;
}

table.ledger td {
  padding: 6px 10px;
  vertical-align: top;
  white-space: nowrap;
}

table.ledger td.wrap { white-space: normal; }

table.ledger.evidence-table {
  table-layout: fixed;
  width: 100%;
}

table.ledger.evidence-table td,
table.ledger.evidence-table th {
  white-space: normal;
  overflow-wrap: break-word;
}

table.ledger tbody tr.r0 { background: var(--paper); }
table.ledger tbody tr.r1 { background: var(--paper); }
table.ledger tbody tr.b0 { background: var(--band); }
table.ledger tbody tr.b1 { background: var(--band); }

table.ledger tbody tr.verified { color: var(--ink); font-weight: 500; }
table.ledger tbody tr.ghost { color: var(--ink-3); font-weight: 400; }

table.ledger tfoot td {
  border-top: 1px solid var(--rule);
  padding-top: 8px;
  color: var(--ink-3);
}

.glyph { display: inline-block; width: 1.4em; text-align: center; }
.glyph.blocked { color: var(--stamp); }

.group-row { cursor: pointer; }
.group-row .twirl { display: inline-block; width: 1em; color: var(--ink-3); }

.sub-list td { padding-top: 0; padding-bottom: 10px; }
.sub-table { width: 100%; border-collapse: collapse; margin-left: 1.4em; }
.sub-table td {
  padding: 3px 10px 3px 0;
  border-bottom: 1px dotted var(--rule);
  font-size: 12px;
  color: var(--ink-2);
}

.stamp-badge {
  display: inline-block;
  border: 1px solid var(--stamp);
  color: var(--stamp);
  border-radius: 2px;
  font-size: 9px;
  letter-spacing: 0.08em;
  padding: 2px 5px;
  transform: rotate(-4deg);
  white-space: nowrap;
  line-height: 1.3;
}

.evidence-hash { color: var(--ink-2); }
.evidence-none { color: var(--ink-3); }

.empty-note {
  color: var(--ink-3);
  font-size: 12px;
  padding: 14px 0;
}
</style>
</head>
<body>
<div class="page">

  <header class="masthead">
    <h1>UNDERWRITER</h1>
    <div class="subtitle" id="masthead-subtitle"></div>
    <hr class="rule">
    <div class="meta" id="masthead-meta"></div>
  </header>

  <section class="block">
    <div class="ledger-summary" id="ledger-summary"></div>
  </section>

  <section class="block">
    <h2>Status ledger</h2>
    <div class="status-bar" id="status-bar"></div>
    <div class="status-legend" id="status-legend"></div>
  </section>

  <section class="block">
    <h2>Market map</h2>
    <div class="filters" id="market-filters"></div>
    <div class="table-scroll">
      <table class="ledger">
        <thead>
          <tr>
            <th></th>
            <th>Rate source</th>
            <th>Legal underwriter</th>
            <th>Group</th>
            <th>Routes</th>
            <th>Distribution</th>
            <th>Verified</th>
          </tr>
        </thead>
        <tbody id="market-map-body"></tbody>
      </table>
    </div>
    <div class="empty-note" id="market-map-empty" hidden>no rate sources match the current filters</div>
  </section>

  <section class="block">
    <h2>Evidence ledger</h2>
    <div class="table-scroll">
      <table class="ledger evidence-table">
        <colgroup>
          <col style="width:5%">
          <col style="width:15%">
          <col style="width:30%">
          <col style="width:22%">
          <col style="width:14%">
          <col style="width:14%">
        </colgroup>
        <thead>
          <tr>
            <th></th>
            <th>Status</th>
            <th>Route</th>
            <th>Rate source</th>
            <th>Verified</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody id="evidence-body"></tbody>
      </table>
    </div>
    <div class="empty-note" id="evidence-note"></div>
  </section>

</div>

<script id="allquote-data" type="application/json">__ALLQUOTE_DATA__</script>
<script>
(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("allquote-data").textContent);
  var REGISTRY = DATA.registry;
  var RESULTS = DATA.results;
  var SUMMARY = DATA.summary;

  var HACKATHON_START = "2026-08-09T00:00:00Z";
  var HACKATHON_END = "2026-08-13T04:00:00Z";

  var STATUS_ORDER = [
    "quoted_comparable", "quoted_non_comparable", "estimate_only",
    "callback_required", "manual_handoff", "ineligible", "affinity_restricted",
    "specialty_only", "not_currently_writing", "blocked", "unreachable",
    "duplicate_rate_source", "unresolved"
  ];

  var STATUS_GLYPH = {
    quoted_comparable: "■",
    quoted_non_comparable: "▨",
    estimate_only: "▤",
    callback_required: "□",
    manual_handoff: "□",
    ineligible: "✕",
    affinity_restricted: "✕",
    specialty_only: "✕",
    not_currently_writing: "✕",
    blocked: "✕",
    unreachable: "✕",
    duplicate_rate_source: "=",
    unresolved: "·"
  };

  var STATUS_LABEL = {
    quoted_comparable: "quoted, comparable",
    quoted_non_comparable: "quoted, non-comparable",
    estimate_only: "estimate only",
    callback_required: "callback required",
    manual_handoff: "manual handoff",
    ineligible: "ineligible",
    affinity_restricted: "affinity restricted",
    specialty_only: "specialty only",
    not_currently_writing: "not currently writing",
    blocked: "blocked",
    unreachable: "unreachable",
    duplicate_rate_source: "duplicate rate source",
    unresolved: "unresolved"
  };

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function el(html) {
    var t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstChild;
  }

  function glyphSpan(status) {
    var cls = status === "blocked" ? "glyph blocked" : "glyph";
    return '<span class="' + cls + '">' + STATUS_GLYPH[status] + '</span>';
  }

  function isVerifiedInWindow(ts) {
    return !!ts && ts >= HACKATHON_START && ts <= HACKATHON_END;
  }

  function verifiedCell(record) {
    if (isVerifiedInWindow(record.last_verified_at)) {
      return '<span class="stamp-badge">VERIFIED<br>' + esc(record.last_verified_at) + '</span>';
    }
    return "";
  }

  function pct(x) {
    if (x === null || x === undefined) return null;
    return Math.round(x * 1000) / 10;
  }

  // -- masthead --
  document.getElementById("masthead-subtitle").textContent =
    "Ontario auto — " + SUMMARY.routes_mapped + " routes, " + SUMMARY.distinct_rate_sources + " underwriters";
  document.getElementById("masthead-meta").textContent =
    "registry generated " + DATA.generated_at + " · personal use only · not insurance advice";

  // -- ledger summary --
  (function renderSummary() {
    var mc = pct(SUMMARY.market_completion);
    var figures = [
      { label: "Routes mapped", value: SUMMARY.routes_mapped },
      { label: "Distinct rate sources", value: SUMMARY.distinct_rate_sources },
      { label: "Duplicates suppressed", value: SUMMARY.duplicates_suppressed },
      { label: "Verified in window", value: SUMMARY.verified_in_window },
      {
        label: "Market completion",
        value: mc === null ? null : mc + "%",
        sub: mc === null
          ? "not computable — no routes verified"
          : SUMMARY.verified_applicable_sources + " of " + SUMMARY.routes_mapped + " routes verified applicable"
      }
    ];
    var host = document.getElementById("ledger-summary");
    figures.forEach(function (f) {
      var isNa = f.value === null || f.value === undefined;
      var html = '<div class="figure">' +
        '<span class="num' + (isNa ? ' na' : '') + '">' + (isNa ? "—" : esc(f.value)) + '</span>' +
        '<span class="label">' + esc(f.label) + '</span>' +
        (f.sub ? '<span class="sub">' + esc(f.sub) + '</span>' : '') +
        '</div>';
      host.appendChild(el(html));
    });
  })();

  // -- status ledger bar --
  (function renderStatusBar() {
    var counts = {};
    STATUS_ORDER.forEach(function (s) { counts[s] = 0; });
    REGISTRY.forEach(function (r) { counts[r.status] = (counts[r.status] || 0) + 1; });
    var total = REGISTRY.length || 1;

    var bar = document.getElementById("status-bar");
    var legend = document.getElementById("status-legend");
    var nonBlocked = STATUS_ORDER.filter(function (s) { return s !== "blocked"; });

    STATUS_ORDER.forEach(function (status) {
      var count = counts[status];
      if (!count) return;
      var color;
      if (status === "blocked") {
        color = "var(--stamp)";
      } else {
        var idx = nonBlocked.indexOf(status);
        var alpha = 0.12 + (idx / Math.max(1, nonBlocked.length - 1)) * 0.78;
        color = "rgba(26,32,22," + alpha.toFixed(2) + ")";
      }
      var width = (count / total) * 100;
      bar.appendChild(el('<span class="seg" style="width:' + width + '%;background:' + color + '"></span>'));
      legend.appendChild(el(
        '<div class="row"><span><span class="swatch" style="background:' + color + '"></span>' +
        esc(STATUS_LABEL[status]) + '</span><span class="count">' + count + '</span></div>'
      ));
    });
  })();

  // -- market map (grouped by distinct_rate_source_id) --
  var groups = (function buildGroups() {
    var byId = {};
    var order = [];
    REGISTRY.forEach(function (r) {
      var key = r.distinct_rate_source_id || ("(unassigned:" + r.registry_id + ")");
      if (!byId[key]) {
        byId[key] = { id: key, rows: [] };
        order.push(key);
      }
      byId[key].rows.push(r);
    });
    return order.map(function (k) { return byId[k]; });
  })();

  var marketFilter = { distribution: "ALL", status: "ALL" };

  function groupDistributions(g) {
    var set = {};
    g.rows.forEach(function (r) { set[r.distribution_type] = true; });
    return Object.keys(set);
  }

  function groupRepresentative(g) {
    var verifiedRow = g.rows.find(function (r) { return r.last_verified_at; });
    return verifiedRow || g.rows[0];
  }

  function groupMatchesFilter(g) {
    var distOk = marketFilter.distribution === "ALL" ||
      groupDistributions(g).indexOf(marketFilter.distribution) !== -1;
    var statusOk = marketFilter.status === "ALL" ||
      g.rows.some(function (r) { return r.status === marketFilter.status; });
    return distOk && statusOk;
  }

  function renderMarketFilters() {
    var distValues = Array.from(new Set(REGISTRY.map(function (r) { return r.distribution_type; }))).sort();
    var statusValues = STATUS_ORDER.filter(function (s) {
      return REGISTRY.some(function (r) { return r.status === s; });
    });

    var host = document.getElementById("market-filters");
    host.innerHTML = "";

    function makeGroup(label, values, current, onPick) {
      var wrap = el('<div class="group"><span class="group-label">' + esc(label) + '</span></div>');
      ["ALL"].concat(values).forEach(function (v) {
        var btn = el('<button class="filter-toggle' + (v === current ? " active" : "") + '">' + esc(v) + '</button>');
        btn.addEventListener("click", function () { onPick(v); });
        wrap.appendChild(btn);
      });
      host.appendChild(wrap);
    }

    makeGroup("Distribution", distValues, marketFilter.distribution, function (v) {
      marketFilter.distribution = v;
      renderMarketFilters();
      renderMarketMap();
    });
    makeGroup("Status", statusValues, marketFilter.status, function (v) {
      marketFilter.status = v;
      renderMarketFilters();
      renderMarketMap();
    });
  }

  var expanded = {};

  function renderMarketMap() {
    var body = document.getElementById("market-map-body");
    var emptyNote = document.getElementById("market-map-empty");
    body.innerHTML = "";

    var visible = groups.filter(groupMatchesFilter);
    emptyNote.hidden = visible.length !== 0;

    var bandPair = 0;
    visible.forEach(function (g, i) {
      var rep = groupRepresentative(g);
      var verifiedInWindow = g.rows.some(function (r) { return isVerifiedInWindow(r.last_verified_at); });
      var rowClass = (Math.floor(bandPair / 2) % 2 === 0 ? "r" : "b") + (bandPair % 2);
      bandPair++;
      var stateClass = verifiedInWindow ? "verified" : "ghost";
      var isOpen = !!expanded[g.id];

      var tr = el(
        '<tr class="group-row ' + rowClass + ' ' + stateClass + '" tabindex="0" role="button" aria-expanded="' + isOpen + '">' +
        '<td><span class="twirl">' + (isOpen ? "−" : "+") + '</span>' + glyphSpan(rep.status) + '</td>' +
        '<td>' + esc(g.id) + '</td>' +
        '<td>' + esc(rep.legal_underwriter) + '</td>' +
        '<td>' + esc(rep.insurer_group) + '</td>' +
        '<td>' + g.rows.length + '</td>' +
        '<td>' + esc(groupDistributions(g).join(", ")) + '</td>' +
        '<td>' + verifiedCell(rep) + '</td>' +
        '</tr>'
      );
      function toggle() {
        expanded[g.id] = !expanded[g.id];
        renderMarketMap();
      }
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
      });
      body.appendChild(tr);

      if (isOpen) {
        var subRows = g.rows.map(function (r) {
          return '<tr><td>' + glyphSpan(r.status) + ' ' + esc(r.brand_or_program) + '</td>' +
            '<td>' + esc(r.distribution_type) + '</td>' +
            '<td class="wrap">' + esc(r.quote_url || r.public_phone_route || r.source_url) + '</td></tr>';
        }).join("");
        var subTr = el(
          '<tr class="sub-list ' + rowClass + '"><td colspan="7"><table class="sub-table">' + subRows + '</table></td></tr>'
        );
        body.appendChild(subTr);
      }
    });
  }

  renderMarketFilters();
  renderMarketMap();

  // A back/forward-cache restore replays the DOM (and its click-toggled
  // "active" classes) exactly as left, without re-running this script. Force
  // filters back to ALL/ALL on any such restore so the map always opens
  // showing every rate source.
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    marketFilter.distribution = "ALL";
    marketFilter.status = "ALL";
    renderMarketFilters();
    renderMarketMap();
  });

  // -- evidence ledger (flat, per route, capped to the 20 most recently touched) --
  var EVIDENCE_LIMIT = 20;

  (function renderEvidence() {
    var evidenceByRoute = {};
    RESULTS.forEach(function (res) {
      var id = res.source.registry_id;
      if (!evidenceByRoute[id] || res.evidence.timestamp > evidenceByRoute[id].timestamp) {
        evidenceByRoute[id] = res.evidence;
      }
    });

    function touchedAt(r) {
      var fromResult = evidenceByRoute[r.registry_id] ? evidenceByRoute[r.registry_id].timestamp : null;
      var candidates = [r.last_verified_at, fromResult].filter(Boolean);
      if (!candidates.length) return null;
      candidates.sort();
      return candidates[candidates.length - 1];
    }

    var rows = REGISTRY.slice().sort(function (a, b) {
      var ta = touchedAt(a);
      var tb = touchedAt(b);
      if (ta && tb) return ta < tb ? 1 : ta > tb ? -1 : 0;
      if (ta && !tb) return -1;
      if (!ta && tb) return 1;
      return a.brand_or_program.localeCompare(b.brand_or_program);
    });

    var shown = rows.slice(0, EVIDENCE_LIMIT);

    var body = document.getElementById("evidence-body");
    body.innerHTML = "";
    shown.forEach(function (r, i) {
      var rowClass = (Math.floor(i / 2) % 2 === 0 ? "r" : "b") + (i % 2);
      var verifiedInWindow = isVerifiedInWindow(r.last_verified_at);
      var stateClass = verifiedInWindow ? "verified" : "ghost";
      var evidence = evidenceByRoute[r.registry_id];
      var evidenceCell = evidence
        ? '<span class="evidence-hash">' + esc(evidence.evidence_hash.slice(0, 8)) + '</span>'
        : '<span class="evidence-none">no evidence</span>';

      var tr = el(
        '<tr class="' + rowClass + ' ' + stateClass + '">' +
        '<td>' + glyphSpan(r.status) + '</td>' +
        '<td>' + esc(STATUS_LABEL[r.status]) + '</td>' +
        '<td class="wrap">' + esc(r.brand_or_program) + '</td>' +
        '<td class="wrap">' + esc(r.distinct_rate_source_id || "—") + '</td>' +
        '<td>' + verifiedCell(r) + '</td>' +
        '<td>' + evidenceCell + '</td>' +
        '</tr>'
      );
      body.appendChild(tr);
    });

    document.getElementById("evidence-note").textContent =
      "showing " + shown.length + " of " + rows.length + " — full ledger in exports/registry.csv";
  })();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
