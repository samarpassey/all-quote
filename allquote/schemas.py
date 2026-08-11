"""Pydantic v2 schemas. Single source of truth; mirrors docs/SCHEMAS.md exactly.

Do not rename, alias, or add fields here without updating docs/SCHEMAS.md too.
"""

import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, field_validator, model_validator
from pydantic_core import core_schema


class Status(str, Enum):
    QUOTED_COMPARABLE = "quoted_comparable"
    QUOTED_NON_COMPARABLE = "quoted_non_comparable"
    ESTIMATE_ONLY = "estimate_only"
    CALLBACK_REQUIRED = "callback_required"
    MANUAL_HANDOFF = "manual_handoff"
    INELIGIBLE = "ineligible"
    AFFINITY_RESTRICTED = "affinity_restricted"
    SPECIALTY_ONLY = "specialty_only"
    DUPLICATE_RATE_SOURCE = "duplicate_rate_source"
    NOT_CURRENTLY_WRITING = "not_currently_writing"
    BLOCKED = "blocked"
    UNREACHABLE = "unreachable"
    UNRESOLVED = "unresolved"


class VaultRef(str):
    """Opaque vault reference token. Never holds a real sensitive value."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )


def sensitive_fields(model: type[BaseModel]) -> frozenset[str]:
    """Field names on `model` whose annotation is VaultRef (bare, optional, or list-of)."""

    def is_vaultref(annotation: Any) -> bool:
        if annotation is VaultRef:
            return True
        args = get_args(annotation)
        if get_origin(annotation) is not None and args:
            return any(is_vaultref(arg) for arg in args)
        return False

    return frozenset(
        name for name, info in model.model_fields.items() if is_vaultref(info.annotation)
    )


# --- IntakeProfile groups -----------------------------------------------------

FSA_PATTERN = re.compile(r"^[A-Za-z]\d[A-Za-z]$")

# ON first (the applicant's own province), then the remaining 12 provinces
# and territories alphabetically by postal abbreviation.
Province = Literal[
    "ON", "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "PE", "QC", "SK", "YT"
]


class IntakeConsent(BaseModel):
    consent_timestamp: datetime
    mode: Literal["live_quote", "discovery"]
    permitted_channels: list[str] = Field(default_factory=list)
    excluded_routes: list[str] = Field(default_factory=list)
    callback_permission: bool
    recording_consent: bool


PreferredLanguage = Literal["english", "french"]
Gender = Literal["male", "female", "X", "prefer_not_to_say"]
MaritalStatus = Literal[
    "single", "married", "common_law", "separated", "divorced", "widowed"
]


class IntakeIdentity(BaseModel):
    legal_name: VaultRef
    preferred_language: PreferredLanguage
    date_of_birth: VaultRef
    gender: Gender
    marital_status: MaritalStatus


class IntakeContact(BaseModel):
    email: VaultRef
    mobile: VaultRef
    preferred_callback_window: str | None = None


class IntakeAddress(BaseModel):
    street: VaultRef
    unit: VaultRef | None = None
    city: str
    province: Province
    postal_code: VaultRef
    fsa: str
    residence_start_date: date
    is_garaging_location: bool

    @field_validator("fsa")
    @classmethod
    def _validate_fsa(cls, v: str) -> str:
        if not FSA_PATTERN.match(v):
            raise ValueError(
                "fsa must be a 3-character Canadian Forward Sortation Area, e.g. 'M5V'"
            )
        return v.upper()


LicenceClass = Literal[
    "G1", "G2", "G", "M1", "M2", "M", "A", "B", "C", "D", "E", "F", "other"
]
LicenceStatus = Literal["valid", "suspended", "expired", "cancelled"]


class IntakeLicence(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    licence_number: VaultRef
    province: Province
    class_: LicenceClass = Field(alias="class")
    status: LicenceStatus
    g1_date: date | None = None
    g2_date: date | None = None
    g_date: date | None = None
    first_licensed_date: date | None = None
    driver_training_completed: bool


YEAR_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class IntakeVehicle(BaseModel):
    vin: VaultRef | None = None
    model_year: int = Field(ge=1900, le=2027)
    make: str
    model: str
    trim: str | None = None
    ownership: Literal["owned", "leased"]
    purchase_year_month: str
    lienholder: str | None = None

    @field_validator("purchase_year_month")
    @classmethod
    def _validate_purchase_year_month(cls, v: str) -> str:
        if not YEAR_MONTH_PATTERN.match(v):
            raise ValueError("purchase_year_month must be YYYY-MM, e.g. '2022-06'")
        return v


UseType = Literal["pleasure", "commute", "business", "farm", "commercial"]


class IntakeUse(BaseModel):
    use_type: UseType
    commute_km_oneway: float | None = None
    annual_km: int
    winter_tires: bool
    anti_theft: bool


class IntakeHistory(BaseModel):
    years_continuously_insured: float
    current_insurer: str | None = None
    accidents: list[VaultRef] = Field(default_factory=list)
    convictions: list[VaultRef] = Field(default_factory=list)
    suspensions: list[VaultRef] = Field(default_factory=list)
    cancellations: list[VaultRef] = Field(default_factory=list)


LiabilityLimit = Literal[200_000, 500_000, 1_000_000, 2_000_000]
Deductible = Literal[0, 250, 500, 1000, 2500]


class CoverageBenchmark(BaseModel):
    effective_date: date
    liability_limit: LiabilityLimit
    dcpd_included: bool
    collision_deductible: Deductible
    comprehensive_deductible: Deductible
    endorsements: list[Literal["opcf_20", "opcf_27", "opcf_43", "opcf_44r"]] = Field(
        default_factory=list
    )
    optional_ab_selections: dict[
        str, Literal["included", "excluded", "unavailable", "unknown"]
    ] = Field(default_factory=dict)
    telematics_opt_in: bool


class IntakeProfile(BaseModel):
    identity: IntakeIdentity
    licence: IntakeLicence
    vehicle: IntakeVehicle
    address: IntakeAddress
    coverage_benchmark: CoverageBenchmark
    consent: IntakeConsent | None = None
    contact: IntakeContact | None = None
    use: IntakeUse | None = None
    history: IntakeHistory | None = None

    def completeness(self) -> dict[str, bool]:
        return {
            "identity": self.identity is not None,
            "licence": self.licence is not None,
            "vehicle": self.vehicle is not None,
            "address": self.address is not None,
            "coverage_benchmark": self.coverage_benchmark is not None,
            "consent": self.consent is not None,
            "contact": self.contact is not None,
            "use": self.use is not None,
            "history": self.history is not None,
        }


# --- MarketRecord --------------------------------------------------------------

DistributionType = Literal[
    "direct", "agent", "broker", "aggregator", "affinity", "MGA_program", "mutual", "residual"
]
ProductScope = Literal[
    "standard_PPA",
    "nonstandard_PPA",
    "high_net_worth",
    "collector",
    "commercial_specialty",
    "unknown",
]
RequirementFlag = Literal["licence", "VIN", "membership", "callback", "human", "other"]


class MarketRecord(BaseModel):
    registry_id: str
    legal_underwriter: str
    insurer_group: str
    brand_or_program: str
    distribution_type: DistributionType
    product_scope: ProductScope
    distinct_rate_source_id: str | None = None
    quote_url: str | None = None
    public_phone_route: str | None = None
    licensed_intermediary: str | None = None
    requirements: list[RequirementFlag] = Field(default_factory=list)
    automation_notes: str | None = None
    status: Status
    source_url: str
    last_verified_at: datetime | None = None
    evidence_artifact: str | None = None


# --- QuoteResult groups ---------------------------------------------------------


class QuoteSource(BaseModel):
    registry_id: str
    brand_or_program: str
    legal_underwriter: str
    insurer_group: str
    licensed_intermediary: str | None = None
    distinct_rate_source_id: str | None = None


class QuoteOutcome(BaseModel):
    status: Status
    is_exact_quote: bool
    failure_reason: str | None = None
    next_action: str | None = None


class PriceInfo(BaseModel):
    annual_premium: float | None = None
    monthly_amount: float | None = None
    down_payment: float | None = None
    instalment_fee: float | None = None
    taxes_fees: float | None = None
    total_estimated: float | None = None
    currency: str = "CAD"


class CoverageComparison(BaseModel):
    requested: dict[str, Any] = Field(default_factory=dict)
    returned: dict[str, Any] = Field(default_factory=dict)
    variance_from_benchmark: list[str] = Field(default_factory=list)


class DiscountInfo(BaseModel):
    applied: list[str] = Field(default_factory=list)
    available_not_selected: list[str] = Field(default_factory=list)
    conditional: list[str] = Field(default_factory=list)


class ValidityInfo(BaseModel):
    quote_reference_id: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    verification_may_change_premium: bool


class EvidenceInfo(BaseModel):
    timestamp: datetime
    source_url_or_phone: str
    evidence_artifact: str
    evidence_hash: str


class PrivacyInfo(BaseModel):
    fields_disclosed: list[str] = Field(default_factory=list)
    consent_receipt_id: str | None = None
    retention_deadline: date | None = None


class QuoteResult(BaseModel):
    source: QuoteSource
    outcome: QuoteOutcome
    coverage: CoverageComparison
    discounts: DiscountInfo
    validity: ValidityInfo
    evidence: EvidenceInfo
    confidence: Literal["high", "medium", "low"]
    privacy: PrivacyInfo
    price: PriceInfo | None = None

    @model_validator(mode="after")
    def _require_evidence_artifact(self) -> "QuoteResult":
        if not self.evidence.evidence_artifact.strip():
            raise ValueError(
                "QuoteResult.evidence.evidence_artifact is required and cannot be empty "
                "(ARCHITECTURE.md: a result row without evidence is invalid at the schema level)"
            )
        return self


# --- EvidenceRecord --------------------------------------------------------------

EvidenceKind = Literal[
    "screenshot",
    "html_snapshot",
    "call_transcript",
    "call_outcome",
    "consent_receipt",
    "document",
]

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


Provenance = Literal["observed", "derived"]


class EvidenceRecord(BaseModel):
    evidence_id: str
    registry_id: str
    kind: EvidenceKind
    timestamp: datetime
    source_url_or_phone: str
    artifact_path: str
    evidence_hash: str
    redacted: bool
    provenance: Provenance
    fields_disclosed: list[str] = Field(default_factory=list)
    consent_receipt_id: str | None = None
    retention_deadline: datetime | None = None

    @field_validator("evidence_hash")
    @classmethod
    def _validate_hash(cls, v: str) -> str:
        if not _SHA256_HEX.match(v):
            raise ValueError("evidence_hash must be a 64-character sha256 hex digest")
        return v


# --- Normalizer derived models (Task 8) -----------------------------------------
#
# Everything below is derived from QuoteResult + IntakeProfile, not part of the
# five canonical models (IntakeProfile, MarketRecord, QuoteResult, EvidenceRecord,
# VaultRef). Mirrors docs/SCHEMAS.md's "Normalizer derived models" section.


class CoverageDimension(str, Enum):
    THIRD_PARTY_LIABILITY = "third_party_liability"
    ACCIDENT_BENEFITS_MANDATORY = "accident_benefits_mandatory"
    AB_OPT_INCOME_REPLACEMENT = "ab_opt_income_replacement"
    AB_OPT_NON_EARNER = "ab_opt_non_earner"
    AB_OPT_CAREGIVER = "ab_opt_caregiver"
    AB_OPT_LOST_EDUCATIONAL_EXPENSES = "ab_opt_lost_educational_expenses"
    AB_OPT_EXPENSES_OF_VISITORS = "ab_opt_expenses_of_visitors"
    AB_OPT_HOUSEKEEPING_HOME_MAINTENANCE = "ab_opt_housekeeping_home_maintenance"
    AB_OPT_DAMAGE_TO_PERSONAL_ITEMS = "ab_opt_damage_to_personal_items"
    AB_OPT_DEATH = "ab_opt_death"
    AB_OPT_FUNERAL = "ab_opt_funeral"
    AB_OPT_DEPENDANT_CARE = "ab_opt_dependant_care"
    AB_OPT_INDEXATION = "ab_opt_indexation"
    AB_OPT_SUPPLEMENTARY_MEDICAL_REHAB_ATTENDANT_CARE = (
        "ab_opt_supplementary_medical_rehab_attendant_care"
    )
    AB_OPT_CATASTROPHIC_IMPAIRMENT = "ab_opt_catastrophic_impairment"
    UNINSURED_AUTOMOBILE = "uninsured_automobile"
    DCPD = "dcpd"
    OWN_DAMAGE_SPECIFIED_PERILS = "own_damage_specified_perils"
    OWN_DAMAGE_COMPREHENSIVE = "own_damage_comprehensive"
    OWN_DAMAGE_COLLISION = "own_damage_collision"
    OWN_DAMAGE_ALL_PERILS = "own_damage_all_perils"
    OPCF_20_TRANSPORTATION_REPLACEMENT = "opcf_20_transportation_replacement"
    OPCF_27_NON_OWNED_AUTOMOBILES = "opcf_27_non_owned_automobiles"
    OPCF_43_REMOVING_DEPRECIATION_DEDUCTION = "opcf_43_removing_depreciation_deduction"
    OPCF_44R_FAMILY_PROTECTION = "opcf_44r_family_protection"
    OPCF_49_DCPD_OPT_OUT = "opcf_49_dcpd_opt_out"
    OTHER_ENDORSEMENT = "other_endorsement"


# Every CoverageDimension except OTHER_ENDORSEMENT gets exactly one line on
# every RequestedBasis and every NormalizedQuote. OTHER_ENDORSEMENT is the one
# exception: it may repeat (one line per distinct unmapped label) or be absent.
REQUESTABLE_DIMENSIONS: frozenset[CoverageDimension] = frozenset(
    d for d in CoverageDimension if d != CoverageDimension.OTHER_ENDORSEMENT
)


class DisclosureState(str, Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class Comparability(str, Enum):
    IDENTICAL_BASIS = "identical_basis"
    DIFFERS_ON_COVERAGE = "differs_on_coverage"
    INDICATIVE_ONLY = "indicative_only"
    NOT_COMPARABLE = "not_comparable"


class CoverageObservation(BaseModel):
    """Raw verbatim capture: what a market's page or rep said, uninterpreted."""

    source_label: str
    source_value: str | None = None
    captured_at: datetime
    evidence_id: str


