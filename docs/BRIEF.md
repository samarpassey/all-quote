ONTARIO ALL-QUOTE AGENT CHALLENGE              PARTICIPANT BRIEF




                                     HACKATHON CHALLENGE BRIEF



                            Ontario All-Quote
                              Agent Challenge
            One intake. Every reachable rate. Evidence for every result.

          Build an agentic tool that obtains and compares Ontario private-passenger
            auto insurance quotes across direct, agent, broker, aggregator, affinity,
                     specialty, MGA/program and residual-market channels.



                                                   KICKOFF

                          Sunday, August 9, 2026 | 9:00 AM to 5:00 PM ET

                                            SUBMISSION DEADLINE

                             Wednesday, August 12, 2026 | 11:59 PM ET


             Individual participation | Ontario residents only | In-person or remote participation




                                                                                                     Page 1
ONTARIO ALL-QUOTE AGENT CHALLENGE                 PARTICIPANT BRIEF



1. The challenge

    PERSONAL-USE CHALLENGE Build YOUR OWN personal assistant to get and compare YOUR OWN Ontario
    auto-insurance rates. It must work only for the participant's own insurance-shopping needs and must not
    obtain quotes, make calls or submit information for anyone else.



    BEFORE YOU START Enter individually, be an Ontario resident and build only for your own insurance-
    shopping needs. Use only your own information for live interactions. If you do not drive or do not have a
    licence, you can still compete using the permitted estimate-only or discovery route described below. You
    are responsible for your own tools and costs unless the Organizer announces otherwise.



    MISSION Take the participant's own accurate profile and attempt to obtain a comparable quote from
    every distinct Ontario private-passenger auto rate source available to that participant.


The finished product should feel like a capable insurance-shopping operator for its own developer. It
collects the participant's data once, plans the right route for each market, completes available web,
phone, broker or other permitted journeys, normalizes the results, and explains what it could not
obtain.

This is not a model-training exercise and it is not a bulk-scraping contest. The hard parts are market
discovery, workflow orchestration, reliable computer use, truthful voice interaction, data normalization,
privacy and honest accounting of coverage. The rate is not the prize; a working, evidence-backed
retrieval flow is.

What success looks like
     One intake: the applicant enters each material fact once.
     Broad reach: direct writers, exclusive agents, broker panels, affinity programs, specialty programs,
      mutuals and the residual market are all considered.
     Open-ended execution: use whatever permitted combination of tools, automation and human
      handoffs best reaches the market without prescribing one SDK, browser framework or interface.
     Comparable output: premiums are shown only beside matching coverage assumptions, with
      differences called out.
     Proof, not claims: every market ends in a quote or an evidence-backed terminal status.
     Safe by design: no fabricated licence numbers, no hidden automation, no binding a policy and no
      sensitive data in logs or repositories.




                                                                                                          Page 2
ONTARIO ALL-QUOTE AGENT CHALLENGE               PARTICIPANT BRIEF



What “every” means
“Every” means every distinct, current rate source that the applicant can lawfully and truthfully access for
the stated risk. A consumer brand, legal underwriting company, insurer group and broker panel may
describe the same underlying rate source. Conversely, one insurer group may expose different programs
through direct, affinity and broker channels. Your system must discover and deduplicate those
relationships.

Participant profile and eligibility
   You must be an Ontario resident when you register, participate and submit. Ontario residence, not
    citizenship, is the relevant eligibility requirement.
   In-person attendance on August 9 is encouraged but not required. Ontario residents may participate
    remotely and remain eligible if they meet the submission requirements and deadline.
   Entries are individual only. Teams, shared repositories, joint submissions and pooled work are not
    permitted unless the Organizer gives prior written approval.
   This is the participant's personal assistant for the participant's own rates. It is not a service for
    friends, family, customers or the public.
   Use the participant's own accurate information for any live quote or interaction with a real insurer,
    agent or broker. A shared canned driver profile is deliberately not provided and the quoted rate
    itself is not being judged.
   You do not need to drive or hold an Ontario driver's licence to compete or win. This is okay because
    judging rewards safe market discovery, routing, evidence, clear handoffs and normalized results, not
    a completed rate. A participant without a licence may demonstrate discovery or an estimate-only
    workflow using a clearly labelled hypothetical profile only in a local sandbox or a destination flow
    that expressly permits non-binding estimates based on assumptions.
   A hypothetical profile must never contain a driver's licence number, enter a verification, consent,
    declaration, callback or purchase step, or be represented to a real person as a real applicant. The
    system must label that outcome estimate_only, manual_handoff or blocked as appropriate.




                                                                                                            Page 3
ONTARIO ALL-QUOTE AGENT CHALLENGE                   PARTICIPANT BRIEF



Coverage and guardrails

    COVERAGE RULE A complete attempt does not require a price from an unavailable market. It does
    require evidence. Accepted terminal statuses include quoted, estimate only, callback required, manual
    handoff, ineligible, affinity restricted, specialty only, duplicate rate source, not currently writing, access
    blocked by terms or CAPTCHA, unreachable after a bounded attempt, and unresolved.




