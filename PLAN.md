# PLAN — build order for the Ontario All-Quote Agent

Deadline: Wed Aug 12, 11:59 PM ET. Same-day demo: today 3:00 PM.
Work one task per Claude Code session. Each task lists acceptance criteria ("Done when").
Do not start a task until the previous one's criteria pass.

## Phase 0 — Demo slice (today, before 3 PM)

### Task 1 — Schemas + skeleton — DONE
Create `allquote/schemas.py` with pydantic models exactly per docs/SCHEMAS.md:
`Status` enum (13 values), `MarketRecord`, `QuoteResult`, `IntakeProfile` (subset ok
for today: driver basics, vehicle, address, coverage benchmark). Create package
skeleton, Makefile, .env.example, pyproject.
Done when: `make test` passes schema round-trip tests; enum has exactly 13 values
matching docs/SCHEMAS.md; repo tree matches docs/ARCHITECTURE.md layout.

### Task 2 — Registry seed + store — DONE
`allquote/registry.py`: SQLite store; loader that seeds from `data/seed_registry.json`
(I will paste the 32 groups / 60 entities from the brief's Appendix A). Every row
gets status `unresolved`, a `distinct_rate_source_id` (null until verified), and
`last_verified_at` null. CLI: `python -m allquote.registry stats` prints counts by
status and distribution_type.
Done when: seed loads 60 rows; stats command works; export to CSV/JSON works.

### Task 3 — Vault + redaction — DONE
`allquote/vault.py`: Fernet-encrypted JSON at `data/vault.enc`, passphrase from
`VAULT_KEY` env. API: `vault.get(field)` and `vault.inject(callable)` context that
zeroes references after use. `allquote/redact.py`: `redact_text(str)` (regex: ON
licence pattern, DOB-like dates, postal codes, VIN pattern, phone) and
`redact_image(png_bytes, boxes)` (Pillow black-fill).
Done when: unit tests prove a licence-shaped string never survives redact_text;
saving a screenshot without going through redact_image is impossible via the
evidence API (Task 4 will enforce; here just make redact the only public save path).

Also shipped as part of this task: the intake form surface (`allquote/intake.py`,
`exports/intake.html`, `python -m allquote.intake serve` / `make intake`) — the
form described in docs/DESIGN.md §1 that collects IntakeProfile once, routes every
sensitive field through `vault.put()` on submit, writes a consent receipt, and
shows a confirmation listing encrypted field NAMES plus `completeness()` by group.

### Task 4 — Evidence store
`allquote/evidence.py`: `save_evidence(route_id, kind, payload)` → redacts, writes
to `data/evidence/`, returns path + sha256 hash, inserts index row (timestamp UTC,
route, kind, hash). No other module writes into data/evidence/.
Done when: saved artifact is redacted, hashed, indexed; test proves raw payload
differs from stored artifact when payload contains a sensitive pattern.

### Task 5 — Browser executor v1 (one route: Sonnet)
`allquote/executors/browser.py`: wraps browser-use Agent. Input: MarketRecord +
IntakeProfile. Behavior: navigate quote_url, answer fields from profile, vault-inject
sensitive fields, screenshot key pages via evidence.save_evidence, STOP with
`HumanCheckpointRequired` at consent/identity/declaration steps, cap `max_steps`,
1+1 bounded attempts, map outcome to Status, return QuoteResult.
Done when: a dry-run mode works against a local fixture page; a real run against
one direct writer produces a QuoteResult row with evidence path and a legal status.
(I run the real run manually; never in tests.)

### Task 6 — Minimal dashboard
`allquote/dashboard.py` (Streamlit): registry stats by status, results table
(coverage columns BEFORE price columns), click-through to evidence artifact, and a
"gaps" panel listing unresolved/blocked markets.
Done when: `make dashboard` shows seed registry + any results; evidence opens.

STOP — record demo, submit same-day form.

## Phase 1 — Breadth (Mon Aug 10)

### Task 7 — Route planner
`allquote/planner.py`: given registry, choose executor per distribution_type and
requirements flags; skip routes whose requirements the profile can't meet (mark
`ineligible`/`manual_handoff` with reason); order runs; enforce one-run-per-route.
Done when: plan for full registry prints; every route maps to exactly one action.

