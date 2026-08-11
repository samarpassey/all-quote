# Schemas — single source of truth

allquote/schemas.py must mirror this file exactly. Field names below are canonical;
never rename, alias, or improvise. Derived from the hackathon brief (OAF 1 superset,
Appendix B market record, section 7 result schema).

## Status enum — exactly these 13 values

| value | meaning |
|---|---|
| quoted_comparable | exact premium, benchmark coverage matched |
| quoted_non_comparable | exact premium, ≥1 coverage assumption differs (diffs listed) |
| estimate_only | indicative price/range/lead estimate, not a firm quote |
| callback_required | licensed rep must call before a rate is available |
| manual_handoff | applicant/human required (consent, identity, advice) |
| ineligible | profile fails a product rule; stated reason required |
| affinity_restricted | valid group/employer/membership required |
| specialty_only | route doesn't write standard PPA for this profile |
| duplicate_rate_source | route resolved to an existing distinct_rate_source_id |
| not_currently_writing | evidence indicates no new applicable Ontario PPA business |
| blocked | terms, CAPTCHA, authentication, or access control prevents automation |
| unreachable | bounded attempts produced no response |
| unresolved | needs more research; NEVER silently converted to "not offered" |

## MarketRecord (registry row — Appendix B)

registry_id, legal_underwriter, insurer_group, brand_or_program,
distribution_type ∈ {direct, agent, broker, aggregator, affinity, MGA_program,
mutual, residual},
product_scope ∈ {standard_PPA, nonstandard_PPA, high_net_worth, collector,
commercial_specialty, unknown},
distinct_rate_source_id (nullable until verified), quote_url, public_phone_route,
licensed_intermediary, requirements (subset of {licence, VIN, membership, callback,
human, other}), automation_notes, status (Status), source_url, last_verified_at
(ISO 8601 UTC, nullable), evidence_artifact (path, nullable).

## IntakeProfile (canonical intake — OAF 1 superset, data-minimized)

Groups and key fields (sensitive ones are vault references, marked †):

- consent: consent_timestamp, mode ∈ {live_quote, discovery}, permitted_channels,
  excluded_routes, callback_permission, recording_consent
- identity: legal_name†, preferred_language ∈ {english, french}, date_of_birth†,
  gender ∈ {male, female, X, prefer_not_to_say},
  marital_status ∈ {single, married, common_law, separated, divorced, widowed}
- contact: email†, mobile†, preferred_callback_window (optional)
- address: street†, unit† (optional), city, province ∈ Province, postal_code†,
  residence_start_date, is_garaging_location
- licence: licence_number†, province ∈ Province,
  class ∈ {G1, G2, G, M1, M2, M, A, B, C, D, E, F, other},
  status ∈ {valid, suspended, expired, cancelled}, g1_date (optional),
  g2_date (optional), g_date (optional), first_licensed_date (optional),
  driver_training_completed
- vehicle: vin† (optional — no vehicle yet is a valid intake state; a
  fabricated VIN is prohibited by docs/GUARDRAILS.md), model_year (int, 1900–2027),
  make, model, trim (optional), ownership ∈ {owned, leased},
  purchase_year_month (YYYY-MM, e.g. "2022-06"), lienholder (optional)
- use: use_type ∈ {pleasure, commute, business, farm, commercial},
  commute_km_oneway, annual_km, winter_tires, anti_theft
- history: years_continuously_insured, current_insurer, accidents[] (date, fault_pct,
  amount), convictions[] (date, description), suspensions[], cancellations[]
- coverage_benchmark: effective_date,
  liability_limit ∈ {200000, 500000, 1000000, 2000000}, dcpd_included,
  collision_deductible ∈ {0, 250, 500, 1000, 2500},
  comprehensive_deductible ∈ {0, 250, 500, 1000, 2500}, endorsements
  (opcf_20, opcf_27, opcf_43, opcf_44r), optional_ab_selections{}, telematics_opt_in

Province ∈ {ON, AB, BC, MB, NB, NL, NS, NT, NU, PE, QC, SK, YT} (ON first, then
the remaining 12 provinces and territories alphabetically by abbreviation) —
shared by licence.province and address.province.

