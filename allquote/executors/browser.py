"""browser-use Agent wrapper. See PLAN.md Task 5.

Will take a MarketRecord + IntakeProfile, navigate quote_url, vault-inject
sensitive fields at fill-time, screenshot via allquote.evidence.save_evidence,
raise HumanCheckpointRequired at consent/identity/declaration steps, and return
a QuoteResult under the 1-attempt-plus-1-retry bounded-attempt policy.
"""
