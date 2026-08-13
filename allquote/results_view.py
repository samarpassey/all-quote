"""RESULTS view: one row per distinct rate source, per BRIEF.md §7's
"Comparison experience". Reads the single merged-snapshot data path
report.py owns (report.merge_runs / report.build_registry_snapshot /
report.compute_report) — this module adds no second way to read run data,
and never writes to data/allquote.db.
"""

import json
from pathlib import Path

from allquote import planner, registry, report
from allquote.schemas import MarketRecord, Status
from allquote.view_theme import THEME_CSS, nav_html

EVIDENCE_PREFIX = "data/evidence/"


def _evidence_url(artifact_path: str | None) -> str | None:
    if not artifact_path or not artifact_path.startswith(EVIDENCE_PREFIX):
        return None
    return "/evidence/" + artifact_path[len(EVIDENCE_PREFIX) :]


def _artifact_kind(artifact_path: str | None) -> str | None:
    if not artifact_path:
        return None
    return "image" if artifact_path.lower().endswith((".png", ".jpg", ".jpeg")) else "document"


def _origin_to_provenance(origin: str) -> str:
    return "derived" if origin == "derived" else "observed"


def build_rows(
    snapshot: list[MarketRecord], planned: list[planner.PlannedRoute], merged: report.MergedRun
) -> list[dict]:
    """One row per PlannedRoute (the full 79-distinct-source universe, from
    planner.plan_routes -- independent of whether any run has happened yet,
    so an empty data/runs/ still shows all 79 as unresolved rather than 0
    rows). `snapshot` supplies the (possibly run-overridden) status and the
    registry's own last_verified_at; `merged` supplies whatever result
    detail a run actually produced, when one exists."""
    by_registry_id = {r.registry_id: r for r in snapshot}
    rows = []
    for p in planned:
        record = by_registry_id[p.registry_id]
        payload = merged.payloads.get(p.distinct_rate_source_id)
        qr = payload.get("quote_result") if payload else None
        nq = payload.get("normalized_quote") if payload else None

        coverage_lines = []
        annual_premium = None
        if nq:
            coverage_lines = [
                line for line in nq["lines"] if line["disclosure"] != "unknown"
            ]
            annual_premium = nq["premium"].get("annual_premium_cad")
        if annual_premium is None and qr and qr.get("price"):
            annual_premium = qr["price"].get("annual_premium")

        evidence = None
        if qr:
            ev = qr["evidence"]
            evidence = {
                "timestamp": ev["timestamp"],
                "source_url_or_phone": ev["source_url_or_phone"],
                "artifact_url": _evidence_url(ev["evidence_artifact"]),
                "artifact_kind": _artifact_kind(ev["evidence_artifact"]),
                "evidence_hash": ev["evidence_hash"],
            }

        rows.append(
            {
                "distinct_rate_source_id": p.distinct_rate_source_id,
                "registry_id": record.registry_id,
                "brand_or_program": record.brand_or_program,
                "legal_underwriter": record.legal_underwriter,
                "insurer_group": record.insurer_group,
                "distribution_type": record.distribution_type,
                "product_scope": record.product_scope,
                "status": record.status.value,
                "failure_reason": qr["outcome"]["failure_reason"] if qr else None,
                "last_verified_at": (
                    record.last_verified_at.isoformat() if record.last_verified_at else None
                ),
                "provenance": _origin_to_provenance(payload["origin"]) if qr else None,
                "comparability": nq["comparability"] if nq else None,
                "confidence": qr["confidence"] if qr else None,
                "annual_premium": annual_premium,
                "coverage_lines": coverage_lines,
                "evidence": evidence,
            }
        )
    return rows


# A later run only reads as a deliberate, callout-worthy "supersession" of
# specific routes when it's a small, targeted re-run — not when it's just
# another near-full batch that happens to land after the canonical one (that
# case is silent, ordinary chronological progression: e.g. d3116d landed
# 68/79 routes after canonical with the IDENTICAL status on every overlapping
# route — a re-verification, not a change worth flagging). "Small" is
# relative to the canonical run's own landed count, not an absolute number,
# so this keeps working if the registry's size changes.
_PARTIAL_RUN_FRACTION = 0.5


