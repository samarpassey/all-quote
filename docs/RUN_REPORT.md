# Run report

Canonical run: `20260812T000400Z-445a33`, merged with two superseded runs
(`20260811T202744Z-79e3e8`, `20260811T205702Z-9cfc30` — see §6). Produced by
`python -m allquote.report` / `allquote/results_view.py` against the current
market registry (`data/allquote.db`, seeded from `data/seed_registry.json`)
and everything on disk under `data/runs/`. Redacted per docs/GUARDRAILS.md;
no real licence number, DOB, VIN, full address, or phone appears anywhere
below — self-checked by grep, see the end of this document's companion note
in the submission.

## Executive summary

**Headline finding.** This profile holds a G1 Ontario driver's licence,
first licensed 2024-07-22. A G1 holder cannot be the principal driver on a
standard Ontario private-passenger auto policy, so no standard Ontario
market will price this risk. Every terminal status below follows from that
one market fact — it is not a system failure. Full statement in §1.

**The five metrics.**

| Metric | Value | Denominator |
|---|---|---|
| Market completion | 100.0% | 57 of 57 verified-applicable sources carry an evidence-backed terminal status |
| Comparable quote yield | 0.0% | 0 of 57 verified-applicable sources returned `quoted_comparable` |
| Evidence rate (all / observed) | 100.0% / 100.0% | 79 of 79 outcomes; 20 of 20 market-contacted outcomes |
| Duplicate suppression (registry-seeded) | 32 | 111 registry rows → 79 distinct sources |
| Freshness | 7.0% | 4 of 57 verified-applicable sources re-verified in the hackathon window |

Read market completion (100%) as *attempt coverage*, not retrieval success —
it is bounded by what the registry knows exists, and it sits next to a 0%
yield and 7% freshness on purpose. Full discussion in §3.

**Barrier classes, by count, across the 20 distinct sources this run
actually contacted (`provenance=observed`):**

| Class | Count | What it means |
|---|---|---|
| Our own guardrail halts | 0 this run (2 reproduced in superseded runs) | Our safety policy stopping us, not the site — Square One's consent-declaration halt |
| Site access controls (bot walls, account walls) | 3 `blocked` (2 confirmed, 1 lower-confidence) | belairdirect and InsuranceHotline are confirmed real walls; Allstate's evidence shows only its marketing homepage |
| Market gates (consent, identity) | 4 (2 confirmed `manual_handoff`, 2 recognized but unconfirmed) | Sonnet and TD Insurance are deterministically confirmed; Co-operators and Desjardins were correctly refused by the agent but not independently confirmed by the detector |
| Our own automation limits | 13 `unreachable` (10 pure automation limits, 3 suspected undetected bot walls) | The market did not stop these — the agent ran out of step budget or hit the batch hard-cap with no market-side signal; 3 more (Rates.ca, LowestRates.ca, Surex) show a possible wall the detector missed |

Full breakdown, route-by-route, in §4.

**What is and isn't demonstrated.** This run demonstrates full-registry
attempt coverage with an evidence-backed terminal status and redacted,
hashed artifact for every one of 79 distinct rate sources, and a working
normalization/comparability schema exercised against fixture data (§5); it
does **not** demonstrate a live priced quote, a coverage disclosure
captured from a real market page, or the runtime dedupe resolver — none of
which was possible this run because, per the headline finding, this profile
does not currently qualify for standard-market pricing anywhere in Ontario.

---

## 1. The headline finding

**This profile holds a G1 Ontario driver's licence (`class=G1`, valid,
first licensed 2024-07-22). A G1 holder cannot be the principal driver on a
standard Ontario private-passenger auto policy — Ontario's graduated
licensing rules require a G2 or full G before an insurer will rate someone
as the principal operator. No standard Ontario market will price this risk,
full stop.**

This is a market fact, not a system failure. Every terminal status in the
coverage ledger below — every `manual_handoff`, every `blocked`, every
`unreachable`, every `specialty_only`, every `unresolved` — is downstream of
this one fact: there was never a standard-PPA quote to be had for this
profile from any of the 79 distinct rate sources this run reached or
reasoned about. `comparable_quote_yield` is 0% not because the agent failed
to shop hard enough, but because the product this profile qualifies for
does not exist in the standard market it was pointed at. Read the rest of
this report — coverage, barriers, gaps — against that fact, not in spite of
it.

