# All-Quote — Ontario Auto Insurance Quote Agent (Personal Hackathon Project)

Personal-use agent that takes MY OWN Ontario driver profile once, then attempts a
comparable quote from every reachable Ontario auto-insurance rate source, producing
either a quote or an evidence-backed terminal status per market. Built for the
Ontario All-Quote Agent Challenge. Judged on evidence, dedup, honesty, and safety —
NOT on how many quotes or how low the rate.

## Stack
- Python 3.12, single package `allquote/`, uv for env + deps
- browser-use (agentic browser traversal) on local Chromium via Playwright
- LLM: Anthropic API. Two tiers via env: `MODEL_CHEAP` (haiku), `MODEL_SMART` (sonnet)
- SQLite (`data/allquote.db`) for registry + results + evidence index
- Streamlit dashboard (`allquote/dashboard.py`)
- Vapi + Twilio for voice (thin client in `allquote/voice.py`)
- cryptography (Fernet) vault in `allquote/vault.py`

## Commands
- `make setup` — install deps + playwright chromium
- `make run ROUTE=<registry_id>` — run one route end to end
- `make dashboard` — launch Streamlit
- `make export` — write registry CSV/JSON + redacted run report to `exports/`
- `make test` — pytest (unit only; NEVER tests that hit real insurer sites)

## Architecture
@docs/ARCHITECTURE.md — read before touching planner, executors, or evidence flow.
@docs/SCHEMAS.md — single source of truth for all field names and enums.
@docs/GUARDRAILS.md — hackathon compliance rules; read before writing executor code.
@docs/DESIGN.md — canonical visual system. Any UI work reads it first. Never
introduce a colour, typeface, radius or shadow not listed there.

## Non-negotiable safety rules (hackathon disqualifiers — enforce in code AND review)
- NEVER write licence numbers, DOB, VIN, full address, or phone into: logs, prompts,
  LLM messages, test fixtures, comments, screenshots, git-tracked files, or error
  messages. Secrets exist ONLY in the vault and are injected by `vault.inject()` at
  the moment a form field is filled.
- Every screenshot passes through `redact.redact_image()` BEFORE first write to disk.
  There is no code path that saves a raw screenshot.
- Every executor result row MUST use a status from `Status` enum in
  `allquote/schemas.py` (13 values). Never invent, alias, or free-text a status.
- Bounded attempts: 1 attempt + 1 retry on transient technical error ONLY. Never
  retry a CAPTCHA, rejection, or terms block — record status `blocked` and stop.
- NEVER write CAPTCHA-solving, bot-detection-evasion, user-agent-spoofing, or
  auth-bypass code. Not even stubs, not even behind flags.
- Executors never raise for market outcomes. A human checkpoint is a terminal status (manual_handoff, callback_required) with evidence, not an exception — this lets a batch run continue past one blocked market. Checkpoints are enforced by deterministic gate detection in gates.py, which halts the run before any consent, identity, declaration or payment step.
- No payment fields are ever filled. No policy is ever bound.
- Voice: first sentence of every call discloses automation. No recording without
  affirmative consent. One call + one retry only if line fails before connect.

## Code conventions
- Type hints everywhere; pydantic models for all schemas (defined in schemas.py only)
- Small modules, one responsibility each; no module over ~300 lines
- Errors are data: executors never raise for market outcomes — they return a result
  row with the correct status. Raise only for programmer errors and checkpoints.
- Every result write includes: timestamp (ISO 8601, UTC), source_url or phone route,
  evidence_artifact path, distinct_rate_source_id.
- Config via .env (python-dotenv). `.env` is git-ignored; keep `.env.example` current.
- No new dependencies without noting why in the PR/commit message.

## Workflow
- Work task-by-task from PLAN.md. One task per session. Plan first, then code.
- After each task: run it, then self-review the diff against the task's acceptance
  criteria and the safety rules above before declaring done.
- Never modify schemas.py casually — it mirrors docs/SCHEMAS.md and the hackathon
  brief. If a change is needed, update both and say so explicitly.