Demo benchmark default: $2M liability, DCPD included, mandatory med/rehab/attendant
AB, collision + comprehensive $1,000 deductibles, OPCF 44R, no telematics.
Post-July-2026 rule: every optional accident benefit recorded explicitly as
included | excluded | unavailable | unknown.

## QuoteResult (section 7)

- source: registry_id, brand_or_program, legal_underwriter, insurer_group,
  licensed_intermediary, distinct_rate_source_id
- outcome: status (Status), is_exact_quote (bool), failure_reason, next_action
- price (nullable group): annual_premium, monthly_amount, down_payment,
  instalment_fee, taxes_fees, total_estimated, currency="CAD"
- coverage: requested vs returned limits/deductibles/endorsements,
  variance_from_benchmark[] (list of named diffs; empty = comparable)
- discounts: applied[], available_not_selected[], conditional[]
- validity: quote_reference_id, effective_date, expiry_date,
  verification_may_change_premium (bool)
- evidence: timestamp (ISO 8601 UTC), source_url_or_phone, evidence_artifact,
  evidence_hash (sha256)
- confidence ∈ {high, medium, low}  # high = exact premium + matching coverage;
  medium = licensed rep documented quote; low = estimate/unresolved diff
- privacy: fields_disclosed[], consent_receipt_id, retention_deadline

## EvidenceRecord (evidence-index row)

Written by `evidence.py` (Task 4) on every save. One row per artifact: evidence_id
(uuid4 hex), registry_id (FK to MarketRecord), kind ∈ {screenshot, html_snapshot,
call_transcript, call_outcome, consent_receipt, document}, timestamp (ISO 8601
UTC), source_url_or_phone, artifact_path (relative, under data/evidence/),
evidence_hash (sha256 hex digest of the artifact), redacted (bool — must be true
before any disk write), provenance ∈ {observed, derived} — observed means this
evidence came from actually contacting the market (a page was loaded, a
screenshot was captured, a live response was read); derived means it's a
conclusion from our own registry metadata with no contact made (e.g. a route
with no automatable channel on file). This distinction matters because a
derived record and an observed record must never be presented or counted as
equivalent evidence — fields_disclosed[] (plain field NAMES only, never
values), consent_receipt_id (nullable), retention_deadline (nullable). The last
four fields mirror QuoteResult's privacy group and back the evidence drill-down
view and the one-click delete-all flow (see docs/GUARDRAILS.md retention rules).

## Normalizer derived models (Task 8)

Everything in this section is *derived* — built from QuoteResult and
IntakeProfile, not part of the five canonical models (IntakeProfile,
MarketRecord, QuoteResult, EvidenceRecord, VaultRef), which are unchanged by
this section. Owned by `allquote/normalize.py` and `allquote/normalize_labels.py`.

**CoverageDimension** — FIXED 27-value enum, guarded by a test mirroring the
Status guard. Verified against BRIEF.md §6/§7: third_party_liability,
accident_benefits_mandatory, the 13 optional accident benefits named in §6
("Optional benefits to record") each as its own `ab_opt_*` member (never
merged), uninsured_automobile, dcpd, the 4 own-damage perils (specified
perils, comprehensive, collision, all perils), the 5 OPCF endorsements the
brief names by number (20, 27, 43, 44R, 49 — 49 comes from §6's DCPD
paragraph, not the Endorsements row), and other_endorsement for unmapped
labels. `REQUESTABLE_DIMENSIONS` = all 27 minus other_endorsement (26).

**DisclosureState** — included | excluded | unavailable | unknown, the
brief's own vocabulary (§6 demo-benchmark box) verbatim. Never interchanged:
excluded/unavailable are things the market TOLD us (evidence of reach);
unknown is the only state representing a gap in our own knowledge.

**Comparability** — identical_basis | differs_on_coverage | indicative_only |
not_comparable. Computed once per quote by `assess_comparability()`, always
against RequestedBasis, never pairwise between quotes.

**CoverageObservation** — raw verbatim label/value capture, no
interpretation: source_label, source_value (nullable), captured_at,
evidence_id.

**CoverageLine** — one interpreted dimension: dimension, disclosure,
limit_cad, deductible_cad, source_label/source_value (verbatim origin — both
None only when disclosure=unknown; source_label required otherwise),
provenance ∈ {observed, derived} (reuses EvidenceRecord's Provenance
literal exactly).

