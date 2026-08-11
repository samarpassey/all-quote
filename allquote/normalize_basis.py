"""RequestedBasis derivation + observations -> CoverageLines. See PLAN.md
Task 8 / the approved plan.

Two pure building blocks used by allquote.normalize:
  - derive_requested_basis(): the one reference basis for a run, from
    IntakeProfile.coverage_benchmark.
  - map_observations_to_lines(): verbatim label/value pairs -> interpreted
    CoverageLines, via the label table in normalize_labels.py.
Neither computes comparability, materiality, or status — see
allquote.normalize_compare for that.
"""

from datetime import datetime

from allquote.normalize_labels import AB_OPT_KEY_MAP, BASIS_DEFAULTS, INFERENCE_RULES, match_dimensions, parse_currency_amount
from allquote.schemas import (
    REQUESTABLE_DIMENSIONS,
    CoverageBenchmark,
    CoverageDimension,
    CoverageLine,
    CoverageObservation,
    DisclosureState,
    Provenance,
    RequestedBasis,
)

# Dimensions whose numeric value is a deductible, not a coverage limit.
_DEDUCTIBLE_DIMENSIONS: frozenset[CoverageDimension] = frozenset(
    {
        CoverageDimension.OWN_DAMAGE_SPECIFIED_PERILS,
        CoverageDimension.OWN_DAMAGE_COMPREHENSIVE,
        CoverageDimension.OWN_DAMAGE_COLLISION,
        CoverageDimension.OWN_DAMAGE_ALL_PERILS,
    }
)

_ENDORSEMENT_KEY_BY_DIMENSION: dict[CoverageDimension, str] = {
    CoverageDimension.OPCF_20_TRANSPORTATION_REPLACEMENT: "opcf_20",
    CoverageDimension.OPCF_27_NON_OWNED_AUTOMOBILES: "opcf_27",
    CoverageDimension.OPCF_43_REMOVING_DEPRECIATION_DEDUCTION: "opcf_43",
    CoverageDimension.OPCF_44R_FAMILY_PROTECTION: "opcf_44r",
}


# --- RequestedBasis ------------------------------------------------------------


def derive_requested_basis(
    benchmark: CoverageBenchmark,
    *,
    requested_basis_id: str,
    captured_at: datetime,
) -> RequestedBasis:
    """One RequestedBasis per run, from IntakeProfile.coverage_benchmark.
    Every dimension CoverageBenchmark doesn't directly cover falls back to
    BASIS_DEFAULTS (never a blanket default) — see normalize_labels.py.
    """
    lines: dict[CoverageDimension, CoverageLine] = {}

    def _line(dim: CoverageDimension, disclosure: DisclosureState, *, limit=None, deductible=None, label: str, value) -> None:
        lines[dim] = CoverageLine(
            dimension=dim,
            disclosure=disclosure,
            limit_cad=limit,
            deductible_cad=deductible,
            source_label=label,
            source_value=str(value),
            provenance="derived",
        )

    _line(
        CoverageDimension.THIRD_PARTY_LIABILITY,
        DisclosureState.INCLUDED,
        limit=benchmark.liability_limit,
        label="coverage_benchmark.liability_limit",
        value=benchmark.liability_limit,
    )
    _line(
        CoverageDimension.DCPD,
        DisclosureState.INCLUDED if benchmark.dcpd_included else DisclosureState.EXCLUDED,
        label="coverage_benchmark.dcpd_included",
        value=benchmark.dcpd_included,
    )
    _line(
        CoverageDimension.OWN_DAMAGE_COLLISION,
        DisclosureState.INCLUDED,
        deductible=benchmark.collision_deductible,
        label="coverage_benchmark.collision_deductible",
        value=benchmark.collision_deductible,
    )
    _line(
        CoverageDimension.OWN_DAMAGE_COMPREHENSIVE,
        DisclosureState.INCLUDED,
        deductible=benchmark.comprehensive_deductible,
        label="coverage_benchmark.comprehensive_deductible",
        value=benchmark.comprehensive_deductible,
    )
    for dim, key in _ENDORSEMENT_KEY_BY_DIMENSION.items():
        selected = key in benchmark.endorsements
        _line(
            dim,
            DisclosureState.INCLUDED if selected else DisclosureState.EXCLUDED,
            label="coverage_benchmark.endorsements",
            value=key if selected else "not selected",
        )
    for short_key, dim in AB_OPT_KEY_MAP.items():
        raw = benchmark.optional_ab_selections.get(short_key)
        disclosure = DisclosureState(raw) if raw is not None else DisclosureState.EXCLUDED
        _line(
            dim,
            disclosure,
            label=f"coverage_benchmark.optional_ab_selections[{short_key}]",
            value=raw if raw is not None else "not selected",
        )
    for dim, default_disclosure in BASIS_DEFAULTS.items():
        _line(
            dim,
            default_disclosure,
            label=f"normalize_labels.BASIS_DEFAULTS[{dim.value}]",
            value=default_disclosure.value,
        )

    return RequestedBasis(
        requested_basis_id=requested_basis_id,
        requested_effective_date=benchmark.effective_date,
        term_months=12,
        lines=list(lines.values()),
        captured_at=captured_at,
    )


