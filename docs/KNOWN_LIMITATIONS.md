# Known limitations

Per BRIEF.md §9: where the system depends on a human, a licensed intermediary,
a membership, terms permission, or an unavailable integration — plus every
defect found during the build, fixed or not. This document supersedes the
"Known limitations" section of docs/GUARDRAILS.md, which is retained as the
working log this was compiled from.

Canonical run referenced throughout: `20260812T000400Z-445a33`. See
docs/RUN_REPORT.md for the run's coverage ledger and metrics.

## 1. Dependencies

- **Residual market and mutuals need a licensed intermediary.** Facility
  Association (`route-facility-association-residual`) and the Ontario Mutuals
  locator (`route-ontario-mutuals-locator`) do not offer direct-to-consumer
  online rating; both are recorded `manual_handoff` at plan time. So are the
  four MGA/program routes (Agile, APRIL Canada, Burns & Wilcox, Cambrian
  Special Risks, Milnco, Special Risk) and the local-independent-broker
  (RIBO) placeholder route — these require a licensed broker or MGA
  relationship this system does not have and is not permitted to fabricate.
  Aggregator panel members reached only through LowestRates.ca (8 carriers)
  or Surex (3 carriers) fall in the same bucket: the panel itself is the
  intermediary, and a member carrier cannot be contacted independently of it.
- **Affinity routes need a membership.** Inova (`route-inova`) requires a
  qualifying group/employer/membership the participant does not hold;
  recorded `affinity_restricted` per docs/SCHEMAS.md's own definition of that
  status, not attempted.
- **22 unresolved routes need registry research that was not completed.**
  These are legal entities carried over from BRIEF.md Appendix A's regulator
  seed list with no confirmed public Ontario PPA quote route on file —
  no `quote_url`, no `public_phone_route`. Per docs/SCHEMAS.md, `unresolved`
  is never silently converted to a negative outcome; the honest state is "we
  do not yet know how to reach this legal entity," not "this entity does not
  write." Full list in docs/RUN_REPORT.md §2.
- **No telephony integration; callback-dependent routes terminate at the
  handoff package.** `allquote/voice.py`'s Vapi/Twilio client exists but was
  never exercised against a live line for this submission window. Any route
  whose only path forward is `callback_required` stops at a structured
  handoff record (route, profile reference, disclosure line) rather than a
  completed call outcome.

## 2. Defects found and fixed

- **Ineligibility detector matched `rate` as a bare substring.** `gates.py`'s
  `hard_ineligibility` pattern had no word boundary, so it matched inside the
  domain name `rates.ca` itself ("unable to access **rate**s.ca"), which
  would have produced a false `ineligible` status across the registry instead
  of the correct `blocked`. Fixed by bounding the pattern with `\b`.
- **Bot-wall pages classified as `ineligible` instead of `blocked`.** Same
  root cause as above: `captcha_or_bot_check` did not carry explicit bot-wall
  text patterns ("you have been blocked", "security service to protect",
  "ray id", "cloudflare"), so a Cloudflare interstitial fell through to the
  ineligibility matcher. Fixed; `captcha_or_bot_check` now runs at highest
  priority and pre-empts `hard_ineligibility` regardless of substring
  overlap. Regression-tested from the literal captured wall text
  (`tests/fixtures/bot_wall_cloudflare_rates_ca.html`).
- **CAPTCHA detector missed "confirm you are human."** Only "verify you're /
  you are human" was covered. A live probe against belairdirect hit "Let's
  confirm you are human ... this step verifies that you are not a bot" and
  fell through to an unreachable/voluntary-halt result instead of a
  deterministic `blocked` hit. Fixed: the verb/claim axis now covers
  confirm/verify/verifies/prove/proves × human/not-a-bot. Regression-tested
  from the literal captured page text
  (`tests/fixtures/bot_wall_belairdirect_human_check.html`).