class CoverageLine(BaseModel):
    """One interpreted coverage dimension, on a RequestedBasis or a NormalizedQuote."""

    dimension: CoverageDimension
    disclosure: DisclosureState
    limit_cad: float | None = None
    deductible_cad: float | None = None
    source_label: str | None = None
    source_value: str | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def _unknown_carries_no_values(self) -> "CoverageLine":
        if self.disclosure == DisclosureState.UNKNOWN:
            if any(
                v is not None
                for v in (self.limit_cad, self.deductible_cad, self.source_label, self.source_value)
            ):
                raise ValueError(
                    "CoverageLine with disclosure=unknown must carry no limit, deductible, "
                    "or source origin — silence is recorded, never given a substitute value"
                )
        elif self.source_label is None:
            raise ValueError(
                "CoverageLine with disclosure != unknown must carry a verbatim source_label "
                "— None is reserved for the unknown case"
            )
        return self


class RequestedBasis(BaseModel):
    """The single reference coverage basis for one run, derived once from
    IntakeProfile.coverage_benchmark. Every quote's comparability is assessed
    against this — never pairwise between quotes."""

    requested_basis_id: str
    requested_effective_date: date
    term_months: int
    lines: list[CoverageLine]
    captured_at: datetime

    @model_validator(mode="after")
    def _covers_every_requestable_dimension_as_known(self) -> "RequestedBasis":
        seen = [line.dimension for line in self.lines]
        if len(seen) != len(set(seen)):
            raise ValueError("RequestedBasis has a duplicate dimension line")
        if set(seen) != REQUESTABLE_DIMENSIONS:
            missing = REQUESTABLE_DIMENSIONS - set(seen)
            extra = set(seen) - REQUESTABLE_DIMENSIONS
            raise ValueError(
                f"RequestedBasis must carry exactly one line per requestable dimension "
                f"(missing={sorted(d.value for d in missing)}, extra={sorted(d.value for d in extra)})"
            )
        for line in self.lines:
            if line.disclosure not in (DisclosureState.INCLUDED, DisclosureState.EXCLUDED):
                raise ValueError(
                    f"RequestedBasis.{line.dimension.value} has disclosure={line.disclosure.value}: "
                    "a basis is authored by us, not observed from a market — every dimension is "
                    "either included or excluded by our own request, never unavailable or unknown"
                )
        return self


