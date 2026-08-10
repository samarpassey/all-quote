"""Coverage/quality metrics over run results. Computed only; never hand-edited.

Definitions follow docs/SCHEMAS.md's "Metrics" section. `market_completion`,
`comparable_quote_yield`, and `freshness` require an explicit registry snapshot
to compute a denominator ("verified applicable sources") — without one they
return None rather than a number derived from the results list alone, which
would converge to ~100% by construction and overstate coverage. The same
denominator can legitimately be zero (nothing in the registry has left
`unresolved` yet); 0/0 has no meaningful ratio, so that also returns None
rather than a misleading 0.0.
"""

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


def evidence_rate(results: list[QuoteResult]) -> float:
    if not results:
        return 0.0
    numerator = sum(
        1
        for r in results
        if r.evidence.evidence_artifact.strip()
        and r.evidence.evidence_hash.strip()
        and r.evidence.source_url_or_phone.strip()
        and r.evidence.timestamp is not None
    )
    return numerator / len(results)


def duplicate_suppression(results: list[QuoteResult]) -> int:
    return sum(1 for r in results if r.outcome.status == Status.DUPLICATE_RATE_SOURCE)


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