- **`payment_or_binding_step` fired on credit-card marketing prose.** TD
  Insurance's plain homepage was misclassified `manual_handoff` from
  existing-customer discount-eligibility copy ("has a TD personal credit
  card... personal loan or line of credit") — no payment form was on the
  page. This was the fourth prose-vs-control false positive found this way
  (after sonnet.ca's footer fine print, Allstate's account/nav chrome, and
  the rates.ca domain-substring case above). Fixed:
  `payment_or_binding_step` now requires `blocking_control_present=True`,
  the same discipline already applied to `consent_or_terms_required` and
  `declaration_attestation`. Regression-tested from the literal captured
  text (`tests/fixtures/negative_td_credit_eligibility_marketing.html`).
- **The fabrication defect.** During early live probing, the browser agent
  invented values for non-sensitive form fields. The task prompt told the
  agent which profile categories to fill but did not supply the profile's
  actual values inline, and nothing in code at the time prevented an
  identity-shaped field (e.g. name) from being filled through the generic
  `fill_public` path instead of the vault-backed `fill_sensitive` path. At
  least two live sites — Onlia and CAA Insurance — received a fabricated
  name ("John"/"Smith") typed via `fill_public` before this was caught. This
  is recorded in the canonical run's own manifest
  (`data/runs/20260812T000400Z-445a33/manifest.json`) as confirmed against
  the captured evidence screenshots from the two superseded runs
  (`20260811T202744Z-79e3e8`, `20260811T205702Z-9cfc30`). No licence number,
  declaration, or payment field was ever involved in the
  incident, and the vault/sensitive-field masking worked correctly
  throughout — DOB and postal code were masked in every capture taken
  during this period, including both affected runs.
  This was found by auditing evidence screenshots against the profile's
  actual expected values, not by an automated check — a manual review step,
  not a defense of the pipeline. Fixed in two parts: `fill_public` now grounds
  every fill action in the loaded `IntakeProfile` instead of letting the
  model free-generate a value, and a code-level guard makes `fill_public`
  refuse to type into any identity-shaped field, forcing it through
  `fill_sensitive` (the vault) instead. All contact-lane results were
  re-run after the fix; the canonical run (`20260812T000400Z-445a33`)
  reflects the corrected pipeline. The two earlier runs
  (`20260811T202744Z-79e3e8`, `20260811T205702Z-9cfc30`) remain on disk,
  unmodified, superseded — see docs/RUN_REPORT.md §6.

## 3. Defects found and not fixed

Disclosed as found; none of these were patched before the submission
deadline.

- **Gate-detection timing race.** A terminal page reached on the agent's
  final step is never re-evaluated by the step hook, so a real block can
  record as `unreachable` instead of `blocked` even when the deterministic
  pattern for it exists and is unit-tested. Confirmed at the unit level
  (`tests/fixtures/bot_wall_cloudflare_rates_ca.html`,
  `tests/fixtures/bot_wall_surex_antibot.html` both pass their
  `test_gates.py` assertions), but a live re-run of rates.ca and
  lowestrates.ca still returned `unreachable: budget exhausted` in the
  canonical run — the Cloudflare wall text was the last thing the agent saw,
  and no further step-hook evaluation followed to catch it. Surex's live
  result (`unreachable (voluntary halt, no independent gate match)`, citing
  "Anti-bot verification failed.") shows the same pattern: the agent itself
  recognized the bot check and correctly refused to proceed past it, but the
  deterministic detector never independently confirmed it within the run, so
  the recorded status is the lower-confidence `unreachable` rather than
  `blocked`. This is a false negative — the opposite failure mode from
  section 2's four prose-vs-control false positives — and is a detector
  gap, not a market outcome; treat these three routes as unresolved bot-wall
  suspicions, not as evidence the market is unreachable by other means.
- **sonnet.ca's reason string is imprecise.** Gate detection requires
  consent prose and a blocking control to co-occur in the same active
  region, but not the same DOM subtree. On sonnet.ca's quote flow, unrelated
  Tangerine-card promotional fine print in the page footer co-occurs with
  the form's own required control, so the canonical run's `manual_handoff`
  reason cites the promotional text rather than the actual gate. The
  terminal status and evidence screenshot are correct for the page reached;
  only the cited reason string is wrong. The same class of error was seen
  once before, against Allstate Canada's plain marketing homepage
  (`blocked`/`login_or_account_required` matched against site-wide
  account/nav chrome, not a quote-flow login wall) — not fixed for the same
  reason: tightening gate-region scoping to the DOM-subtree level risked the
  full passing test suite with no time left to re-verify it before the
  deadline.
- **Square One's consent screen does not rasterize into the evidence
  screenshot.** Reproduced on both superseded runs
  (`20260811T202744Z-79e3e8`, `20260811T205702Z-9cfc30`): the agent
  correctly halted on a personal-declaration consent screen ("you also
  declare that you have obtained consent from all other drivers...") and the
  halt reason is specific and reproducible both times, but the captured
  `evidence.png` in both cases shows a blank/loading page under a
  step-progress header, not the consent screen the reason describes — most
  likely a timing gap between the halt decision and the screenshot capture,
  not a wrong call. The halt itself is correct; the artifact does not
  visually corroborate it.
- **No failed-transition recovery.** When a form does not advance after a
  submit action, the agent has no way to discover why, because validation
  errors commonly render outside its viewport. This is the direct cause of
  CAA Insurance's and Onlia's canonical-run results: CAA was killed by the
  batch hard-cap at 270 seconds with no determination reached, and Onlia
  exhausted its 12-step budget the same way. Both are automation limits —
  our failure to complete the journey, not the market declining to write.
  Contrast with section 1's genuine dependencies and this section's
  detector gaps: this is neither the market's fact nor a detector miss, it
  is the executor running out of ability to proceed.
- **Orphaned Chromium processes under test conditions.** Same class as the
  Task 5 browser-executor teardown bug; mitigated, not eliminated. Batch
  runs can leave detached Chromium processes behind when a route is killed
  by the hard-cap timeout rather than exiting cleanly.
- **`/api/run/start`'s in-flight-run guard does not survive a server
  restart.** `app.py`'s `_active_run_id` lock lives in the handler class's
  in-memory state, not on disk; `batch.run_batch()`'s subprocesses are never
  made children of anything the server tracks past that point, so killing
  or restarting the server process does not stop a batch already in flight
  — it just stops the server from knowing about it. Repeated dev-session
  restarts of `make app` while a run was mid-flight (observed twice in one
  evening) produced several orphaned `data/runs/<run_id>/` directories with
  partial results and no manifest notes, which briefly skewed the results
  view's canonical/superseded-route accounting until manually removed. Not
  fixed: would need either a durable run registry the server re-attaches to
  on startup, or making the batch subprocess group killable by the server's
  own shutdown hook.
- **Registry write-back (docs/ARCHITECTURE.md rule 5) is not implemented.**
  No code path writes a run's resolved status back to `data/allquote.db`'s
  live `status` column. `market_completion`, `comparable_quote_yield`, and
  `freshness` are computed instead from a read-only, in-memory registry
  snapshot built by merging `data/runs/` at report time
  (`report.build_registry_snapshot`). The database itself still shows each
  route's plan-time status until this lands.
- **`duplicate_suppression` reports only the registry-seeded figure.** The
  runtime dedupe resolver specified as Task 8b in PLAN.md — which would
  assign `duplicate_rate_source` against real `QuoteResult`s keyed on
  `(legal_underwriter, product_scope)` — was not built.
  `duplicate_suppression.runtime_resolved` reads 0 in every run; only the
  seed-time collapse (111 registry rows → 79 distinct sources, keyed on
  `legal_underwriter` alone) is reported.
- **`capture_coverage` (Task 8c) is not built.** No executor path transcribes
  verbatim coverage label/value pairs from a live page. There was no live
  coverage material for it to read even had it existed, since no route this
  run reached a coverage-disclosure surface — see docs/RUN_REPORT.md §5 on
  what the committed `ComparisonReport` actually demonstrates.