Out of scope
      Purchasing, binding, renewing, cancelling or modifying an insurance policy.
      Submitting payment information, an electronic signature or an application declaration.
      Bypassing CAPTCHAs, bot controls, authentication, rate limits or other access controls.
      Using another person's identity, licence number, address, vehicle, claims history or consent, or
       presenting hypothetical information as a real applicant's information.
      Changing material facts across insurers to manufacture a lower premium.
      Presenting an estimate, lead form or callback promise as a firm quote.


2. Required system behaviour
Recommended orchestration flow:

           Consent-aware intake → market registry → route planner → browser and voice agents →
                    evidence store → quote normalizer → coverage ledger and comparison

Tooling freedom
Browser automation is an example, not a requirement. Choose any permitted technical approach that
produces a trustworthy result: computer use, browser automation, approved APIs or integrations, voice,
structured data capture, a licensed intermediary, a human-in-the-loop workflow or another creative
design. There is no prescribed SDK, model, browser framework, dashboard or visible cursor interaction.
Participants supply their own accounts, tools, API access and credits. The Organizer does not reimburse
those costs unless it announces a specific reimbursement or discount in writing.

Freedom of approach does not authorize access-control evasion. Do not bypass CAPTCHAs, bot
controls, authentication, rate limits or destination terms, and do not use private endpoints or
credentials without the owner's authorization.

Web and computer-use routes
      Navigate official direct-writer sites and approved broker or aggregator quote journeys.




                                                                                                                 Page 4
ONTARIO ALL-QUOTE AGENT CHALLENGE               PARTICIPANT BRIEF



   Map each question to the canonical intake schema and ask the user only when a genuinely new field
    appears.
   Pause before any identity lookup, consent attestation, signature, payment or purchase action.
   Capture the source URL, timestamp, quote or reference ID, premium, coverage, discounts, validity
    period and a redacted evidence artifact.
   Stop at CAPTCHAs or explicit anti-automation barriers and record the status. Do not evade them.

Voice agents
Use voice when a website will not return a rate, routes the user to a sales line, promises a callback, or
when a broker must reach a market manually. The implementation may place outbound calls and
receive inbound callbacks.

Where a web journey yields a quote or reference ID before a call, preserve that ID, source URL, partial
progress and consent state. Hand the context to the caller so the representative can continue the same
journey; record whether the handoff returned a rate, an eligibility answer or an exact blocker.

