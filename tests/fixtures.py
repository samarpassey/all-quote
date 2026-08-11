"""Fake-data builders for tests.

No real personal data anywhere: every sensitive field is an obviously-fake
VaultRef token (e.g. "fake-ref-licence-0001"), never a realistic-looking
licence number, VIN, or DOB.
"""

from datetime import date, datetime, timezone
from pathlib import Path

from allquote.schemas import (
    CoverageBenchmark,
    CoverageComparison,
    DiscountInfo,
    EvidenceInfo,
    EvidenceRecord,
    IntakeAddress,
    IntakeContact,
    IntakeHistory,
    IntakeIdentity,
    IntakeLicence,
    IntakeProfile,
    IntakeVehicle,
    MarketRecord,
    PrivacyInfo,
    QuoteOutcome,
    QuoteResult,
    QuoteSource,
    Status,
    ValidityInfo,
    VaultRef,
)


def fake_ref(label: str) -> VaultRef:
    return VaultRef(f"fake-ref-{label}-0001")


def build_identity(**overrides) -> IntakeIdentity:
    data = dict(
        legal_name=fake_ref("legal-name"),
        preferred_language="english",
        date_of_birth=fake_ref("dob"),
        gender="prefer_not_to_say",
        marital_status="single",
    )
    data.update(overrides)
    return IntakeIdentity(**data)


def build_licence(**overrides) -> IntakeLicence:
    data = dict(
        licence_number=fake_ref("licence"),
        province="ON",
        class_="G",
        status="valid",
        g1_date=date(2018, 1, 1),
        g2_date=date(2018, 7, 1),
        g_date=date(2019, 1, 1),
        first_licensed_date=date(2018, 1, 1),
        driver_training_completed=True,
    )
    data.update(overrides)
    return IntakeLicence(**data)


def build_vehicle(**overrides) -> IntakeVehicle:
    data = dict(
        vin=fake_ref("vin"),
        model_year=2022,
        make="Testmake",
        model="Testmodel",
        trim="Base",
        ownership="owned",
        purchase_year_month="2022-06",
        lienholder=None,
    )
    data.update(overrides)
    return IntakeVehicle(**data)


def build_address(**overrides) -> IntakeAddress:
    data = dict(
        street=fake_ref("street"),
        unit=None,
        city="Testville",
        province="ON",
        postal_code=fake_ref("postal"),
        fsa="M5V",
        residence_start_date=date(2020, 1, 1),
        is_garaging_location=True,
    )
    data.update(overrides)
    return IntakeAddress(**data)


def build_coverage_benchmark(**overrides) -> CoverageBenchmark:
    data = dict(
        effective_date=date(2026, 8, 9),
        liability_limit=2_000_000,
        dcpd_included=True,
        collision_deductible=1000,
        comprehensive_deductible=1000,
        endorsements=["opcf_44r"],
        optional_ab_selections={"opcf_20": "included"},
        telematics_opt_in=False,
    )
    data.update(overrides)
    return CoverageBenchmark(**data)


def build_intake_profile(**overrides) -> IntakeProfile:
    data = dict(
        identity=build_identity(),
        licence=build_licence(),
        vehicle=build_vehicle(),
        address=build_address(),
        coverage_benchmark=build_coverage_benchmark(),
    )
    data.update(overrides)
    return IntakeProfile(**data)


def build_market_record(**overrides) -> MarketRecord:
    data = dict(
        registry_id="test-route-0001",
        legal_underwriter="Test Underwriter Co.",
        insurer_group="Test Group",
        brand_or_program="TestBrand Direct",
        distribution_type="direct",
        product_scope="standard_PPA",
        distinct_rate_source_id=None,
        quote_url="https://example.invalid/quote",
        public_phone_route=None,
        licensed_intermediary=None,
        requirements=["licence"],
        automation_notes=None,
        status=Status.UNRESOLVED,
        source_url="https://example.invalid/about",
        last_verified_at=None,
        evidence_artifact=None,
    )
    data.update(overrides)
    return MarketRecord(**data)


