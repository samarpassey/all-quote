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