class NormalizedPremium(BaseModel):
    annual_premium_cad: float | None = None
    monthly_premium_cad: float | None = None
    annualized_from_monthly_cad: float | None = None
    annualized_by_us: bool = False
    down_payment_cad: float | None = None
    instalment_count: int | None = None
    instalment_amount_cad: float | None = None
    finance_or_instalment_charges_cad: float | None = None
    taxes_or_fees_cad: float | None = None
    total_estimated_cost_cad: float | None = None
    currency: str = "CAD"
    term_months: int | None = None
    payment_basis: Literal["annual", "monthly", "not_disclosed"]

    @model_validator(mode="after")
    def _monthly_only_never_yields_annual(self) -> "NormalizedPremium":
        if self.payment_basis == "monthly" and self.annual_premium_cad is not None:
            raise ValueError(
                "payment_basis='monthly' but annual_premium_cad is set — Ontario monthly "
                "plans carry finance charges; annual must never be derived from monthly x 12"
            )
        if not self.annualized_by_us and self.annualized_from_monthly_cad is not None:
            raise ValueError("annualized_from_monthly_cad is set but annualized_by_us is False")
        return self


class NormalizedValidity(BaseModel):
    quote_or_reference_id: str | None = None
    effective_date: date | None = None
    expiry_or_guarantee_date: date | None = None
    verification_may_change_premium: bool | None = None