def _landed_counts(run_ids: tuple[str, ...], *, runs_root: Path) -> dict[str, int]:
    return {
        run_id: sum(1 for payload in report.results_store.list_results(run_id, runs_root=runs_root) if "quote_result" in payload)
        for run_id in run_ids
    }


def _canonical_run_id(landed_counts: dict[str, int], run_ids: tuple[str, ...]) -> str | None:
    """The run treated as "the" full batch a partial re-run supersedes part
    of: the run with the most actually-landed results (not just planned
    manifest routes — a killed/interrupted batch can list 79 planned routes
    while only having written 68). Ties (two equally-complete full runs) are
    broken by most recent, on the assumption that a later full re-run of the
    same universe reflects a fix, not a regression — this is a heuristic,
    not a semantic judgment of which run is "better"; it matches every run
    on disk as of this writing (see docs/RUN_REPORT.md) but a future run
    that completes fully yet is worse than an earlier one would still win.
    None only when no run exists yet."""
    if not run_ids:
        return None
    best_id: str | None = None
    best_landed = -1
    for run_id in run_ids:  # oldest first -> a later tie overwrites an earlier one
        landed = landed_counts.get(run_id, 0)
        if landed >= best_landed:
            best_id, best_landed = run_id, landed
    return best_id


def build_results_payload(
    *, db_path: Path = registry.DB_PATH, runs_root: Path = report.results_store.RUNS_ROOT
) -> dict:
    base_registry = registry.list_records(db_path=db_path)
    planned = planner.plan_routes(base_registry)
    merged = report.merge_runs(runs_root=runs_root)
    snapshot = report.build_registry_snapshot(base_registry, merged)
    coverage_report = report.compute_report(db_path=db_path, runs_root=runs_root)
    rows = build_rows(snapshot, planned, merged)

    landed_counts = _landed_counts(merged.run_ids, runs_root=runs_root)
    canonical_run_id = _canonical_run_id(landed_counts, merged.run_ids)
    canonical_landed = landed_counts.get(canonical_run_id, 0) if canonical_run_id else 0
    partial_run_ids = {
        run_id
        for run_id, landed in landed_counts.items()
        if run_id != canonical_run_id and canonical_landed and landed < canonical_landed * _PARTIAL_RUN_FRACTION
    }
    superseded_route_count = sum(
        1 for distinct_id, run_id in merged.source_run_id.items() if run_id in partial_run_ids
    )

    return {
        "generated_from_runs": list(coverage_report.run_ids),
        "canonical_run_id": canonical_run_id,
        "superseded_route_count": superseded_route_count,
        "rows": rows,
        "metrics": {
            "registry_total_rows": coverage_report.registry_total_rows,
            "registry_distinct_sources": coverage_report.registry_distinct_sources,
            "verified_applicable": coverage_report.verified_applicable,
            "market_completion": coverage_report.market_completion,
            "comparable_quote_yield": coverage_report.comparable_quote_yield,
            "freshness": coverage_report.freshness,
            "evidence_rate_all": coverage_report.evidence_rate.all_outcomes,
            "evidence_rate_observed": coverage_report.evidence_rate.observed_only,
            "duplicate_suppression_registry_seeded": coverage_report.duplicate_suppression.registry_seeded,
            "duplicate_suppression_basis": coverage_report.duplicate_suppression.registry_seeded_basis,
        },
        "unresolved_count": sum(1 for r in rows if r["status"] == Status.UNRESOLVED.value),
    }


