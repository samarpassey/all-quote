"""Shared CSS + nav chrome for every server-rendered view (results, run
console, and — via app.py — the existing intake page keeps its own template
as-is). One copy of docs/DESIGN.md's tokens so nothing here can drift from
`dashboard.py`'s own copy or invent a new colour/radius/shadow. Reuse, don't
redesign, per DESIGN.md's own instruction.
"""

THEME_CSS = r"""
:root {
  --paper:        #F3F6EF;
  --band:         #E9EFE5;
  --sunken:       #E2E9DE;
  --ink-900:      #12180F;
  --ink-700:      #1A2016;
  --ink-500:      #55604F;
  --ink-400:      #767F71;
  --ink-300:      #8D958A;
  --rule:         #C6D0C0;
  --rule-strong:  #A8B5A2;
  --stamp:        #8C2F39;

  --text-primary:   var(--ink-900);
  --text-body:      var(--ink-700);
  --text-label:     var(--ink-500);
  --text-caption:   var(--ink-400);
  --text-muted:     var(--ink-300);
  --surface:        var(--paper);
  --surface-alt:    var(--band);
  --surface-sunken: var(--sunken);
  --border:         var(--rule);
  --border-strong:  var(--rule-strong);
  --border-focus:   var(--stamp);
  --accent:         var(--stamp);
}

* { box-sizing: border-box; }

html, body { background: var(--surface); color: var(--text-body); margin: 0; padding: 0; }

body {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-variant-numeric: tabular-nums;
  line-height: 1.35;
  font-size: 13px;
}

.page { max-width: 1180px; margin: 0 auto; padding: 40px 56px 96px; }
@media (max-width: 900px) { .page { padding: 24px 20px 64px; } }

a { color: var(--text-body); }
button { font-family: inherit; font-size: inherit; color: var(--text-label); background: none; border: none; cursor: pointer; padding: 0; }
:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }

.eyebrow {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.12em; line-height: 1.4; color: var(--text-muted);
}

.nav { display: flex; gap: 20px; margin-bottom: 20px; }
.nav a {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.12em; line-height: 1.4; color: var(--text-label);
  text-decoration: none; border-bottom: 2px solid transparent; padding-bottom: 2px;
}
.nav a:hover { color: var(--text-body); }
.nav a.current { color: var(--text-body); border-bottom-color: var(--accent); }

.masthead h1 {
  font-size: 22px; font-weight: 600; letter-spacing: -0.01em; line-height: 1.2;
  text-transform: uppercase; color: var(--text-primary); margin: 0 0 6px;
}
.masthead .subtitle { color: var(--text-caption); font-size: 12px; letter-spacing: 0.01em; line-height: 1.4; margin: 0 0 14px; }
.masthead .rule { border: none; border-top: 1px solid var(--border-strong); margin: 0 0 10px; }
.masthead .meta { color: var(--text-label); font-size: 12px; letter-spacing: 0.01em; line-height: 1.4; }

section.block { margin: 40px 0; }
section.block > h2 {
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em;
  line-height: 1.4; color: var(--text-muted); margin: 0 0 16px;
}

.metrics-strip { display: flex; flex-wrap: wrap; margin: 32px 0; }
.metrics-strip .figure { flex: 1 1 170px; padding: 0 20px; border-left: 1px solid var(--border); }
.metrics-strip .figure:first-child { padding-left: 0; border-left: none; }
.metrics-strip .num { font-size: 30px; font-weight: 500; letter-spacing: -0.02em; line-height: 1.1; color: var(--text-primary); display: block; }
.metrics-strip .num.na { color: var(--text-muted); }
.metrics-strip .label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em; line-height: 1.4; color: var(--text-muted); margin-top: 4px; display: block; }
.metrics-strip .sub { font-size: 11px; letter-spacing: 0.01em; line-height: 1.45; color: var(--text-muted); margin-top: 6px; display: block; max-width: 30ch; }

.filters { display: flex; flex-wrap: wrap; gap: 4px 18px; margin-bottom: 16px; }
.filters .group { display: flex; flex-wrap: wrap; gap: 0 14px; align-items: baseline; }
.filters .group-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em; line-height: 1.4; color: var(--text-muted); margin-right: 4px; }
.filter-toggle { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em; line-height: 1.4; color: var(--text-label); padding: 2px 0; border-bottom: 2px solid transparent; }
.filter-toggle.active { color: var(--text-body); border-bottom-color: var(--accent); }
.filter-toggle:hover { color: var(--text-body); }

.table-scroll { overflow-x: auto; }
table.ledger { width: 100%; border-collapse: collapse; line-height: 1.35; font-size: 13px; }
table.ledger th { text-align: left; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em; line-height: 1.4; color: var(--text-muted); padding: 6px 10px; border-bottom: 1px solid var(--border-strong); white-space: nowrap; }
table.ledger th.sortable { cursor: pointer; }
table.ledger th.sortable:hover { color: var(--text-body); }
th#th-premium { white-space: normal; max-width: 200px; }
th#th-premium .th-main { display: block; }
th#th-premium .th-note {
  display: block; text-transform: none; font-weight: 400; font-size: 11px;
  letter-spacing: 0.01em; line-height: 1.45; color: var(--text-caption); margin-top: 4px;
}
table.ledger td { padding: 6px 10px; vertical-align: top; white-space: nowrap; }
table.ledger td.wrap { white-space: normal; }
table.ledger tbody tr.r0, table.ledger tbody tr.r1 { background: var(--surface); }
table.ledger tbody tr.b0, table.ledger tbody tr.b1 { background: var(--surface-alt); }
table.ledger tbody tr.verified { color: var(--text-body); font-weight: 500; }
table.ledger tbody tr.ghost { color: var(--text-muted); font-weight: 400; }
table.ledger tbody tr.row-clickable { cursor: pointer; }

.glyph { display: inline-block; width: 1.4em; text-align: center; }
.glyph.blocked { color: var(--accent); }

.stamp-badge {
  display: inline-block; border: 1px solid var(--accent); color: var(--accent);
  border-radius: 2px; font-size: 9px; letter-spacing: 0.08em; padding: 2px 5px;
  transform: rotate(-4deg); white-space: nowrap; line-height: 1.3;
}

.drawer-row td { background: var(--surface-sunken); padding: 0; }
.drawer { padding: 16px 20px 22px; }
.drawer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px 28px; }
.drawer h3 {
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em;
  line-height: 1.4; color: var(--text-muted); margin: 18px 0 8px;
}
.drawer h3:first-child { margin-top: 0; }
.drawer-field { font-size: 12px; color: var(--text-body); margin: 0 0 6px; }
.drawer-field .k { color: var(--text-label); margin-right: 6px; }
.drawer img.evidence-shot { max-width: 100%; border: 1px solid var(--border); margin-top: 6px; }
.evidence-hash { color: var(--text-label); word-break: break-all; }
.empty-note { color: var(--text-caption); font-size: 12px; letter-spacing: 0.01em; line-height: 1.4; padding: 14px 0; }
"""


def nav_html(current: str) -> str:
    items = [("results", "Results"), ("run", "Run console"), ("intake", "Intake")]
    links = "".join(
        f'<a href="/{key}" class="{"current" if key == current else ""}">{label}</a>'
        for key, label in items
    )
    return f'<div class="nav">{links}</div>'
