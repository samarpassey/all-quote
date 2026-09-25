# All-Quote

A personal tool that takes one Ontario driver's details, tries to get a car insurance quote from
every company that sells in the province, and records what happened at each one with proof.

**It produces no priced quote, and that is the result.** The profile it was built for holds a G1
learner's licence, and a G1 holder cannot be the principal driver on a standard Ontario
private-passenger policy. Running live, after the agent filled in vehicle and driver details and
selected licence class G1 with zero validation errors, CAA Insurance's own server declined to
quote: *"we are unable to provide you with a quote at this time... find a local licensed CAA Agent
or Broker."* CAA gave no reason. G1 is the one atypical fact in an otherwise unremarkable profile,
so it is the strongest available explanation, but it is an inference and no market stated it
outright. The full evidence trail is in [`docs/RUN_REPORT.md`](docs/RUN_REPORT.md).

This is a personal-use prototype built for the author's own driver profile, not a service. It is
not for resale, not multi-tenant, and every run acts only on the profile held in this project's own
encrypted local vault.

## How it works

- **A browser agent drives each quote form.** `browser-use` on Playwright Chromium, with
  `claude-sonnet-4-6` reading the page and deciding the next action. One attempt plus one bounded
  retry on a transient error, and no retry at all on a CAPTCHA, a block or a rejection.
- **A registry of the market, not a list of favourites.** 111 seeded Ontario rows in SQLite collapse
  to 79 distinct rate sources, keyed by legal underwriter, so the same insurer reached through four
  brands counts once. Every one of the 79 ends in a terminal status: a quote, a referral, a decline
  or a block, never a silent gap.
- **Every outcome carries evidence.** Each attempt writes a redacted screenshot or document plus a
  JSON sidecar holding the timestamp, the source URL or phone number, a sha256 of the artifact, and
  whether the outcome was `observed` by contacting the market or `derived` from registry metadata.
  The driver profile itself sits in a Fernet-encrypted vault.

<!-- TODO: GIF here - the run console filling in as routes land, then a Results row expanded. -->
<!-- TODO: screenshot here - one evidence record: redacted screenshot plus its JSON sidecar. -->

## Run it

Needs Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and an Anthropic API key. From a
clean clone:

```bash
cp .env.example .env                    # set ANTHROPIC_API_KEY and VAULT_KEY
make setup                              # uv sync, then playwright install chromium
uv run python -m allquote.registry load # seeds the 111-row registry, 79 distinct sources
make app                                # the console at http://localhost:8000
```

`registry load` is idempotent and is what turns an empty database into the 79-source universe the
app shows. `data/seed_registry.json` is the only thing under `data/` in git; the database, runs and
evidence are local and gitignored.

`make test` runs all 269 tests. The browser-driven ones in `tests/test_executor.py` launch a real
local Chrome against fixture pages served from 127.0.0.1, and never reach an insurer: every
`agent_runner` is a scripted fake, so no model is called either.

Nothing here contacts a real insurer until you start a run from the console or pass `--live` to a
single route. Read [`docs/GUARDRAILS.md`](docs/GUARDRAILS.md) before the first live run.

## Every way to run it

**The console: `make app`.** Serves the whole app at **http://localhost:8000**
and opens it in your browser. The intended path:

`Intake` (fill in / confirm the driver profile) → **Find quotes** (starts a
live batch run against the full registry and jumps to the run console) →
`Run console` (watch routes land; a full batch covers the whole registry and
can run long; it's meant to be watched, not waited on) → `Results` (one row
per distinct rate source, sortable/filterable, click a row for its evidence).

**One route, live, with the browser window visible.** To watch a single
market instead of a full batch:

```bash
HEADLESS=0 uv run python -m allquote.executor run --market-id <registry_id> --live
```

`<registry_id>` is a value from `data/seed_registry.json` (or
`exports/registry.csv` after the export step below), for example
`route-caa-insurance`. Drop `HEADLESS=0` to run headless. This makes exactly
one attempt plus one bounded retry on a transient error only. It never
retries a CAPTCHA, a block, or a rejection (see `docs/GUARDRAILS.md`).

**Registry export.**

```bash
make export-registry   # writes exports/registry.csv and exports/registry.json
```

**Metrics, from the command line.**

```bash
uv run python -m allquote.report          # human-readable
uv run python -m allquote.report --json   # same, as JSON
```

Prints the five docs/SCHEMAS.md metrics (market completion, comparable quote
yield, evidence rate, duplicate suppression, freshness) plus every run-level
note attached to the runs it merged, the same computation the results page
renders.

**Where evidence lands.** Every attempted route writes to
`data/evidence/<run_id>/...`, a redacted screenshot or document per attempt,
each paired with a `*.evidence.json` sidecar record (timestamp, source URL or
phone, sha256 hash of the artifact, `redacted: true`, and `provenance`:
`observed` for an outcome from actually contacting a market, `derived` for
one concluded from registry metadata with no contact made). The results page
renders this inline. Expand any row for its evidence, including the
screenshot, so reading it there is usually easier than the raw files.

## What to look at

- **`docs/RUN_REPORT.md`, start here.** The full run: the G1 headline
  finding, the five metrics with denominators, every barrier class the run
  hit, and where each of the 79 distinct sources landed.
- **`docs/KNOWN_LIMITATIONS.md`.** Every dependency this system has on a
  human/licensed intermediary/membership it doesn't have, and every defect
  found during the build, fixed or not, disclosed either way.
- **`docs/GUARDRAILS.md`.** The hard safety rules (bounded attempts, no
  CAPTCHA-solving, no payment, human checkpoints as terminal statuses, not
  exceptions) and the architecture/safety note for the submission.
- **`exports/comparison_*.json`.** A committed `ComparisonReport`: the
  normalizer's coverage-then-price comparison output, coverage deltas listed
  before any price view, per docs/SCHEMAS.md §7's ordering requirement.