def render_results_html(payload: dict) -> str:
    data_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return _TEMPLATE.replace("__NAV__", nav_html("results")).replace(
        "__THEME_CSS__", THEME_CSS
    ).replace("__ALLQUOTE_DATA__", data_json)


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>All-Quote — Results</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
__THEME_CSS__
</style>
</head>
<body>
<div class="page">
  __NAV__
  <header class="masthead">
    <h1>Results</h1>
    <div class="subtitle">One row per distinct rate source. Sort and filters never imply a
      ranking — position on this page is not a recommendation.</div>
    <div class="meta" id="masthead-meta"></div>
  </header>

  <section class="block">
    <div class="metrics-strip" id="metrics-strip"></div>
  </section>

  <section class="block">
    <h2>Rate sources</h2>
    <div class="filters" id="filters"></div>
    <div class="table-scroll">
      <table class="ledger">
        <thead>
          <tr>
            <th>Status</th>
            <th>Brand</th>
            <th>Legal underwriter</th>
            <th>Group</th>
            <th>Distribution</th>
            <th>Provenance</th>
            <th>Verified</th>
            <th class="sortable" id="th-premium"><span class="th-main">Annual premium</span><span class="th-note">no priced quote is reachable for this profile — see run report.</span></th>
          </tr>
        </thead>
        <tbody id="rows-body"></tbody>
      </table>
    </div>
    <div class="empty-note" id="rows-empty" hidden>no rate sources match the current filters</div>
  </section>
</div>

