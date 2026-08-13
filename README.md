# All-Quote — Ontario Auto Insurance Quote Agent

## 1. What this is

All-Quote is a personal-use agent that takes one Ontario driver profile —
captured once, encrypted at rest — and attempts a quote from every reachable
Ontario private-passenger auto insurance rate source, producing an
evidence-backed terminal status (a quote, a referral, a decline, a block —
never a silent gap) for each one. **This is a personal-use prototype built
for the author's own driver profile, not a service** — it is not for
resale, not multi-tenant, and every run acts only on the profile stored
locally in this project's own encrypted vault.

**It produces no priced quote.** The author's profile holds a G1
(learner's) Ontario licence, and G1 holders cannot be the principal driver
on a standard Ontario private-passenger auto policy — the strongest
available explanation for what follows, but it is an inference, not
something any market has stated outright. Live, after the agent filled in
vehicle details, driver details, and selected licence class G1 with zero
validation errors, CAA Insurance's own server declined to quote: *"we are
unable to provide you with a quote at this time... find a local licensed
CAA Agent or Broker."* CAA did not give a reason — the rest of the profile
was unremarkable, G1 is the one atypical fact in it, and the decline itself
stayed unexplained. See `docs/RUN_REPORT.md` for the full evidence trail.

## 2. Setup

Requirements: **Python 3.12+**, **[uv](https://docs.astral.sh/uv/)**, and an
**Anthropic API key**.

From the project root:

```bash
cp .env.example .env
# edit .env: set ANTHROPIC_API_KEY to a real key, and VAULT_KEY to any long
# random passphrase (this encrypts the profile vault at rest — see
# docs/GUARDRAILS.md)

make setup                              # uv sync + playwright install chromium
uv run python -m allquote.registry load # seeds the 111-row Ontario market registry
```

The registry seed (`data/seed_registry.json`) is the only thing under `data/`
that's checked into git — `data/allquote.db`, `data/runs/`, and
`data/evidence/` are local/gitignored. `registry load` is idempotent (safe to
re-run; it only inserts rows that aren't already present) and is what turns
an empty database into the 79-distinct-source universe the app shows.

## 3. Running it

**Console — `make app`.** Serves the whole app at **http://localhost:8000**
and opens it in your browser. The intended path:

`Intake` (fill in / confirm the driver profile) → **Find quotes** (starts a
live batch run against the full registry and jumps to the run console) →
`Run console` (watch routes land — a full batch covers the whole registry and
can run long; it's meant to be watched, not waited on) → `Results` (one row
per distinct rate source, sortable/filterable, click a row for its evidence).

**One route, live, with the browser window visible.** To watch a single
market instead of a full batch:

```bash
HEADLESS=0 uv run python -m allquote.executor run --market-id <registry_id> --live
```

`<registry_id>` is a value from `data/seed_registry.json` (or
`exports/registry.csv` after the export step below) — e.g.
`route-caa-insurance`. Drop `HEADLESS=0` to run headless. This makes exactly
one attempt plus one bounded retry on a transient error only — it never
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
note attached to the runs it merged — the same computation the results page
renders.

**Where evidence lands.** Every attempted route writes to
`data/evidence/<run_id>/...` — a redacted screenshot or document per attempt,
each paired with a `*.evidence.json` sidecar record (timestamp, source URL or
phone, sha256 hash of the artifact, `redacted: true`, and `provenance`:
`observed` for an outcome from actually contacting a market, `derived` for
one concluded from registry metadata with no contact made). The results page
renders this inline — expand any row for its evidence, including the
screenshot — so reading it there is usually easier than the raw files.

## 4. What to look at

- **`docs/RUN_REPORT.md` — start here.** The full run: the G1 headline
  finding, the five metrics with denominators, every barrier class the run
  hit, and where each of the 79 distinct sources landed.
- **`docs/KNOWN_LIMITATIONS.md`** — every dependency this system has on a
  human/licensed intermediary/membership it doesn't have, and every defect
  found during the build, fixed or not, disclosed either way.
- **`docs/GUARDRAILS.md`** — the hard safety rules (bounded attempts, no
  CAPTCHA-solving, no payment, human checkpoints as terminal statuses, not
  exceptions) and the architecture/safety note for the submission.
- **`exports/comparison_*.json`** — a committed `ComparisonReport`: the
  normalizer's coverage-then-price comparison output, coverage deltas listed
  before any price view, per docs/SCHEMAS.md §7's ordering requirement.
