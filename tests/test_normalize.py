"""Task 8 normalizer tests: C1-C12 from the approved plan, plus the
mandatory-AB materiality test. Fixtures in this file use realistic Ontario
quoter wording written independently of normalize_labels.py's own table
entries — the table was extended to match these, not the other way around.
"""

import re
from datetime import date, datetime, timezone

import pytest

from allquote.normalize import normalize_quote
from allquote.normalize_basis import derive_requested_basis, map_observations_to_lines
from allquote.normalize_compare import assess_comparability, build_comparison_report, classify_delta, derive_priced_status
from allquote.schemas import (
    Comparability,
    CoverageDimension,
    CoverageObservation,
    DisclosureState,
    NormalizedPremium,
    Status,
)

from tests.fixtures import (
    build_coverage_benchmark,
    build_coverage_observation,
    build_normalized_quote,
    build_quote_result,
    build_requested_basis,
    build_vaulted_profile,
)

UTC = timezone.utc


def _obs(label: str, value: str | None, *, evidence_id: str = "evd-0001") -> CoverageObservation:
    return CoverageObservation(source_label=label, source_value=value, captured_at=datetime(2026, 8, 9, tzinfo=UTC), evidence_id=evidence_id)


# --- C1: realistic wording, extended combined label --------------------------


def test_c1_realistic_quoter_wording_maps_to_expected_dimensions():
    from allquote.normalize_labels import match_dimensions

    single_label_cases = {
        "Liability - Bodily Injury & Property Damage": CoverageDimension.THIRD_PARTY_LIABILITY,
        "Other Than Collision (Comprehensive)": CoverageDimension.OWN_DAMAGE_COMPREHENSIVE,
        "Direct Compensation - Property Damage": CoverageDimension.DCPD,
        "Loss of Use / Transportation Replacement": CoverageDimension.OPCF_20_TRANSPORTATION_REPLACEMENT,
        "Family Protection Coverage (OPCF 44R)": CoverageDimension.OPCF_44R_FAMILY_PROTECTION,
        "Accident Benefits - Standard": CoverageDimension.ACCIDENT_BENEFITS_MANDATORY,
        "Income Replacement Benefit - Increased": CoverageDimension.AB_OPT_INCOME_REPLACEMENT,
        "Non-Earner Benefit": CoverageDimension.AB_OPT_NON_EARNER,
        "Loss of Educational Expenses Benefit": CoverageDimension.AB_OPT_LOST_EDUCATIONAL_EXPENSES,
        "Expenses of Visitors Benefit": CoverageDimension.AB_OPT_EXPENSES_OF_VISITORS,
        "Loss of or Damage to Personal Property": CoverageDimension.AB_OPT_DAMAGE_TO_PERSONAL_ITEMS,
        "Death Benefit": CoverageDimension.AB_OPT_DEATH,
        "Funeral Expense Benefit": CoverageDimension.AB_OPT_FUNERAL,
        "Dependant Care Benefit": CoverageDimension.AB_OPT_DEPENDANT_CARE,
        "Indexation Benefit": CoverageDimension.AB_OPT_INDEXATION,
        "Supplementary Medical, Rehabilitation and Attendant Care": CoverageDimension.AB_OPT_SUPPLEMENTARY_MEDICAL_REHAB_ATTENDANT_CARE,
        "Catastrophic Impairment Benefit": CoverageDimension.AB_OPT_CATASTROPHIC_IMPAIRMENT,
    }
    for label, expected in single_label_cases.items():
        assert match_dimensions(label) == [expected], label

    # combined label: two benefits named in one line item, not merged into one
    combined = match_dimensions("Optional Caregiver, Housekeeping & Home Maintenance")
    assert set(combined) == {
        CoverageDimension.AB_OPT_CAREGIVER,
        CoverageDimension.AB_OPT_HOUSEKEEPING_HOME_MAINTENANCE,
    }


def test_c1_combined_label_produces_two_coverage_lines_not_one():
    observations = [_obs("Optional Caregiver, Housekeeping & Home Maintenance", "Included")]
    lines, warnings = map_observations_to_lines(observations)
    matched = [l for l in lines if l.dimension in (CoverageDimension.AB_OPT_CAREGIVER, CoverageDimension.AB_OPT_HOUSEKEEPING_HOME_MAINTENANCE)]
    assert len(matched) == 2
    assert all(l.disclosure == DisclosureState.INCLUDED for l in matched)
    assert all(l.dimension != CoverageDimension.OTHER_ENDORSEMENT for l in matched)


# --- C2: unmapped label -------------------------------------------------------


