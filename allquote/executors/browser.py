"""browser-use Agent wrapper. See PLAN.md Task 5.

Superseded by allquote/executor.py — that module holds the actual
implementation (run_route(), gate-driven status mapping, bounded-attempt
retry). This stub predates that design: executors never raise for a market
outcome; a human checkpoint is a terminal status (manual_handoff,
callback_required) with evidence, returned like any other QuoteResult, so a
batch run continues past one blocked market. See CLAUDE.md's "Non-negotiable
safety rules" and docs/ARCHITECTURE.md rule 3.
"""