def build_quote_result(**overrides) -> QuoteResult:
    data = dict(
        source=QuoteSource(
            registry_id="test-route-0001",
            brand_or_program="TestBrand Direct",
            legal_underwriter="Test Underwriter Co.",
            insurer_group="Test Group",
            licensed_intermediary=None,
            distinct_rate_source_id="test-underwriter::standard_PPA",
        ),
        outcome=QuoteOutcome(
            status=Status.QUOTED_COMPARABLE,
            is_exact_quote=True,
            failure_reason=None,
            next_action=None,
        ),
        coverage=CoverageComparison(
            requested={"liability_limit": 2_000_000},
            returned={"liability_limit": 2_000_000},
            variance_from_benchmark=[],
        ),
        discounts=DiscountInfo(),
        validity=ValidityInfo(
            quote_reference_id="TEST-REF-0001",
            effective_date=date(2026, 8, 9),
            expiry_date=date(2026, 9, 8),
            verification_may_change_premium=False,
        ),
        evidence=EvidenceInfo(
            timestamp=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
            source_url_or_phone="https://example.invalid/quote",
            evidence_artifact="data/evidence/test-route-0001/quote.png",
            evidence_hash="a" * 64,
        ),
        confidence="high",
        privacy=PrivacyInfo(
            fields_disclosed=["make", "model", "model_year"],
            consent_receipt_id=None,
            retention_deadline=None,
        ),
        price=None,
    )
    data.update(overrides)
    return QuoteResult(**data)


def build_evidence_record(**overrides) -> EvidenceRecord:
    data = dict(
        evidence_id="evd-0001",
        registry_id="test-route-0001",
        kind="screenshot",
        timestamp=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
        source_url_or_phone="https://example.invalid/quote",
        artifact_path="data/evidence/test-route-0001/quote.png",
        evidence_hash="a" * 64,
        redacted=True,
        provenance="observed",
        fields_disclosed=["make", "model"],
        consent_receipt_id=None,
        retention_deadline=None,
    )
    data.update(overrides)
    return EvidenceRecord(**data)


def build_vaulted_profile(
    vault_path: Path, vault_key: str, **plaintext_overrides: str
) -> tuple[IntakeProfile, dict[str, str]]:
    """Build an IntakeProfile whose sensitive fields are real vault-backed
    VaultRefs (via vault.put), not the bare fake_ref() tokens used elsewhere in
    this file. For redact.py tests, which need something real to resolve and
    redact. Returns (profile, plaintext_by_field) so tests can assert the
    plaintext doesn't survive redaction. All values are obviously fake
    placeholders, never realistic-looking.
    """
    from allquote import vault

    plaintext = dict(
        legal_name="Fake Testperson",
        date_of_birth="1990-01-15",
        email="fake.testperson@example.invalid",
        mobile="416-555-0100",
        street="123 Fake Test Street",
        postal_code="M5V3A8",
        licence_number="T1234-56789-01234",
        vin="FAKEVEH0000000001",
        accidents="Fake fender-bender note, not at fault",
    )
    plaintext.update(plaintext_overrides)

    def ref(field_name: str) -> VaultRef:
        return vault.put(
            field_name, plaintext[field_name], vault_path=vault_path, vault_key=vault_key
        )

    identity = build_identity(legal_name=ref("legal_name"), date_of_birth=ref("date_of_birth"))
    contact = IntakeContact(
        email=ref("email"), mobile=ref("mobile"), preferred_callback_window="anytime"
    )
    address = build_address(street=ref("street"), postal_code=ref("postal_code"))
    licence = build_licence(licence_number=ref("licence_number"))
    vehicle = build_vehicle(vin=ref("vin"))
    history = IntakeHistory(
        years_continuously_insured=5,
        current_insurer=None,
        accidents=[ref("accidents")],
    )

    profile = build_intake_profile(
        identity=identity,
        licence=licence,
        vehicle=vehicle,
        address=address,
        contact=contact,
        history=history,
    )
    return profile, plaintext
