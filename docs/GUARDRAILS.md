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

## Human checkpoints (executor raises HumanCheckpointRequired)

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
