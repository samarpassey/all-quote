import pytest
from pydantic import ValidationError

from allquote.schemas import (
    CoverageDimension,
    EvidenceRecord,
    IntakeAddress,
    IntakeContact,
    IntakeHistory,
    IntakeIdentity,
    IntakeLicence,
    IntakeProfile,
    IntakeVehicle,
    MarketRecord,
    QuoteResult,
    Status,
    sensitive_fields,
)
from tests.fixtures import (
    build_address,
    build_evidence_record,
    build_intake_profile,
    build_market_record,
    build_quote_result,
)

EXPECTED_STATUS_VALUES = [
    "quoted_comparable",
    "quoted_non_comparable",
    "estimate_only",
    "callback_required",
    "manual_handoff",
    "ineligible",
    "affinity_restricted",
    "specialty_only",
    "duplicate_rate_source",
    "not_currently_writing",
    "blocked",
    "unreachable",
    "unresolved",
]


def test_status_has_exactly_13_values_matching_docs():
    assert len(Status) == 13
    assert {s.value for s in Status} == set(EXPECTED_STATUS_VALUES)


EXPECTED_COVERAGE_DIMENSION_VALUES = [
    "third_party_liability",
    "accident_benefits_mandatory",
    "ab_opt_income_replacement",
    "ab_opt_non_earner",
    "ab_opt_caregiver",
    "ab_opt_lost_educational_expenses",
    "ab_opt_expenses_of_visitors",
    "ab_opt_housekeeping_home_maintenance",
    "ab_opt_damage_to_personal_items",
    "ab_opt_death",
    "ab_opt_funeral",
    "ab_opt_dependant_care",
    "ab_opt_indexation",
    "ab_opt_supplementary_medical_rehab_attendant_care",
    "ab_opt_catastrophic_impairment",
    "uninsured_automobile",
    "dcpd",
    "own_damage_specified_perils",
    "own_damage_comprehensive",
    "own_damage_collision",
    "own_damage_all_perils",
    "opcf_20_transportation_replacement",
    "opcf_27_non_owned_automobiles",
    "opcf_43_removing_depreciation_deduction",
    "opcf_44r_family_protection",
    "opcf_49_dcpd_opt_out",
    "other_endorsement",
]


def test_coverage_dimension_has_exactly_27_values_matching_docs():
    assert len(CoverageDimension) == 27
    assert {d.value for d in CoverageDimension} == set(EXPECTED_COVERAGE_DIMENSION_VALUES)


def test_intake_profile_round_trip_json():
    profile = build_intake_profile()
    restored = IntakeProfile.model_validate_json(profile.model_dump_json())
    assert restored == profile


def test_intake_profile_rejects_invalid_use_type():
    profile = build_intake_profile()
    payload = profile.model_dump(mode="json")
    payload["use"] = {
        "use_type": "joyriding",
        "annual_km": 1000,
        "winter_tires": True,
        "anti_theft": False,
    }
    with pytest.raises(ValidationError):
        IntakeProfile.model_validate(payload)


def test_intake_profile_partial_fill_validates_and_reports_completeness():
    profile = build_intake_profile()
    assert profile.consent is None
    assert profile.contact is None
    assert profile.use is None
    assert profile.history is None

    completeness = profile.completeness()
    assert completeness["identity"] is True
    assert completeness["licence"] is True
    assert completeness["vehicle"] is True
    assert completeness["address"] is True
    assert completeness["coverage_benchmark"] is True
    assert completeness["consent"] is False
    assert completeness["contact"] is False
    assert completeness["use"] is False
    assert completeness["history"] is False


def test_address_fsa_rejects_malformed_value():
    with pytest.raises(ValidationError):
        build_address(fsa="12A")
    with pytest.raises(ValidationError):
        build_address(fsa="toolong")


def test_address_fsa_accepts_and_uppercases_valid_value():
    address = build_address(fsa="m5v")
    assert address.fsa == "M5V"


def test_market_record_round_trip_json():
    record = build_market_record()
    restored = MarketRecord.model_validate_json(record.model_dump_json())
    assert restored == record


def test_market_record_rejects_invalid_distribution_type():
    with pytest.raises(ValidationError):
        build_market_record(distribution_type="reseller")


def test_market_record_rejects_invalid_product_scope():
    with pytest.raises(ValidationError):
        build_market_record(product_scope="lifestyle")


def test_quote_result_round_trip_json():
    result = build_quote_result()
    restored = QuoteResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_quote_result_requires_non_empty_evidence_artifact():
    with pytest.raises(ValidationError):
        result = build_quote_result()
        payload = result.model_dump(mode="json")
        payload["evidence"]["evidence_artifact"] = ""
        QuoteResult.model_validate(payload)


def test_evidence_record_round_trip_json():
    record = build_evidence_record()
    restored = EvidenceRecord.model_validate_json(record.model_dump_json())
    assert restored == record


def test_evidence_record_supports_consent_receipt_kind():
    record = build_evidence_record(
        kind="consent_receipt", consent_receipt_id="receipt-0001"
    )
    assert record.kind == "consent_receipt"
    assert record.consent_receipt_id == "receipt-0001"


def test_evidence_record_rejects_bad_hash_format():
    with pytest.raises(ValidationError):
        build_evidence_record(evidence_hash="not-a-hash")


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (IntakeIdentity, {"legal_name", "date_of_birth"}),
        (IntakeContact, {"email", "mobile"}),
        (IntakeAddress, {"street", "unit", "postal_code"}),
        (IntakeLicence, {"licence_number"}),
        (IntakeVehicle, {"vin"}),
        (IntakeHistory, {"accidents", "convictions", "suspensions", "cancellations"}),
    ],
)
def test_sensitive_fields_finds_vaultref_fields(model, expected):
    assert sensitive_fields(model) == frozenset(expected)