### Task 8 — Normalizer + dedupe — Part A DONE (coverage comparison only)
`allquote/normalize.py` + `allquote/normalize_basis.py` + `allquote/normalize_compare.py`
+ `allquote/normalize_labels.py`: map raw executor output → NormalizedQuote vs
RequestedBasis coverage; compute comparability and the non_comparable diffs list
(ComparisonReport). 20 tests (C1-C12 + mandatory-AB materiality), acceptance
artifact at exports/comparison_*.json. Dedupe (below) and capture_coverage
(below) were explicitly descoped from this pass — see Task 8b / Task 8c.

### Task 8b — Dedupe resolver
Resolver that assigns the authoritative `distinct_rate_source_id` against real
QuoteResults, keyed on (legal_underwriter, product_scope) per
docs/ARCHITECTURE.md's dedupe model — registry.py's seed-time assignment
(`assign_distinct_rate_source_ids`, keyed on legal_underwriter alone) is only
an approximation pending this. Second route resolving to an existing key gets
status `duplicate_rate_source` pointing at the first. Scheduled AFTER Task 7's
batch run (needs a batch of real QuoteResults to resolve against — dedupe
against single-route fixtures doesn't exercise the real collapse case).
Done when: fixture with an aggregator returning an underwriter already quoted
direct collapses to one distinct source.
Note: `metrics.duplicate_suppression()` already exists but returns 0 for any
real run until this lands — no route can carry `duplicate_rate_source` status
without it.

### Task 8c — capture_coverage custom action (Part B, deferred)
`capture_coverage` custom action in browser_ops.py, per the approved Task 8
plan Part B: the LLM transcribes verbatim label/value pairs only (no
dimension naming, no normalization, no included-vs-unavailable judgment);
allquote.normalize_labels' deterministic table decides what the words mean.
Stored as CoverageObservation, same fallback-never-destroys-a-QuoteResult
pattern as Task 5 evidence capture. Until this lands, the normalizer has no
live material — every CoverageObservation in the test suite and the
acceptance artifact is a hand-authored fixture, not something captured from a
real market page. The normalization gate rests entirely on fixtures until
Task 8c ships.

### Task 9 — More routes
Run browser executor across 3–4 direct writers + 1 aggregator (manual runs).
Harden executor from failures; add per-route quirk notes to registry
`automation_notes`. No site-specific hardcoding of my personal data.
Done when: ≥6 routes have evidence-backed terminal statuses in the db.

## Phase 2 — Depth (Tue Aug 11)

### Task 10 — Voice handoff
`allquote/voice.py`: Vapi assistant config (disclosure opening line from
docs/GUARDRAILS.md verbatim), outbound call trigger with context payload (route,
quote ref, progress), webhook receiver storing structured call outcome via
evidence.save_evidence (no audio unless consent flag true). Escalation = end call
politely + status `manual_handoff`.
Done when: one real call produces a structured outcome row. (I place the call.)

### Task 11 — Dashboard v2 + deletion
Sort by annual cost; coverage-diff badges before price; filter estimates; metrics
tiles; one-click "delete all my data" (vault, evidence, results — not registry).
Done when: delete leaves only seed registry; a deletion record is logged.

## Phase 3 — Ship (Wed Aug 12)

### Task 12 — Exports + reports
`make export`: registry CSV/JSON per Appendix B fields; redacted run report (md);
verify NO sensitive pattern in any export (reuse redact_text as a scanner).
Done when: scanner over exports/ and git-tracked files finds zero hits.

### Task 13 — Docs freeze
Update README (setup for judges), ARCHITECTURE.md (final), GUARDRAILS.md →
architecture & safety note, known limitations section.
Done when: fresh clone + `make setup` + `make dashboard` works per README.

Then: Loom, submission form, IP agreement, LinkedIn post. FEATURE FREEZE at noon.