**RequestedBasis** — one per run, derived once from
IntakeProfile.coverage_benchmark via `derive_requested_basis()`. Carries
exactly one CoverageLine per requestable dimension (26), disclosure always
included or excluded — never unavailable/unknown, since a basis is authored
by us, not observed from a market. Dimensions CoverageBenchmark doesn't
directly cover fall back to an explicit `BASIS_DEFAULTS` table (in
normalize_labels.py), not a blanket default:
  - accident_benefits_mandatory → included, limit_cad=None (mandatory by
    law; §6: only these remain mandatory for new Ontario policies after
    July 1, 2026 — not a limit we synthesize)
  - uninsured_automobile → included (mandatory Ontario coverage; §6 requires
    included status and limit details where returned)
  - own_damage_specified_perils → excluded (benchmark elects collision +
    comprehensive; specified perils is the unchosen alternative)
  - own_damage_all_perils → excluded (same reason)
  - opcf_49_dcpd_opt_out → excluded (benchmark includes DCPD; opting out
    would contradict the basis)
Every quote's comparability is assessed against this one object; its id is
stamped into every NormalizedQuote so a judge can see what "comparable" was
measured against.

**NormalizedQuote** — market_id, rate_source_id, status, comparability (stored,
computed once by `assess_comparability()` — ComparisonReport copies this
rather than recomputing it, so it needs to live somewhere; not in the task's
original NormalizedQuote field list but added for that reason), requested_basis_id,
lines (one per requestable dimension, plus zero or more other_endorsement
lines), binding_basis ∈ {bound_offer, indicative_assumption, none},
premium (NormalizedPremium: annual/monthly/annualized_from_monthly_cad —
annual is NEVER derived from monthly × 12 — down_payment, instalments,
finance charges, taxes/fees, total, currency, term_months, payment_basis),
validity (NormalizedValidity), discounts (list of NormalizedDiscount:
name/state/condition), confidence ∈ {high, medium, low} — derived from
comparability AND the route's distribution_type, not a restatement of
comparability (a licensed-intermediary-channel quote is medium even when
coverage differs), normalization_warnings, captured_at, evidence_ids.

Status derivation — the ONLY place status is derived from coverage:
  identical_basis     → quoted_comparable
  differs_on_coverage → quoted_non_comparable (quote preserved, every
                        difference listed, per §6: "If a route cannot match
                        it, preserve the quote but mark it non-comparable")
  indicative_only     → estimate_only
  not_comparable       → status unchanged
Bounded authority: the normalizer may only ever write one of
{quoted_comparable, quoted_non_comparable, estimate_only}, and only when the
input QuoteResult.outcome.status is already one of those three. Attempting
to write over a terminal status raises rather than silently passing.

**ComparisonReport** — reports only, never sets status. Field declaration
order is significant and enforced by the model itself: coverage_deltas
serializes before price_view, per §7 ("see coverage differences before price
differences"). inputs, requested_basis_id, comparability (copied from each
quote's own A2 result, never recomputed — one source of truth),
coverage_deltas (CoverageDelta: dimension, the requested basis line, each
compared quote's line, materiality ∈ {material, minor, evidenced_gap,
undisclosed_gap}, optional warning), undisclosed_dimensions (dimensions
where any input is unknown ONLY — unavailable is evidence, not a gap, and
never appears here), price_view (PriceView: per-quote premiums,
price_comparison_valid, reason). No ranking, no best/cheapest/recommended/
winner/savings field or value anywhere in this model — ordering is the
caller's concern, per §7's "never label the lowest displayed number as
best."

## Metrics (computed, never hand-edited)

market_completion = evidence-backed terminal statuses ÷ verified applicable sources
comparable_quote_yield = quoted_comparable ÷ verified applicable sources
evidence_rate = outcomes with valid source+timestamp+artifact ÷ all outcomes
duplicate_suppression = routes mapped to existing distinct_rate_source_id
freshness = % of registry verified during hackathon window

"Verified applicable sources" = MarketRecord rows with status != unresolved.
market_completion, comparable_quote_yield, and freshness require a registry
snapshot to compute this denominator; without one they return None (never a
number derived from the results list alone, which would overstate coverage by
converging toward 100%).
