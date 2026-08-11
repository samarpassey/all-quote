"""Coverage/quality metrics over run results. Computed only; never hand-edited.

Definitions follow docs/SCHEMAS.md's "Metrics" section. `market_completion`,
`comparable_quote_yield`, and `freshness` require an explicit registry snapshot
to compute a denominator ("verified applicable sources") — without one they
return None rather than a number derived from the results list alone, which
would converge to ~100% by construction and overstate coverage. The same
denominator can legitimately be zero (nothing in the registry has left
`unresolved` yet); 0/0 has no meaningful ratio, so that also returns None
rather than a misleading 0.0. `evidence_rate` and `duplicate_suppression`
follow the identical zero-denominator-is-None rule (see their docstrings).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from allquote.schemas import MarketRecord, QuoteResult, Status

HACKATHON_WINDOW: tuple[datetime, datetime] = (
    datetime(2026, 8, 9, 0, 0, tzinfo=timezone.utc),
    datetime(2026, 8, 13, 4, 0, tzinfo=timezone.utc),
)


def _verified_applicable(registry: list[MarketRecord]) -> list[MarketRecord]:
    return [r for r in registry if r.status != Status.UNRESOLVED]


def market_completion(
    results: list[QuoteResult], registry: list[MarketRecord] | None = None
) -> float | None:
    if registry is None:
        return None
    denominator = len(_verified_applicable(registry))
    if denominator == 0:
        return None
    numerator = sum(
        1
        for r in results
        if r.outcome.status != Status.UNRESOLVED and r.evidence.evidence_artifact.strip()
    )
    return numerator / denominator


def comparable_quote_yield(
    results: list[QuoteResult], registry: list[MarketRecord] | None = None
) -> float | None:
    if registry is None:
        return None
    denominator = len(_verified_applicable(registry))
    if denominator == 0:
        return None
    numerator = sum(1 for r in results if r.outcome.status == Status.QUOTED_COMPARABLE)
    return numerator / denominator


@dataclass(frozen=True)
class EvidenceRate:
    """docs/SCHEMAS.md: "outcomes with a valid source, timestamp AND redacted
    artifact ÷ all outcomes." "All outcomes" is a three-way conjunction check
    against QuoteResult.evidence, which every QuoteResult satisfies by
    construction (the schema-level validator on QuoteResult already refuses
    to build a row with an empty evidence_artifact) — so this is really
    checking for a malformed/bypassed row, not a normal gap.

    The one real ambiguity BRIEF.md doesn't settle: derived-lane outcomes
    (provenance="derived" — no market was actually contacted, the status is
    resolved from our own registry metadata) DO carry a real artifact: their
    QuoteResult still points at a redacted, hashed document (the cited-fields
    reasoning JSON), written through the same evidence.py path as an observed
    screenshot. Decision: a derived artifact counts as a "redacted artifact"
    for this metric — it is genuinely redacted and hashed, just not evidence
    of contact. Rather than resolve the resulting ambiguity ("all outcomes"
    could mean literally every QuoteResult, or only ones where we actually
    reached a market) silently, this reports BOTH: `all_outcomes` over every
    QuoteResult passed in, and `observed_only` over just the subset the
    caller identifies as provenance="observed" (report.py does this split
    using each result's run-store `origin` label). Zero-denominator returns
    None on that half, same rule as every other metric here.
    """

    all_outcomes: float | None
    observed_only: float | None
    all_count: int
    observed_count: int


def _evidence_ratio(results: list[QuoteResult]) -> float | None:
    if not results:
        return None
    numerator = sum(
        1
        for r in results
        if r.evidence.evidence_artifact.strip()
        and r.evidence.evidence_hash.strip()
        and r.evidence.source_url_or_phone.strip()
        and r.evidence.timestamp is not None
    )
    return numerator / len(results)


def evidence_rate(
    all_results: list[QuoteResult], observed_results: list[QuoteResult]
) -> EvidenceRate:
    """`observed_results` must be the subset of `all_results` whose evidence
    has provenance="observed" (a market was actually contacted) — the caller
    (report.py) determines this from run-store origin, since QuoteResult
    itself carries no provenance field."""
    return EvidenceRate(
        all_outcomes=_evidence_ratio(all_results),
        observed_only=_evidence_ratio(observed_results),
        all_count=len(all_results),
        observed_count=len(observed_results),
    )


@dataclass(frozen=True)
class DuplicateSuppression:
    """docs/SCHEMAS.md: "brands or routes mapped to an existing
    distinct_rate_source_id rather than counted twice." Two different
    mechanisms currently produce this count, and reporting only one number
    would let a reader mistake one for the other:

    - `registry_seeded`: rows collapsed at registry-seed time
      (registry.assign_distinct_rate_source_ids, keyed on legal_underwriter
      alone — see docs/ARCHITECTURE.md's dedupe model) into a
      distinct_rate_source_id another row already claims. This is real
      suppression, computed from the registry alone, with no QuoteResult
      involved. None if no registry snapshot is supplied.
    - `runtime_resolved`: QuoteResults whose outcome.status is literally
      Status.DUPLICATE_RATE_SOURCE. PLAN.md Task 8b (the resolver that
      assigns this against real QuoteResults, keyed on
      (legal_underwriter, product_scope) per the ARCHITECTURE.md dedupe
      model) is explicitly deferred, so this is always 0 today — a true,
      not-yet-populated count, not a bug.
    """

    registry_seeded: int | None
    registry_seeded_basis: str | None
    runtime_resolved: int


def duplicate_suppression(
    results: list[QuoteResult], registry: list[MarketRecord] | None = None
) -> DuplicateSuppression:
    runtime_resolved = sum(1 for r in results if r.outcome.status == Status.DUPLICATE_RATE_SOURCE)
    if registry is None:
        return DuplicateSuppression(
            registry_seeded=None, registry_seeded_basis=None, runtime_resolved=runtime_resolved
        )
    total_rows = len(registry)
    distinct_sources = len({r.distinct_rate_source_id for r in registry if r.distinct_rate_source_id})
    registry_seeded = total_rows - distinct_sources
    basis = f"{total_rows} registry rows -> {distinct_sources} distinct sources"
    return DuplicateSuppression(
        registry_seeded=registry_seeded, registry_seeded_basis=basis, runtime_resolved=runtime_resolved
    )


def freshness(
    results: list[QuoteResult],
    registry: list[MarketRecord] | None = None,
    window: tuple[datetime, datetime] = HACKATHON_WINDOW,
) -> float | None:
    if registry is None:
        return None
    applicable = _verified_applicable(registry)
    denominator = len(applicable)
    if denominator == 0:
        return None
    start, end = window
    numerator = sum(
        1 for r in applicable if r.last_verified_at is not None and start <= r.last_verified_at <= end
    )
    return numerator / denominator