class NormalizedDiscount(BaseModel):
    name: str
    state: Literal["applied", "available_not_selected", "conditional_on_purchase"]
    condition: str | None = None


class NormalizedQuote(BaseModel):
    market_id: str
    rate_source_id: str | None = None
    status: Status
    # Stored, not re-derivable-by-name: ComparisonReport.comparability is
    # explicitly required to be COPIED from here, never recomputed (A4) — so
    # this needs a place to live even though the task's NormalizedQuote field
    # list didn't name it. Computed once by assess_comparability() and never
    # touched again.
    comparability: Comparability
    requested_basis_id: str
    lines: list[CoverageLine]
    binding_basis: Literal["bound_offer", "indicative_assumption", "none"]
    premium: NormalizedPremium
    validity: NormalizedValidity
    discounts: list[NormalizedDiscount] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    normalization_warnings: list[str] = Field(default_factory=list)
    captured_at: datetime
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _covers_every_requestable_dimension(self) -> "NormalizedQuote":
        seen = [line.dimension for line in self.lines if line.dimension != CoverageDimension.OTHER_ENDORSEMENT]
        if len(seen) != len(set(seen)):
            raise ValueError("NormalizedQuote has a duplicate non-other_endorsement dimension line")
        if set(seen) != REQUESTABLE_DIMENSIONS:
            missing = REQUESTABLE_DIMENSIONS - set(seen)
            extra = set(seen) - REQUESTABLE_DIMENSIONS
            raise ValueError(
                f"NormalizedQuote must carry exactly one line per requestable dimension "
                f"(missing={sorted(d.value for d in missing)}, extra={sorted(d.value for d in extra)}); "
                "dimensions never mentioned by the market must still appear with disclosure=unknown"
            )
        return self


class CoverageDelta(BaseModel):
    """One dimension's row in a ComparisonReport: what the basis asked for,
    what each compared quote disclosed, and how material the difference is."""

    dimension: CoverageDimension
    requested: CoverageLine
    per_quote: dict[str, CoverageLine]
    materiality: Literal["material", "minor", "evidenced_gap", "undisclosed_gap"]
    warning: str | None = None


class PriceView(BaseModel):
    per_quote: dict[str, NormalizedPremium]
    price_comparison_valid: bool
    reason: str


class ComparisonReport(BaseModel):
    """Reports only — never sets status (allquote.normalize owns that via
    assess_comparability). Field declaration order is significant: coverage
    differences must serialize before price, per BRIEF.md §7 ("see coverage
    differences before price differences")."""

    inputs: list[str]
    requested_basis_id: str
    comparability: dict[str, Comparability]
    coverage_deltas: list[CoverageDelta]
    undisclosed_dimensions: list[CoverageDimension]
    price_view: PriceView
