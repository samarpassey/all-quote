# Guardrails — hackathon compliance (doubles as the Architecture & Safety Note)

This system obtains and compares information for its own developer. It does not
sell insurance, bind coverage, give licensed advice, or act for anyone else.

## Hard out-of-scope (never implemented, never stubbed)

- Purchasing, binding, renewing, cancelling, or modifying a policy
- Submitting payment info, e-signatures, or application declarations
- Bypassing CAPTCHAs, bot controls, authentication, rate limits, or site terms
- Using anyone else's identity, licence, address, vehicle, claims history, consent
- Presenting hypothetical info as a real applicant; fabricating licence numbers
- Changing material facts across insurers to manufacture a lower premium
- Presenting an estimate, lead form, or callback promise as a firm quote

## Human checkpoints (terminal status, not an exception — see CLAUDE.md)

| trigger | behaviour |
|---|---|
| identity / database lookup | pause; applicant confirms name, licence use, consent |
| application declaration | STOP — never click or sign |
| coverage advice requested | present options + differences only; no suitability advice |
| CAPTCHA / access restriction | log `blocked`; never evade |
| quote-to-purchase transition | save quote details, STOP; never bind |

## Alias / licence rules

- Alias only in discovery/estimate paths that don't verify identity, don't request
  a truth declaration, and permit it under site terms. Alias mode reaching any
  identity check → stop, switch to human checkpoint. Never mix alias + real licence.
- Live quotes: participant's own legal name and accurate info only. Licence field:
  participant's own valid Ontario licence, injected from vault, or stop.

## Voice scripts (verbatim, first utterance of every call)

Outbound: "Hello, I am an automated assistant acting for [legal name] to request an
Ontario private-passenger auto insurance quote. Is it okay to continue with an
automated assistant? The applicant is available if you need verification or consent."

Inbound: "Thank you for calling back. I am an automated assistant receiving this
call for [legal name]. May I continue, or would you prefer to speak directly with
the applicant?"

Rules: never claim to be human, licensed, or affiliated with the organizer or any
insurer/brokerage. Answer truthfully if asked about the prototype; offer transfer
to the participant. No recording/transcription without affirmative consent — on
refusal keep only structured non-audio outcome notes. Never spoof caller ID,
pressure, repeat-call, or continue after a request to stop. Escalate immediately
when the rep requires the applicant, licensed advice, a declaration, identity
verification, or third-party-record consent.

## Data handling

- Sensitive set: licence number, DOB, full address, VIN, phone, email, claims
  history, voice audio. Held only in Fernet-encrypted vault (data/vault.enc);
  injected at fill-time; masked in UI; excluded from logs, prompts, traces,
  analytics, screenshots, source control, and all exports.
- All evidence redacted before first disk write (redact.py); artifacts hashed.
- Consent receipts, access logs, and deletion records stored separately from
  quote display data.
- Per-route disclosure preview: user sees which fields go to which route and can
  exclude any route before submission.
- Retention: one-click delete-all (vault, evidence, results); hackathon data
  deleted after judging unless the participant chooses otherwise.

## Bounded attempts

Web: 1 attempt + 1 retry (transient technical error only). Voice: 1 call + 1 retry
only if the line fails before connection. Callback: wait declared window, then mark
callback_required or unreachable with timestamps. Broker: ask once for full carrier
list + all outcomes; preserve response as evidence. Unresolved stays unresolved.

## Personal-use boundary

Not sold, licensed, marketed, published for public use, or deployed as a service.
Works only for the participant's own insurance shopping.

## Known limitations (maintain as they're discovered)

- (fill during build: routes needing membership, human, or licensed intermediary;
  sites blocked by terms; panels unverified; telephony not production-compliant)
- Shape-based text redaction (licence/VIN/postal-code/phone/DOB patterns in
  redact.py) is regex-based, not exhaustive. It can over-redact a benign
  look-alike string (e.g. an unrelated 17-character code, or a non-DOB date) —
  an accepted tradeoff; the failure mode is always over-redaction, never a
  sensitive value surviving.
- The vault's Fernet key (vault.py) is derived from `VAULT_KEY` via a single
  SHA-256 pass, not a proper password-KDF (PBKDF2/scrypt). Acceptable for a
  personal single-user hackathon vault; not production-grade key derivation.
- The browser executor's `sensitive_data` dict (browser_ops.py, Task 5) is
  populated lazily, at the moment `fill_sensitive` resolves a value from the
  vault — intentional, to minimize how long plaintext exists anywhere and to
  keep the vault-resolution point single and explicit. The consequence: a
  sensitive value already on the page before our own code types it (browser
  autofill, a resumed session, a site-prefilled field) is not covered by
  native `sensitive_data` filtering on the step it first appears, since
  nothing has registered it yet. `redact_text` at evidence-write time still
  catches it before anything reaches disk; the residual exposure is limited
  to that one LLM API call in transit for that one step. This is not closed
  by eagerly pre-resolving the whole vault at run start — that would defeat
  the resolve-at-fill-time design for a narrow, low-probability edge case
  (this executor never auto-fills from a prior session, and always fills
  fields itself).
- Gate detection currently requires consent prose and a blocking control to
  be present in the same active region, but does not require them to be in
  the same sub-container. On sonnet.ca's quote flow, unrelated partner
  promotional fine print in the page footer co-occurs with the form's own
  required control, producing a consent_or_terms_required status whose
  reason string cites text that is not the actual gate. The terminal status
  and evidence artifact are correct for the page reached; the reason string
  is imprecise. Tightening this requires matching prose and control within
  the same DOM subtree.