Suggested outbound opening

    Hello, I am an automated assistant acting for [applicant's legal name] to request an Ontario private-
    passenger auto insurance quote. Is it okay to continue with an automated assistant? The applicant is
    available if you need verification or consent.

Suggested inbound opening

    Thank you for calling back. I am an automated assistant receiving this call for [applicant's legal name].
    May I continue, or would you prefer to speak directly with the applicant?

   Disclose that the agent is automated and identify the purpose at the beginning of every call.
   Do not misrepresent the caller as a licensed broker, agent, insurer employee or human applicant.
   Do not claim affiliation with the organizer, an insurer or a brokerage. Do not volunteer irrelevant
    event details, but if asked about the prototype or its operator, answer truthfully and offer to
    transfer to the participant.
   Do not record or transcribe unless the other party affirmatively agrees. If consent is refused, retain
    only structured, non-audio outcome notes.
   Never spoof caller ID, pressure a representative, place repeated calls or continue after a request to
    stop.
   Escalate immediately when the representative requires the applicant, licensed advice, a declaration,
    identity verification or consent to obtain third-party records.




                                                                                                            Page 5
ONTARIO ALL-QUOTE AGENT CHALLENGE                      PARTICIPANT BRIEF



Human checkpoints
    Checkpoint                         Required behaviour

                                       Applicant confirms the legal name, licence use and consent immediately before
    Identity or database lookup
                                       submission.

    Application declaration            Stop. Do not click or sign as part of the challenge.

                                       Present options and differences. Do not recommend suitability unless handled by a
    Coverage advice
                                       licensed professional.

    CAPTCHA or access restriction      Hand off only if permitted; otherwise log the blocker.

    Quote-to-purchase transition       Stop after saving the quote details. Do not bind.



3. Build the Ontario market map
The public auto-rate approval dataset returned 60 legal insurer records across 32 insurer groups on
August 6, 2026. Use that dataset as the regulatory seed, not as a claim that all 60 entities are currently
open for standard retail new business. It includes recent retail writers, specialty and commercial names,
legacy entities and multiple legal companies within the same group. [1]

Keep these layers separate
    Layer                         Meaning for the project

    Legal underwriter             The licensed company named on the policy or rate filing.

    Insurer group                 The parent or operating group that may contain several legal underwriters.

    Consumer brand                The name the applicant sees. It may be a direct brand, affinity brand or broker brand.

                                  A direct writer, exclusive agent, independent broker or digital brokerage that can place
    Distributor
                                  the business.

                                  A comparison or lead platform. Its output is only as broad as its live panel and the
    Aggregator
                                  applicant's eligibility.

                                  An administrator or wholesale market with delegated authority. It is not automatically a
    MGA or program
                                  distinct insurer or standard auto market.

                                  A market of last resort accessed through a licensed broker or agent, not a normal direct
    Residual market
                                  quote path.


Required market-registry fields
      registry_id and last_verified_at
      legal_underwriter and insurer_group
      brand or program_name



                                                                                                                         Page 6
ONTARIO ALL-QUOTE AGENT CHALLENGE                        PARTICIPANT BRIEF



      distribution_type: direct, exclusive agent, broker, aggregator, affinity, MGA/program, mutual or
       residual
      product_scope: standard PPA, non-standard PPA, high-net-worth, collector, affinity,
       commercial/specialty or unknown
      quote_url, public sales number and callback route
      known_panel_source and licensed intermediary
      requires_licence, requires_VIN, requires_membership and requires_human
      terms_or_automation_notes
      status, evidence_url or redacted artifact, and source citation
      distinct_rate_source_id for deduplication

A practical route strategy
    Route                   Action                                              Why it matters

                            Attempt Allstate, Aviva Direct, belairdirect,       Captures rates that broker panels may not expose.
    Direct and exclusive-   CAA, Co-operators, Desjardins, RBC Insurance,       CADRI identifies eight major direct-relationship
    agent set               Sonnet, Square One, TD Insurance and The            members; CAA and Square One add current public
                            Personal where the applicant qualifies.             quote routes. [3] [7] [8]

                                                                                LowestRates currently names CAA, Coachman,
                            Use either Rates.ca or LowestRates.ca first,        Economical, Gore, Pafco, Pembridge, SGI, Travelers
    Broad broker engine A
                            then inspect the returned legal underwriters.       and Zenith for auto quotes. Rates.ca describes
                                                                                insurer API and industry-rater connectivity. [9] [10]

                            Use Surex to add or verify Aviva, Intact, Jevco,
                            Wawanesa, CAA, Coachman,                            Its compensation disclosure is more useful than logo
    Broad broker engine B   Definity/Economical, Gore, Pafco, Pembridge,        counts because it names insurer and MGA
                            SGI and Travelers, subject to the live panel and    relationships. [11]
                            profile.

                            Use a broad licensed brokerage such as
                                                                                Ontario law requires a broker to provide the names
    Independent broker      ThinkInsure, Onlia or Scoop, or another RIBO-
                                                                                of its automobile insurer contracts and quote
    verifier                licensed broker, and request the complete
                                                                                information obtained for the applicant. [6]
                            carrier list and all quote outcomes.

                            Contact Ontario mutuals, affinity programs,
                            high-net-worth markets, collector programs          These are often absent, restricted or collapsed in
    Gap-fill routes
                            and the residual market through their actual        mainstream aggregator output. [12] [13]
                            route.

Panel membership changes. Participants must verify each route during the hackathon and record the date, source and returned
underwriter. A claim such as “50+ providers” does not prove that 50 Ontario PPA quotes were produced for one profile.


4. Channel coverage requirements

Direct, affinity and digital routes
    Route                   Primary journey                                Known underwriting layer

    Allstate                Online quote plus agent path                   Allstate Insurance Company of Canada



                                                                                                                                  Page 7
ONTARIO ALL-QUOTE AGENT CHALLENGE                       PARTICIPANT BRIEF



Starting map only. The implementation must capture the legal underwriter actually returned on the quote or disclosure page. [3]
[7] [8] [14] [15] [16] [17] [18]


Broker, aggregator and branded-broker routes
    Route                         How to use it

                                  Broad online comparison. Treat as overlapping routes until the returned panels prove
    Rates.ca / LowestRates.ca
                                  otherwise.

    Surex                         Broad licensed brokerage and callback route; useful published carrier and MGA disclosure.

    ThinkInsure                   Broad independent brokerage, web intake and advisor completion.

                                  Digital brokerage with multiple carriers; capture the actual returned insurer, not the
    Onlia
                                  brokerage brand.

    Scoop                         Digital brokerage and callback workflow; confirm full panel.

    PC Insurance                  Branded digital brokerage; capture the returned underwriter and any eligibility discount.

    Inova                         Membership-based brokerage route; verify membership and actual panel.

    InsuranceHotline              Lead and broker-network route, not itself the underwriting company.

                                  Essential for full market disclosure, mutuals, non-standard, specialty and residual-market
    Local independent broker
                                  access.


MGA, program and specialty discovery

Do not assume that every MGA produces a separate standard auto rate. Start with Hagerty for collector
vehicles, where the program is administered separately and underwritten by Aviva. Treat Agile, APRIL
Canada, Burns & Wilcox, Cambrian Special Risks, Milnco and Special Risk as discovery leads from broker
disclosures. Count one only after verifying that it accepts an individual Ontario private-passenger risk
relevant to the profile. [11] [13]

      Non-standard auto: test Echelon, Jevco, Pafco and Coachman through licensed broker routes when
       the profile fits.
      High-net-worth or specialty: verify Chubb and PURE through an appointed broker, and avoid
       counting a market that the user cannot access.
      Collector vehicles: route to Hagerty only if the vehicle and household meet program rules; it is not a
       daily-driver substitute.
      Residual market: Facility Association is the fallback for otherwise hard-to-place risks and is accessed
       through a licensed intermediary.
      Mutuals: use the Ontario Mutuals locator and validate product availability and territory with the
       specific mutual.




                                                                                                                           Page 8
ONTARIO ALL-QUOTE AGENT CHALLENGE                 PARTICIPANT BRIEF



5. Canonical intake schema
The OAF 1 is the authoritative backbone for the information required to complete an Ontario auto
insurance application. The quote agent should collect a superset of those fields, while applying data
minimization and asking only what is necessary for the selected route. [2]

Applicant, contact and household
 Data group               Fields and rules

                          Consent timestamp; live-quote or discovery mode; permitted channels; approved insurers or
 Consent and mode
                          brokers; callback permission; recording or transcription choice.

                          Alias for permitted discovery-only use; legal name for a live quote; preferred language; date of
 Identity
                          birth; gender field as required by the form; marital status.

 Contact                  Email, mobile, home or work phone, preferred callback window.

                          Street, unit, city, province, postal code, residence start date, prior address if a route requires
 Primary address
                          it, and confirmation that this is the normal residence and garaging location.

                          All licensed household members, all regular vehicle users, dependants relevant to optional
 Household
                          benefits, and other vehicles in the household.


Driver information
 Data group               Fields and rules

                          Name exactly as shown on the licence; own valid Ontario driver's licence number when
 Licence identity
                          required; province; class; status; expiry if requested.

                          Dates or years for G1, G2 and G; date first licensed in Canada or the U.S.; other classes;
 Licensing timeline
                          recognized out-of-country experience and proof availability.

 Training                 Approved driver-training completion and certificate availability.

 Assignment               Principal, secondary or occasional driver; percentage use by vehicle; other regular access.

                          Retiree criteria, student status, good-driver or group discounts, and willingness to consider
 Discount eligibility
                          telematics. Keep telematics quotes separate unless the user opts in.

                          All other licensed persons in the household or business and whether they have their own
 Other drivers
                          policy or require an exclusion form.


Vehicle and use
 Data group               Fields and rules

                          VIN; model year; make; model; trim or body type; engine or fuel type; cylinders or engine size
 Vehicle identity
                          and GVWR where requested.

                          Owned or leased; new or used; purchase or lease month and year; purchase price; registered
 Ownership
                          owner; actual owner; lienholder or lessor details.




                                                                                                                        Page 9
ONTARIO ALL-QUOTE AGENT CHALLENGE                     PARTICIPANT BRIEF



 Data group                  Fields and rules

                             Pleasure, commute, school, business, farm or commercial; one-way commute distance; annual
 Use
                             kilometres; business-use percentage; days commuting; carpool and passenger count.

                             Garaging address; unrepaired damage; modifications or customization; non-factory
 Risk details
                             equipment; winter tires; approved theft-recovery device; anti-theft features.

                             Rideshare, delivery, carshare, rental to others, passengers for compensation, trailer use,
 Special use                 explosives or radioactive materials. These answers may trigger commercial or specialty
                             handling.

 Household fleet             Total household or business vehicles and driver-to-vehicle allocation.



6. History, coverage and quote controls

Insurance and driving history
 History group               Fields and lookback

                             Insurer, policy number, expiry date, current premium if volunteered, years continuously
 Current insurance
                             insured, and reason for shopping.

                             Any driver's licence, vehicle permit or similar suspension or cancellation in the last 6 years,
 Licence and permit events
                             with dates and details.

 Insurance cancellations     Any insurer cancellation in the last 3 years, including non-payment where asked.

 Misrepresentation           Any policy cancellation or claim denial for material misrepresentation in the last 3 years.

 Fraud finding               Any court finding of fraud connected with auto insurance.

                             All ownership, use or operation accidents and claims in the last 6 years: driver, vehicle, date,
 Accidents and claims
                             fault percentage if known, coverage, paid or estimated amount and details.

 Convictions                 All driving convictions in the last 3 years: driver, conviction date and description.


Coverage configuration
Every route must receive the same requested effective date and benchmark coverage package. If a route
cannot match it, preserve the quote but mark it non-comparable and list every difference.

 Coverage group              Normalization requirement

 Policy timing               Requested effective date; 12-month term where available; same quote date window.

                             Selected limit, such as $1 million or $2 million. Ontario's legal minimum is $200,000, but the project
 Third-party liability
                             must use one consistent user-selected limit.

                             Mandatory medical, rehabilitation and attendant care; requested increased limits; explicit included
 Accident benefits
                             or excluded status for every optional benefit after July 1, 2026.




                                                                                                                            Page 10
ONTARIO ALL-QUOTE AGENT CHALLENGE                       PARTICIPANT BRIEF



 Coverage group                Normalization requirement

                               Income replacement; non-earner; caregiver; lost educational expenses; expenses of visitors;
                               housekeeping and home maintenance; damage to personal items; death; funeral; dependant care;
 Optional benefits to record
                               indexation; supplementary or increased medical, rehabilitation and attendant care; catastrophic
                               impairment.

 Uninsured automobile          Included status and limit details where returned.

                               Included or opted out; deductible if any. If the applicant elects OPCF 49, collision and all-perils
 DCPD
                               implications must be surfaced.

 Own-damage coverage           Specified perils, comprehensive, collision or all perils; deductible for each.

                               At minimum track OPCF 20 transportation replacement, OPCF 27 non-owned automobiles, OPCF 43
 Endorsements
                               removing depreciation deduction and OPCF 44R family protection when offered or requested.

                               Bundle, multi-vehicle, winter tires, theft-recovery, driver training, claims-free, conviction-free,
 Discounts
                               retiree, affinity and telematics. Record which discounts are conditional.

                               Annual versus monthly premium; finance charge or instalment fee; deposit; number and amount of
 Payment
                               instalments. Never submit payment.

Ontario changed accident-benefit defaults on July 1, 2026. Only medical, rehabilitation and attendant care remain mandatory
for new policies; other accident benefits are optional and must be captured explicitly. [19] [20]


Suggested demo benchmark

 APPLES-TO-APPLES For the demo, use one disclosed configuration such as $2 million third-party liability,
 DCPD included, standard mandatory medical/rehabilitation/attendant-care benefits, collision and
 comprehensive with $1,000 deductibles, OPCF 44R, and no telematics unless separately opted into. This
 is a comparison benchmark, not coverage advice. Record every optional benefit as included, excluded,
 unavailable or unknown.




7. Normalize and prove every result

Quote result schema
 Result group                  Required output

 Source identity               Registry ID, brand, legal underwriter, group, intermediary and distinct rate-source ID.

 Outcome                       Status enum, exact quote versus estimate, eligibility result, failure reason and next action.

                               Annual premium, monthly amount, down payment, instalment or finance charges, taxes or
 Price
                               fees, total estimated cost and currency.

                               All requested limits, deductibles, optional benefits and endorsements, plus any variance from
 Coverage
                               the benchmark.

                               Applied, available but not selected, conditional on purchase, bundle, membership or
 Discounts
                               telematics.



                                                                                                                                 Page 11
ONTARIO ALL-QUOTE AGENT CHALLENGE                   PARTICIPANT BRIEF



    Result group            Required output

                            Quote or reference ID, effective date, expiry or guarantee date, and whether verification may
    Validity
                            change the premium.

                            Timestamp, source URL or public phone route, redacted screenshot or call outcome, and
    Evidence
                            evidence hash or artifact link.

                            High for a returned exact premium with matching coverage; medium for a licensed
    Confidence
                            representative's documented quote; low for an estimate or unresolved coverage difference.

                            Fields disclosed to the route, consent receipt, retention deadline and proof that secrets were
    Privacy
                            excluded from logs.


Status enum
    Status                          Meaning

    quoted_comparable               Exact premium and benchmark coverage matched.

    quoted_non_comparable           Exact premium returned, but one or more coverage assumptions differ.

    estimate_only                   Indicative price, range or lead estimate, not a firm quote.

    callback_required               A licensed representative must call before a rate is available.

    manual_handoff                  Applicant or human operator is required for consent, identity or advice.

    ineligible                      The profile fails an approved rule or product requirement, with the stated reason.

    affinity_restricted             A valid group, employer or membership relationship is required.

    specialty_only                  The route does not write standard private-passenger use for this profile.

    duplicate_rate_source           A different brand or route resolved to the same underlying rate program.

    not_currently_writing           Evidence indicates no new applicable Ontario PPA business.

    blocked                         Terms, CAPTCHA, authentication or another access control prevents automation.

    unreachable                     A bounded number of attempts produced no response.

    unresolved                      More research is required; never silently convert this to “not offered.”


Coverage metrics
      Market completion = distinct rate sources with evidence-backed terminal status ÷ verified applicable
       rate sources.
      Comparable quote yield = quoted_comparable results ÷ verified applicable rate sources.
      Evidence rate = outcomes with a valid source, timestamp and redacted artifact ÷ all outcomes.
      Duplicate suppression = brands or routes mapped to an existing distinct_rate_source_id rather than
       counted twice.
      Freshness = percentage of registry records verified during the hackathon window.




                                                                                                                         Page 12
ONTARIO ALL-QUOTE AGENT CHALLENGE                PARTICIPANT BRIEF



Comparison experience
The user should be able to sort by annual cost, see coverage differences before price differences, filter
estimates out, open the evidence for each outcome and understand exactly which markets remain
unresolved. Never label the lowest displayed number as “best” without surfacing non-price differences
and eligibility conditions.


8. Identity, privacy and safety rules

    NON-NEGOTIABLE Use truthful risk information. The current OAF 1 warns against false particulars,
    misrepresentation and false documents. The regulator also identifies policy misrepresentation and quote
    manipulation as auto-insurance fraud categories. [2] [21]




Alias and driver's licence rule
     An alias may be used only for discovery or an estimate path that does not verify identity, does not
      request a declaration that all information is true and permits that use under the site's terms.
     For a live consumer quote, use the participant's own legal name and accurate risk information.
     If any route requests a driver's licence number, use only the participant's own valid Ontario licence
      number and the legal name exactly matching that licence.
     Never invent, generate, borrow, alter or store another person's driver's licence number.
     If alias mode reaches an identity check, database lookup, consent declaration or application
      attestation, stop and switch to an explicit human checkpoint. Do not mix an alias with a real licence
      number.
     If the participant has no licence, do not attempt to work around the field. Stop at that point and
      preserve the earlier, non-verifying estimate or route-discovery evidence. That is an acceptable
      challenge outcome.

Consent and other household drivers
     Obtain the participant's explicit consent before sharing any personal data with a quote route.
     Do not enter another household driver's information without that person's consent. The OAF 1
      declaration requires the applicant to have obtained listed drivers' consent for collection, use and
      disclosure of driving, policy and claims history.
     Show the user which route will receive which fields before submission and let the user exclude a
      route.
     Treat licence numbers, date of birth, address, claims history, voice data and VIN as sensitive data.




                                                                                                        Page 13
ONTARIO ALL-QUOTE AGENT CHALLENGE             PARTICIPANT BRIEF



Secure implementation
   Keep sensitive fields in a dedicated encrypted vault and inject them only into the destination that
    needs them.
   Mask licence numbers and other identifiers in the UI; never place them in prompts, traces, analytics,
    screenshots, demos, source control or submitted datasets. Do not retain raw page captures or call
    transcripts that include them.
   Redact browser and call evidence before saving or presenting it.
   Use least-privilege access, short retention and a one-click delete function. Delete hackathon quote
    data after judging unless the participant explicitly chooses otherwise.
   Keep consent receipts, access logs and deletion records separate from the quote display.
   Follow the destination's terms, privacy notice and rate limits. Stop if automated access is not
    permitted.

Phone and recording safety
Canadian criminal law permits interception with consent from an originator or intended recipient, but
privacy obligations and organizational policies can impose additional duties. For this challenge, use the
stricter rule: disclose automation, ask for affirmative recording or transcription consent, and do not
retain audio if consent is not granted. Automated or unsolicited calling rules may also apply depending
on how a system is deployed. Do not treat a hackathon prototype as production-ready telephony
compliance. [22] [23] [24]

Legal and professional boundary
The prototype obtains and compares information. It does not sell insurance, bind coverage, provide
licensed advice or decide which coverage is suitable. If the experience crosses into advice or purchase,
transfer the user to a properly licensed broker, agent or insurer representative.

Personal-use protection
This is a personal-use hackathon prototype, not a commercial product. Do not sell, license, market,
publish for public use, or deploy the submission as an insurance-quote service. This boundary is there to
protect you: commercializing an automated insurance-quote product without the required permissions
can expose you to insurer or provider disputes and litigation, as well as privacy, telemarketing and
regulatory risk. Submission conditions, including ownership and commercialization rights, will be
presented for affirmative acceptance when you submit.




                                                                                                      Page 14
ONTARIO ALL-QUOTE AGENT CHALLENGE                       PARTICIPANT BRIEF



9. Submission requirements

    FORMAT Participation and submission are individual. Ontario residents may participate in person or
    remotely; in-person attendance is encouraged but not required. Submit through the Organizer's
    submission form. A shortlisted participant may be asked to run the system live and explain the evidence
    lineage; a pre-recorded walkthrough or static mock alone does not establish that the system works.
    Submission is conditional on accepting the linked Submission IP Agreement.


      GitHub repository and setup instructions: provide the repository URL and enough instructions for
       judges to understand how the system runs. Use a private repository only if the Organizer has been
       given access.
      Three to five minute Loom walkthrough: show the product, its market-routing logic, one working
       route to a returned quote or exact terminal blocker, two normalized results and one evidence-
       backed no-quote or handoff outcome. Use voice, callback or broker-assisted context handoff where
       the route needs it.
      Machine-readable market registry: submit CSV or JSON with sources, verification dates, channels,
       statuses and distinct rate-source IDs.
      Redacted run report: include the coverage ledger, comparisons, gaps, errors and timestamps
       without real licence numbers or other sensitive data.
      Architecture and safety note: explain agent responsibilities, human checkpoints, consent flow, data
       storage, redaction and deletion.
      Known limitations: state where the system depends on a human, licensed intermediary,
       membership, terms permission or unavailable integration.

Minimum demo acceptance
    Area                     Acceptance check

                             At least one permitted route reaches a returned rate or exact terminal blocker. A browser UI, a
    Retrieval
                             specific SDK and visible cursor movement are not required.

                             Where the chosen journey requires it, show an outbound or inbound voice, callback, broker-
    Cross-channel
                             assisted or other permitted handoff that preserves context and discloses automation.

    Normalization            At least two outcomes use the common schema and show coverage differences.

    Market map               The registry distinguishes legal underwriter, group, brand, distributor and rate source.

    Evidence                 Every demonstrated outcome has a timestamp and redacted evidence.

                             No real licence number, full address, payment data or unredacted call recording appears in the
    Safety
                             submission; no route uses a fabricated licence number.




                                                                                                                         Page 15
ONTARIO ALL-QUOTE AGENT CHALLENGE                PARTICIPANT BRIEF



Review and finalist process
     All qualifying submissions will receive a high-level review of the submission form, repository, Loom
      walkthrough and required artifacts.
     The Organizer may invite up to 10 shortlisted participants to a live remote or in-person walkthrough
      and verification session. A remote shortlisted participant must be able to attend the requested live
      remote session. A live walkthrough may include a request to run the system, explain evidence
      lineage and answer questions about limitations and safety controls.
     Optional demos delivered during the event are showcase opportunities only. They do not replace
      the final submission or determine eligibility by themselves.
     The Organizer will communicate finalist timing, presentation logistics and any follow-up instructions
      directly to selected participants.

Judging focus
     Creativity and interpretation: does the participant find a clever, useful way through a fragmented
      market?
     Domain understanding: does the system correctly separate insurers, brands, brokers, programs and
      coverage differences?
     Technical execution: does the chosen approach work reliably, recover from errors and preserve an
      audit trail?
     Live proof: can the participant show a real run, evidence lineage and, where relevant, a quote-ID or
      callback handoff rather than only pre-canned output?
     Coverage and honesty: how much of the verified market is completed, and are gaps reported
      without inflation or hallucination?
     Privacy and safety: are identity, consent, sensitive data and access controls handled responsibly?
     Communication: can the participant clearly explain what was built, what was quoted and what
      remains unresolved?

    WINNING PRINCIPLE A smaller number of trustworthy, comparable quotes with excellent evidence is
    stronger than a large number of duplicated, estimated or unverifiable results. The best system makes
    both its reach and its uncertainty legible.




Appendix A. Regulatory seed list
The following 32 insurer groups and 60 legal entities appeared in the Ontario regulator's public private-
passenger rate-approval dataset on August 6, 2026. This is a discovery seed. It does not by itself prove
current new-business availability, standard personal-auto scope or a consumer-accessible quote path.
Every row requires current validation. [1]


                                                                                                           Page 16
ONTARIO ALL-QUOTE AGENT CHALLENGE                    PARTICIPANT BRIEF



 Group            Legal entities in seed dataset                                     Starting route / validation note

                                                                                     Specialty/commercial broker; validate PPA
 AIG              AIG Insurance Company of Canada
                                                                                     relevance

                  Allstate Insurance Company of Canada; Esurance Insurance
                                                                                     Allstate direct/agent; Pafco and Pembridge
 Allstate         Company of Canada; Pafco Insurance Company; Pembridge
                                                                                     broker; validate Esurance
                  Insurance Company

                  Aviva General Insurance Company; Aviva Insurance Company of
                                                                                     Direct, RBC, broker and program routes;
 Aviva            Canada; S&Y Insurance Company; Scottish & York Insurance Co.
                                                                                     deduplicate and validate legacy entities
                  Limited; Traders General Insurance Company

 Beneva           Unica Insurance Inc.                                               Broker route

                                                                                     CAA direct/broker; Echelon broker and non-
 CAA              CAA Insurance Company; Echelon Insurance
                                                                                     standard

 Chubb            Chubb Insurance Company of Canada                                  High-net-worth or specialty broker

                  COSECO Insurance Company; CUMIS General Insurance Company;
                                                                                     Co-operators web/agent; affinity and
 Co-op            Co-operators General Insurance Company; The Sovereign General
                                                                                     specialty entities need validation
                  Insurance Company

 Commonwell       The Commonwell Mutual Insurance Group                              Mutual and broker/agent route

                                                                                     Specialty/commercial broker; validate PPA
 Continental      Continental Casualty Company
                                                                                     relevance

 Definity         Definity Insurance Company; Sonnet Insurance Company               Definity/Economical broker; Sonnet direct

                  Certas Direct Insurance Company; Certas Home and Auto Insurance
 Desjardins                                                                          Desjardins web/agent; The Personal affinity
                  Company; The Personal Insurance Company

                                                                                     Broker route; map current legal
 Economical       Economical Mutual Insurance Company
                                                                                     entity/program

                                                                                     Residual-market route through licensed
 FA               Facility Association
                                                                                     intermediary

                                                                                     Ontario Mutuals locator and specific mutual
 FMRe             Farm Mutual Reinsurance Plan Inc. (on behalf of Ontario Mutuals)
                                                                                     validation

 Gore             Gore Mutual Insurance Company                                      Broker route

                                                                                     Specialty/commercial broker; validate PPA
 Hartford         Hartford Fire Insurance Company
                                                                                     relevance

 Heartland        Heartland Farm Mutual Inc.                                         Mutual/local agent or broker

                  Belair Insurance Company Inc.; The Guarantee Company of North
                  America; Intact Insurance Company; Jevco Insurance Company;
                                                                                     belairdirect direct; Intact and Jevco broker;
 Intact           Novex Insurance Company; Royal & SunAlliance Insurance Company
                                                                                     validate legacy/affinity entities
                  of Canada; Unifund Assurance Company; Western Assurance
                  Company

                                                                                     Specialty/commercial broker; validate PPA
 Liberty          Liberty Mutual Insurance Company
                                                                                     relevance

                  Federated Insurance Company of Canada; Northbridge General
                                                                                     Northbridge and Zenith broker; validate
 Northbridge      Insurance Corporation; Verassure Insurance Company; Zenith
                                                                                     Federated/Verassure scope
                  Insurance Company

 Optimum          Optimum Insurance Company Inc.                                     Broker route




                                                                                                                           Page 17
ONTARIO ALL-QUOTE AGENT CHALLENGE                       PARTICIPANT BRIEF



 Group               Legal entities in seed dataset                                    Starting route / validation note

 PURE                PURE Insurance                                                    High-net-worth broker

 Peel                Peel Mutual Insurance Company                                     Mutual/local agent or broker

 Portage             The Portage la Prairie Mutual Insurance Company                   Broker route

 SGI                 Coachman Insurance Company; SGI CANADA Insurance Services Ltd.    Broker route; Coachman non-standard

                                                                                       Specialty/commercial broker; validate PPA
 Sompo               Endurance Specialty Insurance Ltd.; Sompo Japan Insurance Inc.
                                                                                       relevance

                     Primmum Insurance Company; Security National Insurance
 TD                                                                                    TD online, phone and affinity routes
                     Company; TD General Insurance Company

                                                                                       Specialty/commercial broker; validate PPA
 Tokio               Tokio Marine and Nichido Fire Insurance Company Limited
                                                                                       relevance

 Travelers           The Dominion of Canada General Insurance Company                  Broker route

 Wawanesa            The Wawanesa Mutual Insurance Company                             Broker route

                                                                                       Specialty/commercial broker; validate PPA
 XL                  XL Specialty Insurance Company
                                                                                       relevance

                                                                                       Square One direct for Ontario car; specialty
 Zurich              Zurich Insurance Company
                                                                                       broker routes may differ

Names reflect the regulator's public dataset display. Current legal names, amalgamations, product scope and new-business
status must be verified against authoritative sources during the hackathon.


Appendix B. Market-record template
Participants may use the following as a minimum machine-readable record:

 Field                                    Meaning

 registry_id                              Stable internal key

 legal_underwriter                        Licensed company name

 insurer_group                            Parent or operating group

 brand_or_program                         Consumer-facing route

 distribution_type                        direct | agent | broker | aggregator | affinity | MGA_program | mutual | residual

                                          standard_PPA | nonstandard_PPA | high_net_worth | collector |
 product_scope
                                          commercial_specialty | unknown

 distinct_rate_source_id                  Deduplication key

 quote_url                                Official public quote URL

 public_phone_route                       Public sales or callback route

 licensed_intermediary                    Brokerage or agency name and regulator evidence

 requirements                             licence | VIN | membership | callback | human | other




                                                                                                                              Page 18
ONTARIO ALL-QUOTE AGENT CHALLENGE                  PARTICIPANT BRIEF



    Field                             Meaning

    automation_notes                  Terms, CAPTCHA, rate limit and handoff notes

    status                            One value from the brief's status enum

    source_url                        Authoritative evidence

    last_verified_at                  ISO 8601 timestamp

    evidence_artifact                 Redacted screenshot, structured call note or response reference


Recommended bounded-attempt policy
      Web: one normal attempt plus one retry for a transient technical error. Do not retry a rejection,
       CAPTCHA or terms restriction.
      Outbound voice: one call during published sales hours and one retry only if the line fails before
       connection. Do not repeatedly call representatives.
      Callback: wait through the declared callback window, then mark callback_required or unreachable
       with the timestamps.
      Broker: ask once for the complete carrier list and all obtained quote outcomes. Preserve the
       response as evidence.
      Unresolved records remain unresolved. They are not silently dropped from the denominator.


Sources and verification links
Research checked August 6, 2026. Participants should re-verify market relationships and quote paths
because panels, legal entities, eligibility and website flows change.

[1] Ontario private-passenger auto rate approvals

[2] OAF 1: Ontario Application for Automobile Insurance Owner's Form, July 2026

[3] FSRA: Purchasing auto insurance

[4] FSRA: Licensed insurance companies in Ontario

[5] FSRA: Getting an auto insurance quote and Take-All-Comers

[6] Ontario Insurance Act

[7] Canadian Association of Direct Relationship Insurers: members

[8] Square One: car insurance and underwriting

[9] Rates.ca: Ontario auto quotes

[10] LowestRates.ca: named auto quote providers

[11] Surex: insurer and MGA compensation disclosure

[12] Ontario Mutuals: find a mutual




                                                                                                        Page 19
ONTARIO ALL-QUOTE AGENT CHALLENGE                 PARTICIPANT BRIEF



[13] Hagerty Canada: program and underwriting information

[14] Aviva Direct: Ontario quoting and underwriter disclosure

[15] RBC Insurance: Ontario car insurance and underwriter disclosure

[16] TD Insurance: Ontario car insurance quote and purchase flow

[17] Sonnet: Ontario online auto quote requirements

[18] The Personal: group car insurance quote

[19] FSRA: Customize liability and accident benefits

[20] Insurance Bureau of Canada: Ontario auto insurance changes, July 1, 2026

[21] FSRA: Automobile insurance fraud reporting categories

[22] Office of the Privacy Commissioner: Meaningful consent

[23] Criminal Code, section 184: interception and consent

[24] CRTC: Unsolicited telecommunications obligations

 FINAL REMINDER The prototype should help a real person understand the market without pretending
 that an estimate is a quote, a brand is an insurer, an intermediary covers the whole market, or a failed
 attempt never happened.




                                                                                                        Page 20
