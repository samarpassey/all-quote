from datetime import datetime, timezone

from allquote.metrics import (
    HACKATHON_WINDOW,
    comparable_quote_yield,
    duplicate_suppression,
    evidence_rate,
    freshness,
    market_completion,
)
from allquote.schemas import EvidenceInfo, QuoteOutcome, QuoteResult, Status
from tests.fixtures import build_market_record, build_quote_result


def make_result(status: Status) -> QuoteResult:
    is_exact_quote = status in (Status.QUOTED_COMPARABLE, Status.QUOTED_NON_COMPARABLE)
    return build_quote_result(
        outcome=QuoteOutcome(
            status=status, is_exact_quote=is_exact_quote, failure_reason=None, next_action=None
        )
    )


SIX_RESULTS = [
    make_result(Status.QUOTED_COMPARABLE),
    make_result(Status.QUOTED_NON_COMPARABLE),
    make_result(Status.DUPLICATE_RATE_SOURCE),
    make_result(Status.BLOCKED),
    make_result(Status.UNRESOLVED),
    make_result(Status.INELIGIBLE),
]


def test_evidence_rate_all_valid_evidence():
    assert evidence_rate(SIX_RESULTS) == 1.0


def test_evidence_rate_empty_list_is_zero():
    assert evidence_rate([]) == 0.0


def test_evidence_rate_catches_malformed_row_bypassing_validation():
    good = make_result(Status.QUOTED_COMPARABLE)
    malformed = QuoteResult.model_construct(
        source=good.source,
        outcome=good.outcome,
        coverage=good.coverage,
        discounts=good.discounts,
        validity=good.validity,
        evidence=EvidenceInfo.model_construct(
            timestamp=None, source_url_or_phone="", evidence_artifact="", evidence_hash=""
        ),
        confidence=good.confidence,
        privacy=good.privacy,
        price=None,
    )
    assert evidence_rate([good, malformed]) == 0.5


def test_duplicate_suppression_counts_duplicate_rows():
    assert duplicate_suppression(SIX_RESULTS) == 1


def test_market_completion_comparable_yield_freshness_none_without_registry():
    assert market_completion(SIX_RESULTS, registry=None) is None
    assert comparable_quote_yield(SIX_RESULTS, registry=None) is None
    assert freshness(SIX_RESULTS, registry=None) is None


def test_market_completion_uses_registry_denominator_not_results_length():
    # 60-row registry: 57 rows already resolved/curated (non-unresolved), 3 still
    # unresolved. Only 3 QuoteResults exist so far. A results-only denominator
    # would read as ~1.0; the registry-derived denominator should not.
    registry = [
        build_market_record(registry_id=f"resolved-{i}", status=Status.INELIGIBLE)
        for i in range(57)
    ] + [
        build_market_record(registry_id=f"unresolved-{i}", status=Status.UNRESOLVED)
        for i in range(3)
    ]
    results = [
        make_result(Status.QUOTED_COMPARABLE),
        make_result(Status.QUOTED_NON_COMPARABLE),
        make_result(Status.BLOCKED),
    ]

    completion = market_completion(results, registry=registry)
    assert completion == 3 / 57
    assert completion < 0.06

    yield_ = comparable_quote_yield(results, registry=registry)
    assert yield_ == 1 / 57


def test_freshness_ratio_against_registry_window():
    in_window = datetime(2026, 8, 10, tzinfo=timezone.utc)
    out_of_window = datetime(2025, 1, 1, tzinfo=timezone.utc)
    registry = [
        build_market_record(registry_id="a", status=Status.BLOCKED, last_verified_at=in_window),
        build_market_record(registry_id="b", status=Status.BLOCKED, last_verified_at=in_window),
        build_market_record(
            registry_id="c", status=Status.INELIGIBLE, last_verified_at=out_of_window
        ),
        build_market_record(registry_id="d", status=Status.UNRESOLVED, last_verified_at=None),
    ]

    result = freshness([], registry=registry, window=HACKATHON_WINDOW)
    assert result == 2 / 3