<script id="allquote-data" type="application/json">__ALLQUOTE_DATA__</script>
<script>
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("allquote-data").textContent);
  var ROWS = DATA.rows;
  var METRICS = DATA.metrics;

  var HACKATHON_START = "2026-08-09T00:00:00Z";
  var HACKATHON_END = "2026-08-13T04:00:00Z";

  var STATUS_LABEL = {
    quoted_comparable: "quoted, comparable", quoted_non_comparable: "quoted, non-comparable",
    estimate_only: "estimate only", callback_required: "callback required",
    manual_handoff: "manual handoff", ineligible: "ineligible",
    affinity_restricted: "affinity restricted", specialty_only: "specialty only",
    not_currently_writing: "not currently writing", blocked: "blocked",
    unreachable: "unreachable", duplicate_rate_source: "duplicate rate source",
    unresolved: "unresolved"
  };

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function el(html) { var t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; }
  function pct(x) { return x === null || x === undefined ? null : Math.round(x * 1000) / 10; }
  function fmtPct(x) { var p = pct(x); return p === null ? "—" : p + "%"; }
  function isVerifiedInWindow(ts) { return !!ts && ts >= HACKATHON_START && ts <= HACKATHON_END; }
  function money(x) { return x === null || x === undefined ? "—" : "$" + Math.round(x).toLocaleString(); }

  (function renderMastheadMeta() {
    var runLabel;
    if (!DATA.canonical_run_id) {
      runLabel = "no run yet";
    } else if (DATA.superseded_route_count > 0) {
      runLabel = "canonical run " + DATA.canonical_run_id + ", " + DATA.superseded_route_count +
        " route" + (DATA.superseded_route_count === 1 ? "" : "s") + " superseded by later runs";
    } else {
      runLabel = "canonical run " + DATA.canonical_run_id;
    }
    document.getElementById("masthead-meta").textContent =
      runLabel + " · " + DATA.unresolved_count + " of " + ROWS.length +
      " unresolved · personal use only, not insurance advice";
  })();

  // -- metrics strip: hero card (the headline coverage figure) + a grid of
  // supporting cards. Every caveat/sub line below is unchanged verbatim from
  // the original figures list -- only the container markup changed. --
  (function renderMetrics() {
    var hero = { label: "Market completion", value: fmtPct(METRICS.market_completion),
      sub: "attempt coverage against the registry's own known universe (" +
           METRICS.verified_applicable + " of " + METRICS.registry_distinct_sources +
           " sources) — not retrieval success, and bounded by what the registry knows exists." };
    var figures = [
      { label: "Comparable quote yield", value: fmtPct(METRICS.comparable_quote_yield),
        sub: "quoted_comparable ÷ verified applicable sources" },
      { label: "Evidence rate (all)", value: fmtPct(METRICS.evidence_rate_all),
        sub: "evidence rate, observed contact only: " + fmtPct(METRICS.evidence_rate_observed) },
      { label: "Duplicate suppression (registry-seeded)", value: METRICS.duplicate_suppression_registry_seeded,
        sub: (METRICS.duplicate_suppression_basis || "") + " — not the runtime-resolved figure" },
      { label: "Freshness", value: fmtPct(METRICS.freshness),
        sub: "share of verified-applicable rows re-verified in the hackathon window" }
    ];
    function figureHtml(f, extraClass) {
      var isNa = f.value === null || f.value === undefined || f.value === "—";
      return '<div class="figure' + (extraClass ? " " + extraClass : "") + '"><span class="num' +
        (isNa ? " na" : "") + '">' + (isNa ? "—" : esc(f.value)) + '</span><span class="label">' +
        esc(f.label) + '</span><span class="sub">' + esc(f.sub) + '</span></div>';
    }
    var host = document.getElementById("metrics-strip");
    host.appendChild(el(figureHtml(hero, "hero")));
    var grid = el('<div class="grid"></div>');
    figures.forEach(function (f) { grid.appendChild(el(figureHtml(f))); });
    host.appendChild(grid);
  })();

  // -- filters --
  var filter = { distribution: "ALL", hideEstimates: false };

  function matches(r) {
    if (filter.distribution !== "ALL" && r.distribution_type !== filter.distribution) return false;
    if (filter.hideEstimates && r.status === "estimate_only") return false;
    return true;
  }

  function renderFilters() {
    var host = document.getElementById("filters");
    host.innerHTML = "";
    var distValues = Array.from(new Set(ROWS.map(function (r) { return r.distribution_type; }))).sort();
    var wrap = el('<div class="group"><span class="group-label">Distribution</span></div>');
    ["ALL"].concat(distValues).forEach(function (v) {
      var btn = el('<button class="filter-toggle' + (v === filter.distribution ? " active" : "") + '">' + esc(v) + "</button>");
      btn.addEventListener("click", function () { filter.distribution = v; renderFilters(); renderRows(); });
      wrap.appendChild(btn);
    });
    host.appendChild(wrap);

    var estWrap = el('<div class="group"><span class="group-label">Estimates</span></div>');
    var estBtn = el('<button class="filter-toggle' + (filter.hideEstimates ? " active" : "") + '">Hide estimate_only</button>');
    estBtn.addEventListener("click", function () { filter.hideEstimates = !filter.hideEstimates; renderFilters(); renderRows(); });
    estWrap.appendChild(estBtn);
    host.appendChild(estWrap);
  }

  // -- sort (null-safe: unpriced rows always sort last, in either direction) --
  var sortDir = null; // null | "asc" | "desc"
  document.getElementById("th-premium").addEventListener("click", function () {
    sortDir = sortDir === null ? "asc" : sortDir === "asc" ? "desc" : null;
    this.querySelector(".th-main").textContent =
      "Annual premium" + (sortDir === "asc" ? " ↑" : sortDir === "desc" ? " ↓" : "");
    renderRows();
  });

  function sortedRows(visible) {
    if (!sortDir) return visible;
    var withPrice = visible.filter(function (r) { return r.annual_premium !== null && r.annual_premium !== undefined; });
    var withoutPrice = visible.filter(function (r) { return r.annual_premium === null || r.annual_premium === undefined; });
    withPrice.sort(function (a, b) {
      return sortDir === "asc" ? a.annual_premium - b.annual_premium : b.annual_premium - a.annual_premium;
    });
    return withPrice.concat(withoutPrice); // unpriced rows never move to imply a rank
  }

  var expanded = null;

  function verifiedCell(r) {
    return isVerifiedInWindow(r.last_verified_at)
      ? '<span class="stamp-badge">VERIFIED<span class="verified-time">' +
        esc(r.last_verified_at) + "</span></span>" : "";
  }

  function drawerHtml(r) {
    var coverage = r.coverage_lines.length
      ? r.coverage_lines.map(function (l) {
          return '<div class="drawer-field"><span class="k">' + esc(l.dimension) + "</span>" +
            esc(l.disclosure) + (l.limit_cad ? " · limit $" + l.limit_cad : "") +
            (l.deductible_cad ? " · deductible $" + l.deductible_cad : "") + "</div>";
        }).join("")
      : '<div class="drawer-field">no coverage disclosed this run</div>';

    var price = r.annual_premium !== null && r.annual_premium !== undefined
      ? '<div class="drawer-field"><span class="k">Annual premium</span>' + money(r.annual_premium) + "</div>"
      : '<div class="drawer-field">no price disclosed this run</div>';

    var ev = r.evidence;
    var evidenceHtml;
    if (!ev) {
      evidenceHtml = '<div class="drawer-field">no run has attempted this route yet</div>';
    } else {
      var artifact = ev.artifact_url
        ? (ev.artifact_kind === "image"
            ? '<img class="evidence-shot" src="' + esc(ev.artifact_url) + '" alt="redacted evidence screenshot">'
            : '<div class="drawer-field"><a href="' + esc(ev.artifact_url) + '" target="_blank">view evidence document ↗</a></div>')
        : "";
      evidenceHtml =
        '<div class="drawer-field"><span class="k">Timestamp</span>' + esc(ev.timestamp) + "</div>" +
        '<div class="drawer-field"><span class="k">Source</span>' + esc(ev.source_url_or_phone) + "</div>" +
        '<div class="drawer-field"><span class="k">Provenance</span>' + esc(r.provenance) + "</div>" +
        '<div class="drawer-field evidence-hash"><span class="k">Hash</span>' + esc(ev.evidence_hash) + "</div>" +
        artifact;
    }

    var reason = r.failure_reason
      ? '<div class="drawer-field"><span class="k">Reason</span>' + esc(r.failure_reason) + "</div>" : "";

    return '<div class="drawer">' +
      '<div class="drawer-field"><span class="k">Status</span>' + esc(STATUS_LABEL[r.status]) + reason + "</div>" +
      "<h3>Coverage</h3><div class=\"drawer-grid\">" + coverage + "</div>" +
      "<h3>Price</h3><div class=\"drawer-grid\">" + price + "</div>" +
      "<h3>Evidence</h3><div class=\"drawer-grid\">" + evidenceHtml + "</div>" +
      "</div>";
  }

  function renderRows() {
    var body = document.getElementById("rows-body");
    var empty = document.getElementById("rows-empty");
    body.innerHTML = "";
    var visible = sortedRows(ROWS.filter(matches));
    empty.hidden = visible.length !== 0;

    visible.forEach(function (r, i) {
      var band = (Math.floor(i / 2) % 2 === 0 ? "r" : "b") + (i % 2);
      var state = isVerifiedInWindow(r.last_verified_at) ? "verified" : "ghost";
      var pill = '<span class="status-pill"><span class="dot"></span>' +
        esc(STATUS_LABEL[r.status]) + "</span>";
      var tr = el(
        '<tr class="' + band + " " + state + ' row-clickable" tabindex="0" role="button">' +
        "<td>" + pill + "</td>" +
        "<td>" + esc(r.brand_or_program) + "</td>" +
        "<td>" + esc(r.legal_underwriter) + "</td>" +
        "<td>" + esc(r.insurer_group) + "</td>" +
        "<td>" + esc(r.distribution_type) + "</td>" +
        "<td>" + esc(r.provenance || "—") + "</td>" +
        "<td>" + verifiedCell(r) + "</td>" +
        "<td>" + money(r.annual_premium) + "</td>" +
        "</tr>"
      );
      function toggle() {
        expanded = expanded === r.distinct_rate_source_id ? null : r.distinct_rate_source_id;
        renderRows();
      }
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
      body.appendChild(tr);

      if (expanded === r.distinct_rate_source_id) {
        // class="wrap" -- table.ledger td defaults to white-space: nowrap
        // (right for dense one-line cells elsewhere in the ledger); the
        // drawer holds prose and a long evidence URL, both of which need to
        // wrap, not run off the edge of the (already horizontally-scrolled)
        // table. Reuses the existing td.wrap override rather than inventing
        // a second one.
        body.appendChild(el('<tr class="drawer-row"><td colspan="9" class="wrap">' + drawerHtml(r) + "</td></tr>"));
      }
    });
  }

  renderFilters();
  renderRows();
})();
</script>
</body>
</html>
"""
