"""Shared CSS + nav chrome for every server-rendered view (results, run
console, and — via app.py — the existing intake page keeps its own template
as-is, restyled with the same token names). Modern light-theme redesign:
neutral surfaces, one confident accent, real elevation and radius, a proper
type scale. Reuse, don't fork — every page pulls from this one token set so
nothing drifts.
"""

THEME_CSS = r"""
:root {
  /* Surfaces — neutral, cool, lightest to most recessed */
  --page-bg:        #F4F5F9;
  --surface:        #FFFFFF;
  --surface-alt:    #FAFBFD;
  --surface-sunken: #F1F2F7;

  /* Ink — text, strongest to faintest */
  --ink-900: #14161F;
  --ink-700: #33364D;
  --ink-500: #63667E;
  --ink-400: #8689A0;
  --ink-300: #ABAEC0;

  /* Borders */
  --rule:        #E6E7F0;
  --rule-strong: #D4D6E4;

  /* Accent — one confident colour, carries brand + interaction */
  --accent:       #4F46E5;
  --accent-ink:   #3730A3;
  --accent-soft:  #EEEDFD;

  /* Verified/confirmed signal only — never used to encode a business-outcome
     status (see .status-pill: status is never colour-coded, that reads as
     traffic-light pass/fail for outcomes like specialty_only or
     manual_handoff that are evidenced facts, not errors). */
  --pos-bg: #E8F7EF; --pos-ink: #146C43; --pos-dot: #22A55E;

  /* Semantic layer — components reference roles, never raw values */
  --text-primary: var(--ink-900);
  --text-body:    var(--ink-700);
  --text-label:   var(--ink-500);
  --text-caption: var(--ink-400);
  --text-muted:   var(--ink-300);

  --border:        var(--rule);
  --border-strong: var(--rule-strong);
  --border-focus:  var(--accent);

  /* Shape */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 18px;
  --shadow-sm: 0 1px 2px rgba(20, 22, 40, 0.05), 0 1px 1px rgba(20, 22, 40, 0.03);
  --shadow-md: 0 8px 24px rgba(24, 26, 51, 0.07), 0 2px 6px rgba(24, 26, 51, 0.05);
  --shadow-lg: 0 20px 48px rgba(24, 26, 51, 0.12), 0 4px 12px rgba(24, 26, 51, 0.06);

  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, monospace;
}

* { box-sizing: border-box; }

html, body { background: var(--page-bg); color: var(--text-body); margin: 0; padding: 0; }

body {
  font-family: var(--font-sans);
  font-variant-numeric: tabular-nums;
  line-height: 1.5;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}

.page { max-width: 1180px; margin: 0 auto; padding: 32px 40px 96px; }
@media (max-width: 900px) { .page { padding: 20px 18px 64px; } }

a { color: var(--accent); }
button { font-family: inherit; font-size: inherit; background: none; border: none; cursor: pointer; padding: 0; }
:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 2px; border-radius: 4px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }

/* -- top bar -- */

.topbar {
  display: flex; align-items: center; justify-content: space-between;
  margin: 0 -40px 32px; padding: 18px 40px;
  background: var(--surface); border-bottom: 1px solid var(--border);
}
@media (max-width: 900px) { .topbar { margin: 0 -18px 24px; padding: 16px 18px; flex-wrap: wrap; gap: 12px; } }

.brand { display: flex; align-items: center; gap: 9px; font-weight: 700; font-size: 15px; letter-spacing: -0.01em; color: var(--text-primary); }
.brand .mark {
  width: 22px; height: 22px; border-radius: 7px; background: var(--accent);
  display: inline-flex; align-items: center; justify-content: center;
  color: #fff; font-size: 12px; font-weight: 700;
}

.nav { display: flex; gap: 4px; }
.nav a {
  font-size: 13px; font-weight: 500; color: var(--text-label);
  text-decoration: none; padding: 7px 14px; border-radius: var(--radius-sm);
  transition: background-color 120ms, color 120ms;
}
.nav a:hover { color: var(--text-primary); background: var(--surface-sunken); }
.nav a.current { color: var(--accent-ink); background: var(--accent-soft); font-weight: 600; }

/* -- masthead -- */

.masthead h1 {
  font-size: 28px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.2;
  color: var(--text-primary); margin: 0 0 6px;
}
.masthead .subtitle { color: var(--text-label); font-size: 14px; line-height: 1.5; margin: 0 0 16px; max-width: 70ch; }
.masthead .meta {
  color: var(--text-label); font-size: 12.5px; line-height: 1.5;
  padding: 9px 14px; background: var(--surface-alt); border: 1px solid var(--border);
  border-radius: var(--radius-sm); display: inline-block;
}

section.block { margin: 40px 0; }
section.block > h2 {
  font-size: 18px; font-weight: 700; letter-spacing: -0.01em;
  line-height: 1.3; color: var(--text-primary); margin: 0 0 16px;
}

/* -- metrics: hero stat + supporting grid -- */

.metrics-strip { margin: 24px 0 0; }
.metrics-strip .figure {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md);
  padding: 20px 22px; box-shadow: var(--shadow-sm);
}
.metrics-strip .figure.hero {
  padding: 26px 28px; margin-bottom: 14px;
  background: linear-gradient(155deg, var(--accent-soft), var(--surface) 65%);
  border-color: #DEDCFB;
}
.metrics-strip .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }
.metrics-strip .num { font-size: 34px; font-weight: 700; letter-spacing: -0.03em; line-height: 1.05; color: var(--text-primary); display: block; }
.metrics-strip .figure.hero .num { font-size: 44px; }
.metrics-strip .num.na { color: var(--text-muted); }
.metrics-strip .label { font-size: 12.5px; font-weight: 600; color: var(--text-label); margin-top: 6px; display: block; }
.metrics-strip .sub { font-size: 12px; line-height: 1.5; color: var(--text-caption); margin-top: 6px; display: block; max-width: 42ch; }

/* -- filters: pill toggles -- */

.filters { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-bottom: 18px; align-items: center; }
.filters .group { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.filters .group-label { font-size: 12px; font-weight: 600; color: var(--text-label); margin-right: 4px; }
.filter-toggle {
  font-size: 12.5px; font-weight: 500; color: var(--text-label);
  padding: 5px 12px; border-radius: 999px; background: var(--surface-alt);
  border: 1px solid var(--border); transition: background-color 120ms, color 120ms, border-color 120ms;
}
.filter-toggle.active { color: #fff; background: var(--accent); border-color: var(--accent); font-weight: 600; }
.filter-toggle:hover:not(.active) { color: var(--text-primary); border-color: var(--border-strong); }

/* -- table card -- */

.table-scroll {
  overflow-x: auto; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-md); box-shadow: var(--shadow-sm);
}
table.ledger { width: 100%; border-collapse: collapse; line-height: 1.4; font-size: 13.5px; }
table.ledger th {
  text-align: left; font-size: 11.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
  line-height: 1.4; color: var(--text-label); padding: 12px 16px; border-bottom: 1px solid var(--border);
  background: var(--surface-alt); white-space: nowrap;
}
table.ledger th:first-child { border-top-left-radius: var(--radius-md); }
table.ledger th:last-child { border-top-right-radius: var(--radius-md); }
table.ledger th.sortable { cursor: pointer; }
table.ledger th.sortable:hover { color: var(--text-primary); }
th#th-premium { white-space: normal; min-width: 190px; max-width: 220px; }
th#th-premium .th-main { display: block; }
th#th-premium .th-note {
  display: block; text-transform: none; font-weight: 400; font-size: 11px;
  letter-spacing: 0; line-height: 1.45; color: var(--text-caption); margin-top: 4px;
}
table.ledger td { padding: 12px 16px; vertical-align: top; white-space: nowrap; border-bottom: 1px solid var(--border); }
table.ledger td.wrap { white-space: normal; }
table.ledger tbody tr:last-child td { border-bottom: none; }
table.ledger tbody tr.r0, table.ledger tbody tr.r1,
table.ledger tbody tr.b0, table.ledger tbody tr.b1 { background: var(--surface); }
table.ledger tbody tr.row-clickable:hover { background: var(--surface-alt); }
table.ledger tbody tr.verified { color: var(--text-body); font-weight: 500; }
table.ledger tbody tr.ghost { color: var(--text-muted); font-weight: 400; }
table.ledger tbody tr.row-clickable { cursor: pointer; }

/* -- status pill (replaces bare glyph) --
   Single neutral tone, deliberately: status is carried by the glyph-dot plus
   the label text only, never by colour. A red/amber/green pill would read as
   pass/fail, but most of these statuses (specialty_only, manual_handoff,
   affinity_restricted...) are evidenced facts about a market, not errors —
   see docs/KNOWN_LIMITATIONS.md and CLAUDE.md's "no colour is used to encode
   status" rule, which this design keeps even though it otherwise departs
   from DESIGN.md's tokens. The row's own ghosted/verified weight (below)
   still carries the one distinction this page's colour IS allowed to carry:
   what's confirmed vs merely claimed. */

.status-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12.5px; font-weight: 600; padding: 3px 10px 3px 8px; border-radius: 999px;
  background: var(--surface-sunken); color: var(--text-body);
  border: 1px solid var(--border);
}
.status-pill .dot { width: 6px; height: 6px; border-radius: 999px; background: var(--ink-400); flex: 0 0 auto; }
tr.ghost .status-pill { color: var(--text-muted); border-color: var(--border); background: var(--surface-alt); }
tr.ghost .status-pill .dot { background: var(--ink-300); }

/* -- verified badge (replaces rotated ledger stamp) -- */

.stamp-badge {
  display: inline-flex; flex-direction: column; gap: 1px;
  border: 1px solid var(--pos-dot); color: var(--pos-ink); background: var(--pos-bg);
  border-radius: var(--radius-sm); font-size: 10px; font-weight: 600; letter-spacing: 0.02em;
  padding: 4px 8px; white-space: nowrap; line-height: 1.3;
}
.stamp-badge .verified-time { font-weight: 400; color: var(--text-label); font-family: var(--font-mono); font-size: 9.5px; }

/* -- expanded drawer -- */

.drawer-row td { background: var(--surface-sunken); padding: 0; border-bottom: 1px solid var(--border); }
.drawer { padding: 22px 24px 26px; }
.drawer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px 28px; }
.drawer h3 {
  font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  line-height: 1.4; color: var(--text-label); margin: 20px 0 10px;
}
.drawer h3:first-child { margin-top: 0; }
.drawer-field { font-size: 12.5px; color: var(--text-body); margin: 0 0 6px; max-width: 640px; overflow-wrap: anywhere; }
.drawer-field .k { color: var(--text-label); margin-right: 6px; font-weight: 600; }
.drawer img.evidence-shot { max-width: 100%; border: 1px solid var(--border); border-radius: var(--radius-sm); margin-top: 8px; box-shadow: var(--shadow-sm); }
.evidence-hash { color: var(--text-label); word-break: break-all; font-family: var(--font-mono); font-size: 11.5px; }
.empty-note { color: var(--text-caption); font-size: 13px; padding: 20px; text-align: center; }

/* -- buttons -- */

.btn {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 13.5px; font-weight: 600; padding: 9px 16px; border-radius: var(--radius-sm);
  transition: background-color 120ms, border-color 120ms, color 120ms, transform 120ms;
}
.btn-primary { background: var(--accent); color: #fff; box-shadow: var(--shadow-sm); }
.btn-primary:hover { background: var(--accent-ink); }
.btn-primary:disabled { background: var(--ink-300); cursor: default; }
.btn-primary:active { transform: translateY(1px); }
.btn-ghost { background: var(--surface); color: var(--text-primary); border: 1px solid var(--border-strong); }
.btn-ghost:hover { background: var(--surface-alt); }
"""


def nav_html(current: str) -> str:
    items = [("results", "Results"), ("run", "Run console"), ("intake", "Intake")]
    links = "".join(
        f'<a href="/{key}" class="{"current" if key == current else ""}">{label}</a>'
        for key, label in items
    )
    return (
        '<div class="topbar">'
        '<div class="brand"><span class="mark">AQ</span>All-Quote</div>'
        f'<div class="nav">{links}</div>'
        "</div>"
    )