def test_c2_unmapped_label_falls_back_to_other_endorsement_verbatim():
    weird_label = "Complimentary Roadside Concierge Perk Bundle"
    observations = [_obs(weird_label, "Included")]
    lines, warnings = map_observations_to_lines(observations)

    other_lines = [l for l in lines if l.dimension == CoverageDimension.OTHER_ENDORSEMENT]
    assert len(other_lines) == 1
    assert other_lines[0].source_label == weird_label
    assert any("other_endorsement" in w for w in warnings)

    real_dimension_lines = [l for l in lines if l.dimension != CoverageDimension.OTHER_ENDORSEMENT]
    assert all(l.source_label != weird_label for l in real_dimension_lines)


# --- C3: omitted dimension -> unknown, no substituted default ----------------


def test_c3_omitted_collision_is_unknown_with_no_default_values():
    observations = [_obs("Liability - Bodily Injury & Property Damage", "$2,000,000")]
    lines, _ = map_observations_to_lines(observations)
    collision = next(l for l in lines if l.dimension == CoverageDimension.OWN_DAMAGE_COLLISION)
    assert collision.disclosure == DisclosureState.UNKNOWN
    assert collision.limit_cad is None
    assert collision.deductible_cad is None
    assert collision.source_label is None
    assert collision.source_value is None


# --- C4: coverage before price in field order ---------------------------------


def test_c4_coverage_deltas_serialize_before_price_view():
    basis = build_requested_basis()
    quote = build_normalized_quote()
    report = build_comparison_report([quote], basis)
    keys = list(report.model_dump().keys())
    assert keys.index("coverage_deltas") < keys.index("price_view")


# --- C5: all four disclosure states distinct ----------------------------------


def test_c5_unavailable_is_evidenced_gap_unknown_is_undisclosed_gap():
    basis = build_requested_basis()
    dim = CoverageDimension.AB_OPT_DEATH
    basis_line = next(l for l in basis.lines if l.dimension == dim)

    unavailable_line = basis_line.model_copy(
        update={"disclosure": DisclosureState.UNAVAILABLE, "limit_cad": None, "deductible_cad": None, "provenance": "observed"}
    )
    unknown_line = basis_line.model_copy(
        update={
            "disclosure": DisclosureState.UNKNOWN,
            "limit_cad": None,
            "deductible_cad": None,
            "source_label": None,
            "source_value": None,
        }
    )
    included_line = basis_line.model_copy(update={"disclosure": DisclosureState.INCLUDED})
    excluded_line = basis_line.model_copy(update={"disclosure": DisclosureState.EXCLUDED})

    materiality_unavailable, _ = classify_delta(dim, basis_line, unavailable_line)
    materiality_unknown, _ = classify_delta(dim, basis_line, unknown_line)
    materiality_included, _ = classify_delta(dim, basis_line, included_line)
    materiality_excluded, _ = classify_delta(dim, basis_line, excluded_line)

    results = {materiality_unavailable, materiality_unknown, materiality_included, materiality_excluded}
    assert len(results) == 4, "all four disclosure states must produce distinct comparison output"
    assert materiality_unavailable == "evidenced_gap"
    assert materiality_unknown == "undisclosed_gap"

    def _quote_with(dim, line):
        lines = [l.model_copy() for l in basis.lines if l.dimension != dim]
        lines.append(line)
        return build_normalized_quote(lines=lines)

    report_unavailable = build_comparison_report([_quote_with(dim, unavailable_line)], basis)
    report_unknown = build_comparison_report([_quote_with(dim, unknown_line)], basis)

    assert dim not in report_unavailable.undisclosed_dimensions
    assert dim in report_unknown.undisclosed_dimensions


# --- C6: monthly-only premium, annualized-vs-stated invalidates price --------


def test_c6_monthly_only_premium_never_yields_annual():
    with pytest.raises(Exception):
        NormalizedPremium(payment_basis="monthly", monthly_premium_cad=125.0, annual_premium_cad=1500.0, term_months=12)

    # valid monthly-only premium is fine
    premium = NormalizedPremium(payment_basis="monthly", monthly_premium_cad=125.0, term_months=12)
    assert premium.annual_premium_cad is None


def test_c6_annualized_by_us_meeting_stated_annual_invalidates_price_comparison():
    basis = build_requested_basis()
    stated_premium = NormalizedPremium(payment_basis="annual", annual_premium_cad=1500.0, term_months=12)
    annualized_premium = NormalizedPremium(
        payment_basis="monthly",
        monthly_premium_cad=140.0,
        annualized_from_monthly_cad=1680.0,
        annualized_by_us=True,
        term_months=12,
    )
    # lines matched to the basis exactly, so no coverage delta masks the
    # annualized-vs-stated price check this test targets.
    matching_lines = [l.model_copy() for l in basis.lines]
    quote_a = build_normalized_quote(market_id="market-a", premium=stated_premium, lines=matching_lines)
    quote_b = build_normalized_quote(market_id="market-b", premium=annualized_premium, lines=[l.model_copy() for l in basis.lines])

    report = build_comparison_report([quote_a, quote_b], basis)
    assert report.price_view.price_comparison_valid is False
    assert "annualized" in report.price_view.reason