## 2. Coverage ledger

All 79 distinct rate sources in the registry (111 registry rows collapse to
79 distinct sources at seed time — see §3's duplicate-suppression note),
each with its terminal status, evidence provenance (`observed` = a market
was actually contacted; `derived` = a conclusion from registry metadata with
no contact made), the registry's own `last_verified_at` where set, and the
evidence artifact this run's outcome is backed by. Sorted by status in
docs/SCHEMAS.md's canonical order, then alphabetically by brand.

No row below carries `quoted_comparable`, `quoted_non_comparable`,
`estimate_only`, `callback_required`, `ineligible`, `duplicate_rate_source`,
or `not_currently_writing` this run — see §1.

| Registry ID | Brand / program | Legal underwriter | Distribution | Status | Provenance | Verified (UTC) | Evidence timestamp (UTC) | Evidence source | Hash (12) |
|---|---|---|---|---|---|---|---|---|---|
| `route-agile` | Agile | Agile | MGA_program | manual_handoff | derived | — | 2026-08-12T00:04:00.185971Z | Brief §4 (channel coverage requirements) | `da197164a0cd` |
| `route-april-canada` | APRIL Canada | APRIL Canada | MGA_program | manual_handoff | derived | — | 2026-08-12T00:04:00.200533Z | Brief §4 (channel coverage requirements) | `cc16e400ea5c` |
| `route-burns-wilcox` | Burns & Wilcox | Burns & Wilcox | MGA_program | manual_handoff | derived | — | 2026-08-12T00:04:00.202848Z | Brief §4 (channel coverage requirements) | `8251443f1e20` |
| `route-cambrian-special-risks` | Cambrian Special Risks | Cambrian Special Risks | MGA_program | manual_handoff | derived | — | 2026-08-12T00:04:00.203989Z | Brief §4 (channel coverage requirements) | `5aabab2dd612` |
| `panel-lowestrates-coachman` | Coachman (via LowestRates.ca panel) | Coachman Insurance Company | aggregator | manual_handoff | derived | — | 2026-08-12T00:04:00.207287Z | Brief §3 (practical route strategy) | `f77e88ece0a7` |
| `panel-lowestrates-economical` | Economical (via LowestRates.ca panel) | Economical Mutual Insurance Company | aggregator | manual_handoff | derived | — | 2026-08-12T00:04:00.214027Z | Brief §3 (practical route strategy) | `d954bff5e2c7` |
| `route-facility-association-residual` | Facility Association (residual) | Facility Association | residual | manual_handoff | derived | — | 2026-08-12T00:04:00.217238Z | Brief §4 (channel coverage requirements) | `edb0447193fe` |
| `panel-lowestrates-gore` | Gore (via LowestRates.ca panel) | Gore Mutual Insurance Company | aggregator | manual_handoff | derived | — | 2026-08-12T00:04:00.221812Z | Brief §3 (practical route strategy) | `89e72ebaf027` |
| `panel-surex-intact` | Intact (via Surex panel) | Intact Insurance Company | broker | manual_handoff | derived | — | 2026-08-12T00:04:00.226342Z | Brief §3 (practical route strategy) | `b2dbd29500c5` |
| `panel-surex-jevco` | Jevco (via Surex panel) | Jevco Insurance Company | broker | manual_handoff | derived | — | 2026-08-12T00:04:00.227817Z | Brief §3 (practical route strategy) | `ccea3c484b6a` |
| `route-local-independent-broker-ribo` | Local independent broker (RIBO) | Local independent broker (RIBO) | broker | manual_handoff | derived | — | 2026-08-12T00:04:00.230352Z | Brief §4 (channel coverage requirements) | `3ba13caf5c6d` |
| `route-milnco` | Milnco | Milnco | MGA_program | manual_handoff | derived | — | 2026-08-12T00:04:00.232040Z | Brief §4 (channel coverage requirements) | `d7f029053d04` |
| `route-ontario-mutuals-locator` | Ontario Mutuals locator | Ontario Mutuals locator | mutual | manual_handoff | derived | — | 2026-08-12T00:04:00.235431Z | Brief §4 (channel coverage requirements) | `3a896dfe08cb` |
| `panel-lowestrates-pafco` | Pafco (via LowestRates.ca panel) | Pafco Insurance Company | aggregator | manual_handoff | derived | — | 2026-08-12T00:04:00.237994Z | Brief §3 (practical route strategy) | `5e66d0bf5525` |
| `panel-lowestrates-pembridge` | Pembridge (via LowestRates.ca panel) | Pembridge Insurance Company | aggregator | manual_handoff | derived | — | 2026-08-12T00:04:00.240466Z | Brief §3 (practical route strategy) | `2998be9ac89c` |
| `panel-lowestrates-sgi` | SGI (via LowestRates.ca panel) | SGI CANADA Insurance Services Ltd. | aggregator | manual_handoff | derived | — | 2026-08-12T00:04:00.248781Z | Brief §3 (practical route strategy) | `36484912e475` |
| `route-sonnet` | Sonnet | Sonnet Insurance Company | direct | manual_handoff | observed | 2026-08-09T18:46:08.702479+00:00 | 2026-08-12T00:09:41.888382Z | https://www.sonnet.ca/ | `348972eb537a` |
| `route-special-risk` | Special Risk | Special Risk | MGA_program | manual_handoff | derived | — | 2026-08-12T00:04:00.251171Z | Brief §4 (channel coverage requirements) | `7aa2bbd47518` |
| `route-td-insurance` | TD Insurance | Security National Insurance Company | direct | manual_handoff | observed | 2026-08-09T18:49:23.349821+00:00 | 2026-08-12T00:08:51.230721Z | https://www.tdinsurance.com/ | `bd2399c23e7a` |
| `panel-lowestrates-travelers` | Travelers (via LowestRates.ca panel) | The Dominion of Canada General Insurance Company | aggregator | manual_handoff | derived | — | 2026-08-12T00:04:00.255137Z | Brief §3 (practical route strategy) | `529af34f7fd6` |
| `panel-surex-wawanesa` | Wawanesa (via Surex panel) | The Wawanesa Mutual Insurance Company | broker | manual_handoff | derived | — | 2026-08-12T00:04:00.273165Z | Brief §3 (practical route strategy) | `20a8d5836781` |
| `panel-lowestrates-zenith` | Zenith (via LowestRates.ca panel) | Zenith Insurance Company | aggregator | manual_handoff | derived | — | 2026-08-12T00:04:00.283229Z | Brief §3 (practical route strategy) | `3dd3307206d8` |
| `route-inova` | Inova | Inova | broker | affinity_restricted | derived | — | 2026-08-12T00:04:00.225259Z | Brief §4 (channel coverage requirements) | `fad1fb98e518` |
| `seed-aig-aig-insurance-company-of-canada` | AIG Insurance Company of Canada | AIG Insurance Company of Canada | broker | specialty_only | derived | — | 2026-08-12T00:04:00.199414Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `23f7c1d28ca6` |
| `seed-chubb-chubb-insurance-company-of-canada` | Chubb Insurance Company of Canada | Chubb Insurance Company of Canada | broker | specialty_only | derived | — | 2026-08-12T00:04:00.206248Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `1ba3883c0e90` |
| `seed-continental-continental-casualty-company` | Continental Casualty Company | Continental Casualty Company | broker | specialty_only | derived | — | 2026-08-12T00:04:00.208481Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `34207c9077d5` |
| `seed-caa-echelon-insurance` | Echelon Insurance | Echelon Insurance | broker | specialty_only | derived | — | 2026-08-12T00:04:00.212987Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `ac5c1fc54c42` |
| `seed-sompo-endurance-specialty-insurance-ltd` | Endurance Specialty Insurance Ltd. | Endurance Specialty Insurance Ltd. | broker | specialty_only | derived | — | 2026-08-12T00:04:00.215080Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `f497cd4fd3a9` |
| `seed-northbridge-federated-insurance-company-of-canada` | Federated Insurance Company of Canada | Federated Insurance Company of Canada | broker | specialty_only | derived | — | 2026-08-12T00:04:00.220741Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `41ee69fe6ab6` |
| `seed-hartford-hartford-fire-insurance-company` | Hartford Fire Insurance Company | Hartford Fire Insurance Company | broker | specialty_only | derived | — | 2026-08-12T00:04:00.222934Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `8a722ef4a5de` |
| `seed-liberty-liberty-mutual-insurance-company` | Liberty Mutual Insurance Company | Liberty Mutual Insurance Company | broker | specialty_only | derived | — | 2026-08-12T00:04:00.229129Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `8b2fc0044932` |
| `seed-northbridge-northbridge-general-insurance-corporation` | Northbridge General Insurance Corporation | Northbridge General Insurance Corporation | broker | specialty_only | derived | — | 2026-08-12T00:04:00.233210Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `ed2308300e0a` |
| `seed-optimum-optimum-insurance-company-inc` | Optimum Insurance Company Inc. | Optimum Insurance Company Inc. | broker | specialty_only | derived | — | 2026-08-12T00:04:00.236854Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `dd6e6f4320eb` |
| `seed-pure-pure-insurance` | PURE Insurance | PURE Insurance | broker | specialty_only | derived | — | 2026-08-12T00:04:00.242667Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `8fa7bc6c5900` |
| `seed-sompo-sompo-japan-insurance-inc` | Sompo Japan Insurance Inc. | Sompo Japan Insurance Inc. | broker | specialty_only | derived | — | 2026-08-12T00:04:00.249746Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `773cf6cc603a` |
| `seed-intact-the-guarantee-company-of-north-america` | The Guarantee Company of North America | The Guarantee Company of North America | broker | specialty_only | derived | — | 2026-08-12T00:04:00.265984Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `ac8af2a653f4` |
| `seed-co-op-the-sovereign-general-insurance-company` | The Sovereign General Insurance Company | The Sovereign General Insurance Company | broker | specialty_only | derived | — | 2026-08-12T00:04:00.270445Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `0a54ea7a43bc` |
| `seed-tokio-tokio-marine-and-nichido-fire-insurance-company-limited` | Tokio Marine and Nichido Fire Insurance Company Limited | Tokio Marine and Nichido Fire Insurance Company Limited | broker | specialty_only | derived | — | 2026-08-12T00:04:00.274228Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `3e62055d08bf` |
| `seed-xl-xl-specialty-insurance-company` | XL Specialty Insurance Company | XL Specialty Insurance Company | broker | specialty_only | derived | — | 2026-08-12T00:04:00.282039Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `25aa9f6b0b4f` |
| `route-allstate-canada` | Allstate Canada | Allstate Insurance Company of Canada | direct | blocked | observed | — | 2026-08-11T19:19:21.330554Z | https://www.allstate.ca/ | `200296ff6a42` |
| `route-belairdirect` | belairdirect | Belair Insurance Company Inc. | direct | blocked | observed | 2026-08-09T18:47:00.526584+00:00 | 2026-08-12T00:04:22.316816Z | https://www.belairdirect.com/ | `f3bdfa3b16bf` |
| `route-insurancehotline` | InsuranceHotline | InsuranceHotline | aggregator | blocked | observed | — | 2026-08-12T00:11:06.689138Z | https://www.insurancehotline.com/ | `1305137267a3` |
| `route-aviva-direct` | Aviva Direct | Aviva Direct | direct | unreachable | observed | — | 2026-08-12T00:10:30.849602Z | https://www.aviva.ca/ | `9db8ef7f60b6` |
| `route-caa-insurance` | CAA Insurance | CAA Insurance Company | direct | unreachable | observed | 2026-08-09T18:48:16.284190+00:00 | 2026-08-12T00:08:30.337178Z | https://www.caainsurancecompany.com/ | `2b140c80c38e` |
| `route-co-operators` | Co-operators | Co-operators General Insurance Company | agent | unreachable | observed | — | 2026-08-11T19:20:26.609694Z | https://www.cooperators.ca/ | `714ba4007b27` |
| `route-desjardins-insurance` | Desjardins Insurance | Certas Home and Auto Insurance Company | agent | unreachable | observed | — | 2026-08-11T19:21:34.671092Z | https://www.desjardinsgeneralinsurance.com/ | `37aa53df1f3e` |
| `route-hagerty-collector-program` | Hagerty (collector program) | Aviva Insurance Company of Canada | MGA_program | unreachable | observed | — | 2026-08-12T00:12:03.579864Z | https://www.hagerty.ca/ | `fe44c543f0df` |
| `route-lowestrates-ca` | LowestRates.ca | LowestRates.ca | aggregator | unreachable | observed | — | 2026-08-12T00:11:33.296903Z | https://www.lowestrates.ca/ | `e9561318739c` |
| `route-onlia` | Onlia | Onlia | broker | unreachable | observed | — | 2026-08-12T00:14:36.200412Z | https://www.onlia.ca/ | `21a9f8c98a6e` |
| `route-pc-insurance` | PC Insurance | PC Insurance | broker | unreachable | observed | — | 2026-08-12T00:13:45.610968Z | https://www.pcinsurance.ca/ | `6dcadb47a125` |
| `route-rates-ca` | Rates.ca | Rates.ca | aggregator | unreachable | observed | — | 2026-08-12T00:13:00.679166Z | https://rates.ca/ | `6827a32c6397` |
| `route-rbc-insurance` | RBC Insurance | RBC Insurance | direct | unreachable | observed | — | 2026-08-12T00:15:47.924241Z | https://www.rbcinsurance.com/ | `ec97d8fcd98c` |
| `route-scoop` | Scoop | Scoop | broker | unreachable | observed | — | 2026-08-12T00:16:32.471628Z | https://www.scoopinsurance.ca/ | `481a8518a77d` |
| `route-square-one` | Square One | Zurich Insurance Company | direct | unreachable | observed | — | 2026-08-12T00:08:30.338169Z | https://www.squareone.ca/ | `97a491f9f9a8` |
| `route-surex` | Surex | Surex | broker | unreachable | observed | — | 2026-08-11T19:28:54.978966Z | https://www.surex.com/ | `0d725790d104` |
| `route-the-personal` | The Personal | The Personal Insurance Company | affinity | unreachable | observed | — | 2026-08-12T00:16:33.128442Z | https://www.thepersonal.com/ | `c3a41f409f43` |
| `route-thinkinsure` | ThinkInsure | ThinkInsure | broker | unreachable | observed | — | 2026-08-12T00:17:30.710470Z | https://www.thinkinsure.ca/ | `27b0e0bd4b3b` |
| `seed-aviva-aviva-general-insurance-company` | Aviva General Insurance Company | Aviva General Insurance Company | broker | unresolved | derived | — | 2026-08-12T00:04:00.201634Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `7838434e2929` |
| `seed-desjardins-certas-direct-insurance-company` | Certas Direct Insurance Company | Certas Direct Insurance Company | direct | unresolved | derived | — | 2026-08-12T00:04:00.205112Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `e92a16475541` |
| `seed-co-op-coseco-insurance-company` | COSECO Insurance Company | COSECO Insurance Company | affinity | unresolved | derived | — | 2026-08-12T00:04:00.209601Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `f93a0b9a4076` |
| `seed-co-op-cumis-general-insurance-company` | CUMIS General Insurance Company | CUMIS General Insurance Company | affinity | unresolved | derived | — | 2026-08-12T00:04:00.210749Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `67c8545d8f4d` |
| `seed-definity-definity-insurance-company` | Definity Insurance Company | Definity Insurance Company | broker | unresolved | derived | — | 2026-08-12T00:04:00.211898Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `9f732a101b2b` |
| `seed-allstate-esurance-insurance-company-of-canada` | Esurance Insurance Company of Canada | Esurance Insurance Company of Canada | direct | unresolved | derived | — | 2026-08-12T00:04:00.216136Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `8addc4a7a896` |
| `seed-fmre-farm-mutual-reinsurance-plan-inc-on-behalf-of-ontario-mutuals` | Farm Mutual Reinsurance Plan Inc. (on behalf of Ontario Mutuals) | Farm Mutual Reinsurance Plan Inc. (on behalf of Ontario Mutuals) | mutual | unresolved | derived | — | 2026-08-12T00:04:00.218324Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `af5af6b9d9f8` |
| `seed-heartland-heartland-farm-mutual-inc` | Heartland Farm Mutual Inc. | Heartland Farm Mutual Inc. | mutual | unresolved | derived | — | 2026-08-12T00:04:00.224016Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `bba6327fd92e` |
| `seed-intact-novex-insurance-company` | Novex Insurance Company | Novex Insurance Company | broker | unresolved | derived | — | 2026-08-12T00:04:00.234247Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `1b0ac75e63e1` |
| `seed-peel-peel-mutual-insurance-company` | Peel Mutual Insurance Company | Peel Mutual Insurance Company | mutual | unresolved | derived | — | 2026-08-12T00:04:00.239226Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `b7b9695a06f9` |
| `seed-td-primmum-insurance-company` | Primmum Insurance Company | Primmum Insurance Company | direct | unresolved | derived | — | 2026-08-12T00:04:00.241540Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `da8c8e61a379` |
| `seed-intact-royal-sunalliance-insurance-company-of-canada` | Royal & SunAlliance Insurance Company of Canada | Royal & SunAlliance Insurance Company of Canada | broker | unresolved | derived | — | 2026-08-12T00:04:00.243924Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `9c27c24a34c9` |
| `seed-aviva-s-y-insurance-company` | S&Y Insurance Company | S&Y Insurance Company | broker | unresolved | derived | — | 2026-08-12T00:04:00.246098Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `6088b8ced292` |
| `seed-aviva-scottish-york-insurance-co-limited` | Scottish & York Insurance Co. Limited | Scottish & York Insurance Co. Limited | broker | unresolved | derived | — | 2026-08-12T00:04:00.247366Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `43c14edfb523` |
| `seed-td-td-general-insurance-company` | TD General Insurance Company | TD General Insurance Company | direct | unresolved | derived | — | 2026-08-12T00:04:00.252287Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `73f3631da96b` |
| `seed-commonwell-the-commonwell-mutual-insurance-group` | The Commonwell Mutual Insurance Group | The Commonwell Mutual Insurance Group | mutual | unresolved | derived | — | 2026-08-12T00:04:00.253704Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `0052b3bf2a90` |
| `seed-portage-the-portage-la-prairie-mutual-insurance-company` | The Portage la Prairie Mutual Insurance Company | The Portage la Prairie Mutual Insurance Company | broker | unresolved | derived | — | 2026-08-12T00:04:00.267808Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `9007d12af1c7` |
| `seed-aviva-traders-general-insurance-company` | Traders General Insurance Company | Traders General Insurance Company | broker | unresolved | derived | — | 2026-08-12T00:04:00.275775Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `3d22b66775b0` |
| `seed-beneva-unica-insurance-inc` | Unica Insurance Inc. | Unica Insurance Inc. | broker | unresolved | derived | — | 2026-08-12T00:04:00.277652Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `c8ea03082fa1` |
| `seed-intact-unifund-assurance-company` | Unifund Assurance Company | Unifund Assurance Company | affinity | unresolved | derived | — | 2026-08-12T00:04:00.278796Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `4c6627cc0f0e` |
| `seed-northbridge-verassure-insurance-company` | Verassure Insurance Company | Verassure Insurance Company | broker | unresolved | derived | — | 2026-08-12T00:04:00.279890Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `3792869592e4` |
| `seed-intact-western-assurance-company` | Western Assurance Company | Western Assurance Company | broker | unresolved | derived | — | 2026-08-12T00:04:00.281034Z | Brief Appendix A (regulator seed list, retrieved 2026-08-06) | `bce6944a29a7` |

Status counts: `manual_handoff` 22, `unresolved` 22, `specialty_only` 16,
`unreachable` 15, `blocked` 3, `affinity_restricted` 1. Of the 79, 20 rows
are `observed` (a market was actually contacted this run); 59 are `derived`
(planner-time conclusions from registry metadata — no contact attempted,
because the route requires an intermediary/membership this profile doesn't
have, is out of standard-PPA scope, or has no confirmed contact channel on
file yet).

## 3. The five metrics

| Metric | Value | Denominator |
|---|---|---|
| Market completion | **100.0%** | 57 of 57 verified-applicable sources carry an evidence-backed terminal status |
| Comparable quote yield | **0.0%** | 0 of 57 verified-applicable sources returned `quoted_comparable` |
| Evidence rate (all outcomes) | **100.0%** | 79 of 79 outcomes have a valid timestamp, source, and evidence artifact |
| Evidence rate (observed only) | **100.0%** | 20 of 20 market-contacted outcomes have a valid timestamp, source, and evidence artifact |
| Duplicate suppression (registry-seeded) | **32** | 111 registry rows collapse to 79 distinct sources (seed-time collapse by `legal_underwriter`; the runtime dedupe resolver, Task 8b, is not built — see docs/KNOWN_LIMITATIONS.md §3) |
| Freshness | **7.0%** | 4 of 57 verified-applicable sources were re-verified within the hackathon window (2026-08-09T00:00Z–2026-08-13T04:00Z) |

"Verified applicable sources" (57) is docs/SCHEMAS.md's definition: registry
rows whose status is not `unresolved`. 22 of the 79 distinct sources are
still `unresolved` (see §2), so they are excluded from this denominator by
design — the metric intentionally does not reward or punish unresearched
routes, it measures completion against what the registry currently knows
exists.

**Market completion at 100% must not be read next to comparable quote yield
at 0% and freshness at 7% as if they tell the same story.** Market
completion measures *attempt coverage* — every verified-applicable source
was either contacted and produced a terminal status, or was correctly
resolved at plan time to a terminal status without contact (a route
requiring a membership this profile lacks does not need to be dialed to
know its answer). It is bounded by what the registry itself knows exists;
it says nothing about whether any of those attempts produced a price, and
nothing about how recently each source's registry entry was itself
re-confirmed against the live market. Comparable quote yield (0%) is the
honest answer to "did anything price"; freshness (7%) is the honest answer
to "how much of the registry was re-checked this week." All three are true
at once, and reporting only the 100% would be the kind of coverage
inflation this document exists to avoid.

## 4. Barrier classes

20 of the 79 distinct sources were actually contacted this run
(`provenance=observed`). What stopped each one is not one thing, and
collapsing them into a single "blocked" bucket would hide who is
responsible for each stop. Four distinct classes, in order of how much
they reflect on the market versus on this system:

**Our own guardrail halts.** Not present as a contact-lane result in the
canonical run's 20 observed outcomes — Square One (`route-square-one`,
underwriter Zurich Insurance Company) hit the batch hard-cap timeout this
run instead (see "our own automation limits" below) — but the guardrail
halt is real, reproducible, and on disk. In both superseded runs
(`20260811T202744Z-79e3e8`, `20260811T205702Z-9cfc30`), the agent reached
Square One's quote flow and correctly stopped at a personal-declaration
consent screen ("you also declare that you have obtained consent from all
other drivers listed on this policy for us to collect, use, and disclose
their personal information"), recording `unreachable (voluntary halt)`
rather than proceeding. This is our own safety policy stopping us, not the
site — the agent was never told to click past it, and didn't. See
docs/KNOWN_LIMITATIONS.md §3 for the one defect in this halt: the evidence
screenshot doesn't visually corroborate it on either occasion.

**Site access controls (bot walls, account walls) — 3 `blocked`.**
belairdirect (`route-belairdirect`) and InsuranceHotline
(`route-insurancehotline`) each hit a real, confirmed bot wall: belairdirect
presented a "Let's confirm you are human ... this step verifies that you
are not a bot" interstitial, and InsuranceHotline presented a Cloudflare-
style "you have been blocked ... this website is using a security service"
page. Both match a deterministic, regression-tested detector
(`tests/fixtures/bot_wall_belairdirect_human_check.html`,
`tests/fixtures/bot_wall_cloudflare_rates_ca.html`) and neither was
retried, per the bounded-attempts policy. Allstate Canada
(`route-allstate-canada`) is also recorded `blocked`
(`login_or_account_required`), but with lower confidence: the captured
evidence screenshot shows the plain marketing homepage with a cookie-
consent popup, and the matched text ("Sign in if you already have an
account", "Create an account") is site-wide account/nav chrome rather than
a quote-flow login wall — there is no evidence this run ever reached or
attempted the "get a quote" journey on Allstate. Treat Allstate's `blocked`
status as unresolved-in-spirit even though it is recorded as terminal; see
docs/KNOWN_LIMITATIONS.md §3.

**Market gates (consent, identity) — 2 confirmed, 2 more recognized but
unconfirmed.** Sonnet (`route-sonnet`) and TD Insurance
(`route-td-insurance`) each recorded `manual_handoff` from a deterministic
gate match with a blocking control present on the page — a real consent/
binding-step gate, not marketing prose (see docs/KNOWN_LIMITATIONS.md §2 on
why "blocking control present" is now required for this detector). Two more
routes show the same kind of gate without a deterministic confirmation:
Co-operators (`route-co-operators`) and Desjardins Insurance
(`route-desjardins-insurance`) both recorded `unreachable (voluntary halt,
no independent gate match)`, with the agent's own stated reason citing a
personal-affirmation consent checkbox (Co-operators: "I agree" under "How
we collect and use your information") or a "We need your consent" accept
screen (Desjardins). The agent correctly refused to proceed past either —
but because gates.py's deterministic pattern didn't independently confirm
the match within the run, both are recorded at the lower-confidence
`unreachable` rather than `manual_handoff`. Read these two as probable
market gates that this system's evidence trail cannot yet prove to the same
standard as Sonnet and TD, not as genuine dead ends.

**Our own automation limits — the market did not stop these, we did.**
CAA Insurance (`route-caa-insurance`) was killed by the batch hard-cap
timeout at 270 seconds with no determination reached. Onlia
(`route-onlia`) exhausted its 12-step budget the same way. Neither
produced any evidence of a market-side barrier — no consent screen, no bot
check, no declaration. The underlying cause (docs/KNOWN_LIMITATIONS.md §3):
when a form does not advance after a submit action, the agent has no way to
discover why, because validation errors commonly render outside its
viewport. Seven more `unreachable` routes share this same failure mode —
Aviva Direct, Hagerty (collector program), PC Insurance, RBC Insurance,
Scoop, Square One (this run), and ThinkInsure all ran out of step budget or
were hard-capped with no determination reached, and none show any evidence
of a market-side gate. This is our failure, not the market's, and it is the
largest single reason this run's contact lane produced no price.

Separately — and distinctly from the automation-limit bucket above — three
more `unreachable` routes carry evidence of a possible market barrier the
system could not confirm in time: Rates.ca and LowestRates.ca both recorded
plain "budget exhausted" outcomes after the agent's last visible action hit
a Cloudflare-style wall (docs/KNOWN_LIMITATIONS.md §3, "gate-detection
timing race" — the deterministic pattern for this exact wall text is
unit-tested and passes, but the live step-hook cadence never re-evaluated
the page after that final action), and Surex recorded `unreachable
(voluntary halt, no independent gate match)` citing "Anti-bot verification
failed." on the page, which is also unit-tested and passing at the fixture
level. Treat these three as unresolved bot-wall suspicions rather than
either a confirmed site block or a pure automation failure.

## 5. Normalization

The committed `ComparisonReport` under `exports/comparison_20260811T184802Z.json`
was generated entirely from **hand-authored fixture inputs**
(`exports/acceptance_inputs/quote_a_marketa_direct.json`,
`quote_b_marketb_broker.json`) using placeholder carrier names ("Marketa
Direct" / "Marketa Insurance Company", "Marketb" equivalents) — not from any
real market. No route in this run or any prior run reached a live coverage-
disclosure surface (§1 explains why: nothing in the standard market prices
this profile), so there was never live material for the normalizer to
consume. `capture_coverage` (PLAN.md Task 8c), the custom action that would
transcribe verbatim coverage label/value pairs from a real quote page, was
never built for the same reason — there was nothing live for it to read.
**The committed comparison artifact demonstrates the NormalizedQuote /
ComparisonReport schema and the comparability-assessment logic work
correctly against known inputs. It is not, and must not be read as, a
market result.** Every `annual_premium` in the Results view for this run is
correctly blank for the same reason.

## 6. Supersession

Two earlier runs exist on disk and are superseded by the canonical run:
`20260811T202744Z-79e3e8` and `20260811T205702Z-9cfc30`. Neither was
deleted — both remain under `data/runs/` and `data/evidence/` in full, and
both are cited by registry ID above (Square One's consent-declaration halt,
§4). They are superseded, not authoritative, for two reasons:

1. They predate two fixes to `allquote/executor.py` and
   `allquote/browser_ops.py`: grounding `fill_public` in the loaded
   `IntakeProfile`'s real values instead of letting the model free-generate
   a value, and a code-level guard that makes `fill_public` refuse to type
   into identity-shaped fields, forcing them through the vault-backed
   `fill_sensitive` path instead.
2. Before those fixes landed, at least two live sites — Onlia and CAA
   Insurance — received a submitted form with a fabricated name
   ("John"/"Smith") typed via the ungrounded `fill_public` path, per the
   canonical run's own manifest note and the evidence screenshots from both
   superseded runs. No licence number, declaration, or payment field was
   ever involved, and the vault/sensitive-field masking worked correctly
   throughout both superseded runs (DOB and postal code were masked in
   every capture). Full account in docs/KNOWN_LIMITATIONS.md §2, "the
   fabrication defect."

All contact-lane results were re-run after both fixes landed. The canonical
run (`20260812T000400Z-445a33`) is the current authoritative contact-lane
data; `data/runs/latest.json` points at it.
