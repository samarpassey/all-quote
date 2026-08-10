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
- identity: legal_name†, preferred_language, date_of_birth†, gender, marital_status
- contact: email†, mobile†, preferred_callback_window (optional)
- address: street†, unit† (optional), city, province, postal_code†,
  residence_start_date, is_garaging_location
- licence: licence_number†, province, class, status, g1_date (optional),
  g2_date (optional), g_date (optional), first_licensed_date (optional),
  driver_training_completed
- vehicle: vin† (optional — no vehicle yet is a valid intake state; a
  fabricated VIN is prohibited by docs/GUARDRAILS.md), model_year, make, model,
  trim (optional), ownership ∈ {owned, leased}, purchase_year_month,
  lienholder (optional)
- use: use_type ∈ {pleasure, commute, business}, commute_km_oneway, annual_km,
  winter_tires, anti_theft
- history: years_continuously_insured, current_insurer, accidents[] (date, fault_pct,
  amount), convictions[] (date, description), suspensions[], cancellations[]
- coverage_benchmark: effective_date, liability_limit, dcpd_included,
  collision_deductible, comprehensive_deductible, endorsements
  (opcf_20, opcf_27, opcf_43, opcf_44r), optional_ab_selections{}, telematics_opt_in

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
before any disk write), fields_disclosed[] (plain field NAMES only, never
values), consent_receipt_id (nullable), retention_deadline (nullable). The last
four fields mirror QuoteResult's privacy group and back the evidence drill-down
view and the one-click delete-all flow (see docs/GUARDRAILS.md retention rules).

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