# --- observations -> coverage lines --------------------------------------------


def _infer_disclosure(value: str | None) -> DisclosureState:
    if value is None:
        return DisclosureState.INCLUDED
    v = value.strip().lower()
    if v in {"not offered", "not available", "unavailable", "n/a", "not offered by this insurer"}:
        return DisclosureState.UNAVAILABLE
    if v in {"excluded", "not included", "declined", "no"}:
        return DisclosureState.EXCLUDED
    if v in {"included", "yes", "selected"}:
        return DisclosureState.INCLUDED
    return DisclosureState.INCLUDED  # a parseable/free-text value implies the line is present


def unknown_line(dim: CoverageDimension, *, provenance: Provenance = "observed") -> CoverageLine:
    # provenance is forced to a binary choice by schema (no third value).
    # Caller decides which one applies: "observed" when the outcome actually
    # reached the market's coverage surface (map_observations_to_lines was
    # called against a real, if incomplete, observation set — this dimension
    # just never came up — "observed absence"); "derived" when it didn't (a
    # terminal outcome — manual_handoff, blocked, callback_required — never
    # captured any coverage observations at all, so asserting "observed" here
    # would claim contact with the market's coverage page that never
    # happened, using the exact vocabulary EvidenceRecord uses to mean
    # contact was made).
    return CoverageLine(
        dimension=dim,
        disclosure=DisclosureState.UNKNOWN,
        provenance=provenance,
    )


def map_observations_to_lines(
    observations: list[CoverageObservation],
) -> tuple[list[CoverageLine], list[str]]:
    """Pure: verbatim label/value pairs -> interpreted CoverageLines. Applies
    the label table, then the two permitted inferences, then fills every
    unmentioned dimension with disclosure=unknown. Never substitutes a
    default limit or deductible."""
    lines_by_dim: dict[CoverageDimension, CoverageLine] = {}
    other_lines: list[CoverageLine] = []
    warnings: list[str] = []

    for obs in observations:
        dims = match_dimensions(obs.source_label)
        source_value = obs.source_value if obs.source_value is not None else obs.source_label
        if not dims:
            other_lines.append(
                CoverageLine(
                    dimension=CoverageDimension.OTHER_ENDORSEMENT,
                    disclosure=_infer_disclosure(obs.source_value),
                    source_label=obs.source_label,
                    source_value=source_value,
                    provenance="observed",
                )
            )
            warnings.append(f"unmapped label {obs.source_label!r} recorded as other_endorsement")
            continue
        disclosure = _infer_disclosure(obs.source_value)
        amount = parse_currency_amount(obs.source_value)
        if (
            obs.source_value
            and amount is None
            and disclosure == DisclosureState.INCLUDED
            and obs.source_value.strip().lower() not in {"included", "yes", "selected"}
        ):
            warnings.append(f"could not parse a numeric amount from {obs.source_value!r} on {obs.source_label!r}")
        for dim in dims:
            if dim in lines_by_dim:
                warnings.append(f"duplicate observation for {dim.value}; keeping the later one")
            lines_by_dim[dim] = CoverageLine(
                dimension=dim,
                disclosure=disclosure,
                limit_cad=amount if dim not in _DEDUCTIBLE_DIMENSIONS else None,
                deductible_cad=amount if dim in _DEDUCTIBLE_DIMENSIONS else None,
                source_label=obs.source_label,
                source_value=source_value,
                provenance="observed",
            )

    for (trig_dim, trig_disclosure), inferred, warning in INFERENCE_RULES:
        trig_line = lines_by_dim.get(trig_dim)
        if trig_line is None or trig_line.disclosure != trig_disclosure:
            continue
        for inf_dim, inf_disclosure in inferred:
            if inf_dim in lines_by_dim:
                continue  # an explicit market disclosure always outranks an inference
            lines_by_dim[inf_dim] = CoverageLine(
                dimension=inf_dim,
                disclosure=inf_disclosure,
                source_label=trig_line.source_label,
                source_value=trig_line.source_value,
                provenance="derived",
            )
            warnings.append(warning)

    for dim in REQUESTABLE_DIMENSIONS:
        if dim not in lines_by_dim:
            lines_by_dim[dim] = unknown_line(dim)

    return list(lines_by_dim.values()) + other_lines, warnings
