# Design system

The visual language for every surface in this project. **Read this before any UI
work.** The tokens here are canonical — never introduce a colour, typeface,
radius or shadow that is not listed below.

---

## 1. Concept

This product is an **audit ledger for a regulatory dataset**, not a SaaS
dashboard. The reference object is green-bar continuous-feed accounting paper —
the stock financial and insurance printouts came on. Everything follows from
that: a warm pale-green page, alternating row bands, monospace throughout,
hairlines instead of shadows, and a single stamp-red accent used sparingly.

Two surfaces exist today:

- **The ledger** (`exports/dashboard.html`) — dense, tabular, read-only. The
  printout after the run.
- **The form** (`exports/intake.html`) — generous, single-column, one field per
  row. The blank application before it is filled in.

They share every token. They differ only in density.

---

## 2. Colour

### Raw values

```css
/* Paper — surfaces, lightest to most recessed */
--paper:        #F3F6EF;   /* page background */
--band:         #E9EFE5;   /* alternating table band */
--sunken:       #E2E9DE;   /* expanded sub-rows, nested content */

/* Ink — text, strongest to faintest */
--ink-900:      #12180F;   /* headings, metric numerals */
--ink-700:      #1A2016;   /* body text, data cells */
--ink-500:      #55604F;   /* field labels, secondary text */
--ink-400:      #767F71;   /* captions, helper text */
--ink-300:      #8D958A;   /* ghosted / unverified / disabled */

/* Rules — hairlines, never shadows */
--rule:         #C6D0C0;   /* default 1px separator */
--rule-strong:  #A8B5A2;   /* header underline, section divider */

/* Accent — exactly one */
--stamp:        #8C2F39;   /* verification stamp, focus ring, errors */
```

### Semantic layer

Components reference **roles**, never raw values. This is what stops a future
screen from inventing a seventh grey.

```css
--text-primary:  var(--ink-900);
--text-body:     var(--ink-700);
--text-label:    var(--ink-500);
--text-caption:  var(--ink-400);
--text-muted:    var(--ink-300);

--surface:       var(--paper);
--surface-alt:   var(--band);
--surface-sunken:var(--sunken);

--border:        var(--rule);
--border-strong: var(--rule-strong);
--border-focus:  var(--stamp);

--accent:        var(--stamp);
```

### The accent rule

`--stamp` may appear **at most three times on any screen**. Its only sanctioned
uses are:

1. The verification stamp
2. The focus ring on the active input
3. An inline validation error

It never appears on buttons, links, badges, headings, or chrome. The moment red
is decorative, the page reads like every other dashboard.

### Never

No colour is used to encode status. No traffic-light green/amber/red, no
coloured pills, no coloured price cells. Status is carried by a **glyph plus a
text label**, and by ink weight. When quotes land, sort by price and let
position do the work — the only thing that earns a mark is coverage variance,
and that mark is `--stamp` text, not a filled chip.

---

## 3. Typography

One family throughout. No second typeface anywhere.

```css
font-family: ui-monospace, 'SF Mono', Menlo, monospace;
font-variant-numeric: tabular-nums;   /* on every number, everywhere */
```

Hierarchy comes from **weight + size + tracking + leading as a set**, never size
alone. Tracking is size-specific: large text tightens, small text opens up. A
single global `letter-spacing` is wrong somewhere by definition.

| Role | Size | Weight | Tracking | Leading | Colour |
|---|---|---|---|---|---|
| Metric numeral | 30px | 500 | −0.02em | 1.1 | `--text-primary` |
| Page title | 22px | 600 | −0.01em | 1.2 | `--text-primary` |
| Section title | 15px | 600 | 0.01em | 1.3 | `--text-primary` |
| Input text | 15px | 400 | 0 | 1.3 | `--text-body` |
| Data row | 13px | 400 | 0 | 1.35 | `--text-body` |
| Field label | 12px | 500 | 0.01em | 1.4 | `--text-label` |
| Eyebrow / caps label | 11px | 600 | 0.12em | 1.4 | `--text-muted` |
| Helper / caption | 11px | 400 | 0.01em | 1.45 | `--text-caption` |

Caps labels are `text-transform: uppercase` and always take the 0.12em tracking —
uppercase without tracking is unreadable at 11px.

Spacing is expressed in `rem`, not fixed `px`, so the layout scales if the reader
enlarges text.

---

## 4. Space and structure

Dense surfaces (tables) and generous surfaces (forms) use the same rhythm at
different multiples.

```
4px   hairline offsets
8px   intra-cell padding
14px  below a form input's rule
24px  between related blocks
28px  between form fields
32px  between table sections
56px  between form sections
80px  page top padding (form) / 56px (ledger)
```

