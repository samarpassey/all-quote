"""Materiality, comparability, bounded-authority status derivation, and the
pairwise ComparisonReport. See PLAN.md Task 8 / the approved plan.

This is the ONLY module allowed to derive Status.{quoted_comparable,
quoted_non_comparable, estimate_only} from coverage (`derive_priced_status`).
It may only ever write one of those three, and only when the caller's current
status is already one of them — `derive_priced_status` raises otherwise,
never a silent pass. allquote.normalize (the orchestrator) is responsible for
never calling it on a terminal-status quote in the first place.
"""

from allquote.schemas import (
    REQUESTABLE_DIMENSIONS,
    Comparability,
    ComparisonReport,
    CoverageDelta,
    CoverageDimension,
    CoverageLine,
    DisclosureState,
    NormalizedPremium,
    NormalizedQuote,
    PriceView,
    RequestedBasis,
    Status,
)

PRICED_TRIAD: frozenset[Status] = frozenset(
    {Status.QUOTED_COMPARABLE, Status.QUOTED_NON_COMPARABLE, Status.ESTIMATE_ONLY}
)

# A market's rep is a licensed intermediary for these distribution channels
# (MarketRecord.distribution_type). "residual" per BRIEF.md §3: Facility
# Association "is accessed through a licensed intermediary, not a normal
# direct quote path."
LICENSED_INTERMEDIARY_CHANNELS: frozenset[str] = frozenset({"agent", "broker", "MGA_program", "residual"})

_MANDATORY_AB_LIMIT_WARNING = (
    "market disclosed a mandatory accident-benefits limit; basis carries none — cannot "
    "determine whether this is the statutory floor or an increased limit"
)

_MATERIALITY_PRECEDENCE = ["undisclosed_gap", "evidenced_gap", "material", "minor"]


# --- materiality (explicit rule set, no blanket default) ----------------------


def classify_delta(
    dimension: CoverageDimension, basis_line: CoverageLine, quote_line: CoverageLine
) -> tuple[str | None, str | None]:
    """(materiality, warning). materiality is None when the quote matches
    the basis on this dimension (no delta at all). Every other outcome is one
    of five explicitly named cases — nothing falls through to an implicit
    default."""
    if quote_line.disclosure == DisclosureState.UNAVAILABLE:
        return "evidenced_gap", None
    if quote_line.disclosure == DisclosureState.UNKNOWN:
        return "undisclosed_gap", None
    if (
        dimension == CoverageDimension.ACCIDENT_BENEFITS_MANDATORY
        and basis_line.disclosure == DisclosureState.INCLUDED
        and quote_line.disclosure == DisclosureState.INCLUDED
        and basis_line.limit_cad is None
        and quote_line.limit_cad is not None
    ):
        return "minor", _MANDATORY_AB_LIMIT_WARNING
    if basis_line.disclosure != quote_line.disclosure:
        return "material", None
    if basis_line.limit_cad != quote_line.limit_cad:
        return "material", None
    if basis_line.deductible_cad != quote_line.deductible_cad:
        return "material", None
    return None, None


# --- comparability + bounded-authority status derivation -----------------------


def assess_comparability(quote: NormalizedQuote, basis: RequestedBasis) -> tuple[Comparability, list[str]]:
    """Always against RequestedBasis, never pairwise between quotes."""
    if quote.binding_basis == "none":
        return Comparability.NOT_COMPARABLE, []
    if quote.binding_basis == "indicative_assumption":
        return Comparability.INDICATIVE_ONLY, []

    basis_lines = {line.dimension: line for line in basis.lines}
    quote_lines = {line.dimension: line for line in quote.lines if line.dimension != CoverageDimension.OTHER_ENDORSEMENT}

    any_mismatch = False
    warnings: list[str] = []
    for dim in REQUESTABLE_DIMENSIONS:
        materiality, warning = classify_delta(dim, basis_lines[dim], quote_lines[dim])
        if materiality is not None:
            any_mismatch = True
            if warning:
                warnings.append(warning)

    if quote.validity.effective_date != basis.requested_effective_date or quote.premium.term_months != basis.term_months:
        any_mismatch = True
        warnings.append("effective date or term differs from the requested basis")

    return (Comparability.DIFFERS_ON_COVERAGE if any_mismatch else Comparability.IDENTICAL_BASIS), warnings