# --- C7: no ranking language --------------------------------------------------

_BANNED_PATTERN = re.compile(r"best|cheapest|recommend|winner|savings", re.IGNORECASE)


def test_c7_no_ranking_language_anywhere_in_comparison_report():
    basis = build_requested_basis()
    quote = build_normalized_quote()
    report = build_comparison_report([quote], basis)

    for field_name in type(report).model_fields:
        assert not _BANNED_PATTERN.search(field_name), field_name

    dumped = report.model_dump_json()
    assert not _BANNED_PATTERN.search(dumped), dumped


# --- C9: bounded authority ----------------------------------------------------


def test_c9_terminal_status_round_trips_byte_identical_with_unknown_lines():
    basis = build_requested_basis()
    qr = build_quote_result()
    qr = qr.model_copy(update={"outcome": qr.outcome.model_copy(update={"status": Status.BLOCKED, "is_exact_quote": False})})

    updated_qr, nq = normalize_quote(
        qr,
        observations=[],
        basis=basis,
        distribution_type="direct",
        requested_basis_id=basis.requested_basis_id,
        captured_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    assert updated_qr.outcome.status == Status.BLOCKED
    assert updated_qr == qr  # byte-identical round trip
    assert nq.status == Status.BLOCKED
    assert all(l.disclosure == DisclosureState.UNKNOWN for l in nq.lines)
    # A terminal outcome never reached the market's coverage surface — these
    # lines must not claim "observed" (EvidenceRecord's vocabulary for
    # contact that was actually made).
    assert all(l.provenance == "derived" for l in nq.lines)
    assert nq.binding_basis == "none"
    assert nq.premium.annual_premium_cad is None
    assert nq.premium.monthly_premium_cad is None


def test_c9_priced_outcome_with_partial_capture_keeps_observed_provenance_on_unmentioned_dimensions():
    basis = build_requested_basis()
    qr = build_quote_result()
    qr = qr.model_copy(update={"outcome": qr.outcome.model_copy(update={"status": Status.QUOTED_COMPARABLE, "is_exact_quote": True})})

    # Only one dimension actually captured — the market's coverage surface
    # WAS reached (this is a priced outcome), it just wasn't fully captured.
    observations = [_obs("Liability - Bodily Injury & Property Damage", "$2,000,000")]

    _, nq = normalize_quote(
        qr,
        observations,
        basis,
        distribution_type="direct",
        requested_basis_id=basis.requested_basis_id,
        captured_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    unmentioned = [l for l in nq.lines if l.dimension != CoverageDimension.THIRD_PARTY_LIABILITY]
    assert unmentioned, "expected at least one unmentioned dimension in this fixture"
    assert all(l.disclosure == DisclosureState.UNKNOWN for l in unmentioned)
    assert all(l.provenance == "observed" for l in unmentioned)


def test_c9_derive_priced_status_raises_on_non_priced_current_status():
    with pytest.raises(ValueError):
        derive_priced_status(Status.BLOCKED, Comparability.IDENTICAL_BASIS)
    with pytest.raises(ValueError):
        derive_priced_status(Status.MANUAL_HANDOFF, Comparability.DIFFERS_ON_COVERAGE)
    # sanity: does NOT raise for a status already in the priced triad
    assert derive_priced_status(Status.QUOTED_COMPARABLE, Comparability.IDENTICAL_BASIS) == Status.QUOTED_COMPARABLE


# --- C10: confidence is not a restatement of comparability --------------------


def test_c10_broker_quote_with_coverage_difference_is_medium_confidence():
    basis = build_requested_basis()
    qr = build_quote_result()
    qr = qr.model_copy(update={"outcome": qr.outcome.model_copy(update={"status": Status.QUOTED_NON_COMPARABLE, "is_exact_quote": True})})

    observations = [_obs("Liability - Bodily Injury & Property Damage", "$1,000,000")]  # differs from $2M basis

    _, nq = normalize_quote(
        qr,
        observations,
        basis,
        distribution_type="broker",
        requested_basis_id=basis.requested_basis_id,
        captured_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    assert nq.comparability == Comparability.DIFFERS_ON_COVERAGE
    assert nq.confidence == "medium"
    assert nq.status == Status.QUOTED_NON_COMPARABLE


def test_c10_direct_channel_with_coverage_difference_is_low_confidence():
    basis = build_requested_basis()
    qr = build_quote_result()
    qr = qr.model_copy(update={"outcome": qr.outcome.model_copy(update={"status": Status.QUOTED_NON_COMPARABLE, "is_exact_quote": True})})
    observations = [_obs("Liability - Bodily Injury & Property Damage", "$1,000,000")]

    _, nq = normalize_quote(
        qr,
        observations,
        basis,
        distribution_type="direct",
        requested_basis_id=basis.requested_basis_id,
        captured_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    assert nq.comparability == Comparability.DIFFERS_ON_COVERAGE
    assert nq.confidence == "low"


# --- C11: OPCF 49 inference ---------------------------------------------------


def test_c11_opcf_49_infers_dcpd_excluded_derived_with_warning():
    observations = [_obs("DCPD Opt-Out Endorsement (OPCF 49)", "Included")]
    lines, warnings = map_observations_to_lines(observations)

    opcf_49_line = next(l for l in lines if l.dimension == CoverageDimension.OPCF_49_DCPD_OPT_OUT)
    dcpd_line = next(l for l in lines if l.dimension == CoverageDimension.DCPD)

    assert opcf_49_line.disclosure == DisclosureState.INCLUDED
    assert dcpd_line.disclosure == DisclosureState.EXCLUDED
    assert dcpd_line.provenance == "derived"
    assert any("opcf 49" in w.lower() or "dcpd" in w.lower() for w in warnings)


def test_c11_all_perils_infers_collision_and_comprehensive_included_derived():
    observations = [_obs("All Perils Coverage", "Included")]
    lines, warnings = map_observations_to_lines(observations)

    collision_line = next(l for l in lines if l.dimension == CoverageDimension.OWN_DAMAGE_COLLISION)
    comprehensive_line = next(l for l in lines if l.dimension == CoverageDimension.OWN_DAMAGE_COMPREHENSIVE)

    assert collision_line.disclosure == DisclosureState.INCLUDED
    assert collision_line.provenance == "derived"
    assert comprehensive_line.disclosure == DisclosureState.INCLUDED
    assert comprehensive_line.provenance == "derived"
    assert any("all perils" in w.lower() for w in warnings)


# --- C12: no plaintext sensitive value survives round-trip --------------------


def test_c12_normalized_quote_round_trip_carries_no_plaintext_sensitive_value(tmp_path):
    vault_path = tmp_path / "vault.enc"
    profile, plaintext = build_vaulted_profile(vault_path, "test-vault-key-0001")

    basis = derive_requested_basis(
        profile.coverage_benchmark, requested_basis_id="basis-vaulted", captured_at=datetime(2026, 8, 9, tzinfo=UTC)
    )
    qr = build_quote_result()
    observations = [_obs("Liability - Bodily Injury & Property Damage", "$2,000,000")]

    _, nq = normalize_quote(
        qr,
        observations,
        basis,
        distribution_type="direct",
        requested_basis_id=basis.requested_basis_id,
        captured_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    dumped = nq.model_dump_json()
    for field_name, value in plaintext.items():
        assert value not in dumped, f"plaintext {field_name!r} leaked into NormalizedQuote output"


# --- mandatory-AB minor-materiality rule (both consumers) --------------------


def test_mandatory_ab_basis_none_vs_quote_figure_is_minor_not_material():
    basis = build_requested_basis()
    dim = CoverageDimension.ACCIDENT_BENEFITS_MANDATORY
    basis_line = next(l for l in basis.lines if l.dimension == dim)
    assert basis_line.disclosure == DisclosureState.INCLUDED
    assert basis_line.limit_cad is None

    quote_line = basis_line.model_copy(update={"limit_cad": 200_000, "source_value": "200000"})

    materiality, warning = classify_delta(dim, basis_line, quote_line)
    assert materiality == "minor"
    assert warning is not None and "statutory floor" in warning

    quote = build_normalized_quote(
        lines=[l if l.dimension != dim else quote_line for l in basis.lines],
    )
    comparability, warnings = assess_comparability(quote, basis)
    assert comparability == Comparability.DIFFERS_ON_COVERAGE  # identical_basis NOT reached
    assert any("statutory floor" in w for w in warnings)

    report = build_comparison_report([quote], basis)
    ab_delta = next(d for d in report.coverage_deltas if d.dimension == dim)
    assert ab_delta.materiality == "minor"
    # a minor delta alone must not invalidate price comparison
    assert report.price_view.price_comparison_valid is True