Max width: **1180px** for the ledger, **620px** for the form. Both centred.

### Structure rules

- **Hairlines, never shadows.** Separation is a 1px `--border`. There are no
  cards, no elevation, no containers. Content sits directly on the paper.
- **Border-radius maximum 3px.** In practice: 2px on the stamp outline, 0
  everywhere else.
- **No vertical rules in tables.** Columns are separated by alignment and space.
  A single `--border-strong` sits under the header row and under the table.
- **Green-bar banding.** Table rows alternate `--surface` / `--surface-alt` in
  *pairs* — two rows per band, as real continuous-feed paper does. Bands run
  full-bleed to the table edges.
- **Expanded sub-rows** sit on `--surface-sunken`, indented, with no border.
  Nesting is read through recession, not outlines.

---

## 5. Signature: epistemic ink

**This is the one memorable element of the product. Execute it precisely and
keep everything around it quiet.**

The design encodes *what is known* versus *what is merely claimed*:

- **Unverified** (`last_verified_at` is null) — the row renders in
  `--text-muted` at weight 400, on plain `--surface`. It reads as not yet
  printed.
- **Verified** — the row renders in `--text-body` at weight 500, on
  `--surface-alt`, with a **verification stamp** in the right margin: a
  transparent-fill box, 1px `--stamp` border, 2px radius, rotated −4°, reading
  `VERIFIED` over the UTC timestamp in 9px mono.

The contrast between ghosted and stamped rows *is* the product thesis. Do not
soften it, do not add a third intermediate state, and do not let the stamp
appear anywhere it has not been earned.

---

## 6. Status encoding

First column, monospace glyph, always accompanied by the status text. No colour
except `blocked`.

| Status | Glyph |
|---|---|
| `quoted_comparable` | ■ |
| `quoted_non_comparable` | ▨ |
| `estimate_only` | ▤ |
| `callback_required` | □ |
| `manual_handoff` | □ |
| `ineligible` | ✕ |
| `affinity_restricted` | ✕ |
| `specialty_only` | ✕ |
| `not_currently_writing` | ✕ |
| `blocked` | ✕ *(in `--stamp`)* |
| `unreachable` | ✕ |
| `duplicate_rate_source` | = |
| `unresolved` | · |

Proportional status bars are built from **graduated tints of `--ink`**, never
from hues.

---

## 7. Controls

- **Inputs**: no box, no fill, no radius. A 1px `--border` underline only. On
  focus the rule thickens to 2px in `--border-focus` and the label shifts to
  `--text-primary`. Nothing else changes.
- **Buttons**: there are none. Actions are tracked text with a rule above them —
  `Save profile →`. No fills, no pills, no radius.
- **Filters / toggles**: tracked caps text. The active one is underlined. Never
  a chip or a pill.
- **Sensitive fields**: a `⌷` lock glyph in `--stamp` sits in the right margin,
  aligned to the label. The explanation — *"encrypted at rest — never written to
  logs, prompts or screenshots"* — appears **once**, at the top of the first
  section containing one. Never repeated per field.

---

## 8. Motion

Almost none. This is a document, not an app.

- Maximum transition duration **120ms**, and only on focus and expand/collapse.
- No entrance animations, no animated counters, no scroll-triggered reveals, no
  spring physics, no parallax.
- `prefers-reduced-motion: reduce` removes all transitions.

---

## 9. Voice

Factual, sentence case, no marketing.

- *"3 of 79 rate sources verified"* — not *"Great progress!"*
- Unresolved and unverified counts are displayed **as prominently as successes**.
  The honesty is the product.
- A metric with no honest value renders `—` with *"not computable — no routes
  verified"* in `--text-muted`. **Never** a zero, never a placeholder number.
- Errors say what to do, in plain language, in `--stamp` at 11px beneath the
  field: *"postal code needs 6 characters, like M5V 2T6"*. The field's rule turns
  `--stamp`. Never a red background fill.
- Labels name what the reader controls, not how the system is built.

---

## 10. Quality floor

Non-negotiable on every surface:

- Keyboard focus always visible — 2px `--border-focus`.
- Tab order follows visual order; forms submit on Enter.
- Responsive down to 768px (ledger) and 380px (form).
- `prefers-reduced-motion` respected.
- Status never conveyed by colour alone.
- No sensitive value is ever echoed back to the screen after submission.

---

## 11. Banned

Gradients · box-shadows · glassmorphism · blur · emoji · icon fonts · filled
buttons · pills · border-radius above 3px · dark mode · blue/green/red
traffic-light status colours · animated counters · progress bars · multi-step
wizards · centred hero text · placeholder text used in place of labels ·
sans-serif or serif faces · any second accent colour · any colour not listed in
section 2.