def derive_priced_status(current: Status, comparability: Comparability) -> Status:
    """The ONLY function allowed to derive quoted_comparable/
    quoted_non_comparable/estimate_only from coverage. Raises — never a
    silent pass — if `current` isn't already in the priced triad; the
    normalizer owns only the priced triad, never a terminal status."""
    if current not in PRICED_TRIAD:
        raise ValueError(
            f"derive_priced_status called with status={current.value!r}, which is not in the "
            f"priced triad {sorted(s.value for s in PRICED_TRIAD)} — the normalizer must never "
            "write over a terminal status"
        )
    mapping = {
        Comparability.IDENTICAL_BASIS: Status.QUOTED_COMPARABLE,
        Comparability.DIFFERS_ON_COVERAGE: Status.QUOTED_NON_COMPARABLE,
        Comparability.INDICATIVE_ONLY: Status.ESTIMATE_ONLY,
        # Unreachable when current is already in PRICED_TRIAD: NOT_COMPARABLE
        # only arises from binding_basis="none", which allquote.normalize
        # only ever assigns to terminal-status quotes. Kept explicit rather
        # than omitted so a future caller gets a clear no-op instead of a
        # KeyError if that invariant is ever broken elsewhere.
        Comparability.NOT_COMPARABLE: current,
    }
    return mapping[comparability]


def derive_confidence(comparability: Comparability, distribution_type: str, final_status: Status) -> str:
    # high = exact premium + matching coverage (BRIEF.md §7).
    if comparability == Comparability.IDENTICAL_BASIS:
        return "high"
    # medium = a licensed representative's documented quote, REGARDLESS of
    # coverage match (§7) — not a restatement of comparability.
    if distribution_type in LICENSED_INTERMEDIARY_CHANNELS and final_status in (
        Status.QUOTED_COMPARABLE,
        Status.QUOTED_NON_COMPARABLE,
    ):
        return "medium"
    return "low"


# --- comparison report (reports only; never sets status) ----------------------


def _aggregate_materiality(materialities: list[str]) -> str:
    return min(materialities, key=_MATERIALITY_PRECEDENCE.index)


def _build_price_view(quotes: list[NormalizedQuote], deltas: list[CoverageDelta]) -> PriceView:
    per_quote = {q.market_id: q.premium for q in quotes}
    material = [d for d in deltas if d.materiality == "material"]
    undisclosed = [d for d in deltas if d.materiality == "undisclosed_gap"]
    annualized_meets_stated = any(
        q.premium.annualized_by_us and q.premium.annualized_from_monthly_cad is not None for q in quotes
    ) and any(not q.premium.annualized_by_us and q.premium.annual_premium_cad is not None for q in quotes)

    if material:
        dims = ", ".join(d.dimension.value for d in material)
        return PriceView(per_quote=per_quote, price_comparison_valid=False, reason=f"material coverage difference on: {dims}")
    if undisclosed:
        dims = ", ".join(d.dimension.value for d in undisclosed)
        return PriceView(
            per_quote=per_quote,
            price_comparison_valid=False,
            reason=f"basis comparison incomplete — unknown for at least one input on: {dims}",
        )
    if annualized_meets_stated:
        return PriceView(
            per_quote=per_quote,
            price_comparison_valid=False,
            reason="an annualized-by-us premium is being set beside a stated annual premium from another input",
        )
    return PriceView(
        per_quote=per_quote,
        price_comparison_valid=True,
        reason="no material coverage difference or price-timing mismatch among the compared inputs",
    )


def build_comparison_report(quotes: list[NormalizedQuote], basis: RequestedBasis) -> ComparisonReport:
    basis_lines = {line.dimension: line for line in basis.lines}
    coverage_deltas: list[CoverageDelta] = []
    undisclosed_dimensions: list[CoverageDimension] = []

    for dim in REQUESTABLE_DIMENSIONS:
        basis_line = basis_lines[dim]
        per_quote: dict[str, CoverageLine] = {}
        materialities: list[str] = []
        warnings_for_dim: list[str] = []
        for q in quotes:
            q_line = next(line for line in q.lines if line.dimension == dim)
            per_quote[q.market_id] = q_line
            materiality, warning = classify_delta(dim, basis_line, q_line)
            if materiality is not None:
                materialities.append(materiality)
            if warning:
                warnings_for_dim.append(warning)
        if not materialities:
            continue
        overall = _aggregate_materiality(materialities)
        coverage_deltas.append(
            CoverageDelta(
                dimension=dim,
                requested=basis_line,
                per_quote=per_quote,
                materiality=overall,
                warning="; ".join(dict.fromkeys(warnings_for_dim)) or None,
            )
        )
        if "undisclosed_gap" in materialities:
            undisclosed_dimensions.append(dim)

    price_view = _build_price_view(quotes, coverage_deltas)

    return ComparisonReport(
        inputs=[q.market_id for q in quotes],
        requested_basis_id=basis.requested_basis_id,
        comparability={q.market_id: q.comparability for q in quotes},
        coverage_deltas=coverage_deltas,
        undisclosed_dimensions=undisclosed_dimensions,
        price_view=price_view,
    )
