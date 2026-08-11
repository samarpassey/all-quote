"""Label -> CoverageDimension mapping, as DATA. See PLAN.md Task 8 / the
approved plan (docs/SCHEMAS.md "Normalizer derived models").

This module holds no comparison judgement — no materiality, no comparability,
no status. It only answers two questions: "which dimension does this verbatim
market label mean" and "what number is in this verbatim value string". Both
answers are table lookups or deterministic parsing, never inference about
whether a difference matters. That split is what keeps the "the LLM
transcribes, code interprets" boundary (Part B) honest: nothing here decides
whether a difference is worth flagging, only what a label denotes.

The two exceptions — INFERENCE_RULES and BASIS_DEFAULTS below — are still
data, not judgement: each is a small, fixed table of (input -> output) pairs
taken directly from BRIEF.md, not a rule computed from a comparison.
"""

import re

from allquote.intake import OPTIONAL_AB_BENEFITS
from allquote.schemas import CoverageDimension, DisclosureState

_D = CoverageDimension


# --- label -> dimension table -----------------------------------------------
#
# Each dimension maps to one or more (all_of, none_of) keyword groups, checked
# against the *normalized* label (lowercased, punctuation stripped to spaces,
# whitespace collapsed). A label matches a dimension if it satisfies at least
# one of that dimension's groups. A single label may match more than one
# dimension (a combined label like "Caregiver, Housekeeping & Home
# Maintenance" legitimately names two benefits at once).

LabelRule = tuple[CoverageDimension, tuple[str, ...], tuple[str, ...]]  # (dim, all_of, none_of)

LABEL_RULES: list[LabelRule] = [
    (_D.THIRD_PARTY_LIABILITY, ("liability",), ()),
    (_D.ACCIDENT_BENEFITS_MANDATORY, ("accident benefits", "standard"), ()),
    (_D.AB_OPT_INCOME_REPLACEMENT, ("income replacement",), ()),
    (_D.AB_OPT_NON_EARNER, ("non earner",), ()),
    (_D.AB_OPT_CAREGIVER, ("caregiver",), ()),
    (_D.AB_OPT_LOST_EDUCATIONAL_EXPENSES, ("educational expenses",), ()),
    (_D.AB_OPT_EXPENSES_OF_VISITORS, ("expenses of visitors",), ()),
    (_D.AB_OPT_HOUSEKEEPING_HOME_MAINTENANCE, ("housekeeping",), ()),
    (_D.AB_OPT_DAMAGE_TO_PERSONAL_ITEMS, ("damage to personal",), ()),
    (_D.AB_OPT_DEATH, ("death benefit",), ()),
    (_D.AB_OPT_FUNERAL, ("funeral",), ()),
    (_D.AB_OPT_DEPENDANT_CARE, ("dependant care",), ()),
    (_D.AB_OPT_INDEXATION, ("indexation",), ()),
    (_D.AB_OPT_SUPPLEMENTARY_MEDICAL_REHAB_ATTENDANT_CARE, ("supplementary medical",), ()),
    (_D.AB_OPT_CATASTROPHIC_IMPAIRMENT, ("catastrophic impairment",), ()),
    (_D.UNINSURED_AUTOMOBILE, ("uninsured automobile",), ()),
    (_D.DCPD, ("direct compensation",), ()),
    (_D.OWN_DAMAGE_SPECIFIED_PERILS, ("specified perils",), ()),
    (_D.OWN_DAMAGE_COMPREHENSIVE, ("comprehensive",), ()),
    (_D.OWN_DAMAGE_COLLISION, ("collision",), ("other than",)),
    (_D.OWN_DAMAGE_ALL_PERILS, ("all perils",), ()),
    (_D.OPCF_20_TRANSPORTATION_REPLACEMENT, ("transportation replacement",), ()),
    (_D.OPCF_20_TRANSPORTATION_REPLACEMENT, ("loss of use",), ()),
    (_D.OPCF_27_NON_OWNED_AUTOMOBILES, ("opcf 27",), ()),
    (_D.OPCF_27_NON_OWNED_AUTOMOBILES, ("non owned automobile",), ()),
    (_D.OPCF_43_REMOVING_DEPRECIATION_DEDUCTION, ("opcf 43",), ()),
    (_D.OPCF_43_REMOVING_DEPRECIATION_DEDUCTION, ("depreciation",), ()),
    (_D.OPCF_44R_FAMILY_PROTECTION, ("44r",), ()),
    (_D.OPCF_44R_FAMILY_PROTECTION, ("family protection",), ()),
    (_D.OPCF_49_DCPD_OPT_OUT, ("opcf 49",), ()),
    (_D.OPCF_49_DCPD_OPT_OUT, ("dcpd opt out",), ()),
]


def normalize_label_text(label: str) -> str:
    text = label.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_dimensions(label: str) -> list[CoverageDimension]:
    """All dimensions this verbatim label denotes. Empty means unmapped —
    caller's responsibility to fall back to other_endorsement."""
    normalized = normalize_label_text(label)
    matched: list[CoverageDimension] = []
    for dimension, all_of, none_of in LABEL_RULES:
        if dimension in matched:
            continue
        if all(kw in normalized for kw in all_of) and not any(kw in normalized for kw in none_of):
            matched.append(dimension)
    return matched


# --- value parsing -----------------------------------------------------------

_AMOUNT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*([mk]?)", re.IGNORECASE)
_AMOUNT_ALLOWED_CHARS = re.compile(r"[^0-9.mkMK]")


def parse_currency_amount(value: str | None) -> int | None:
    """Deterministic parser for verbatim value strings like "$1,000,000",
    "1M", "$500 ded.". Returns None (never a guessed number) when the string
    doesn't contain a recognizable amount."""
    if not value:
        return None
    cleaned = _AMOUNT_ALLOWED_CHARS.sub("", value)
    match = _AMOUNT_PATTERN.search(cleaned)
    if not match or not match.group(1):
        return None
    amount = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "m":
        amount *= 1_000_000
    elif suffix == "k":
        amount *= 1_000
    return int(amount)


# --- permitted inferences (A3: exactly two, both from BRIEF.md §6) ----------
#
# Each rule: if `trigger` dimension/disclosure is present in a quote's lines,
# emit the listed (dimension, disclosure) lines with provenance="derived",
# UNLESS that dimension already has an observed line (an explicit market
# disclosure always outranks an inference). Add no others.

InferenceRule = tuple[
    tuple[CoverageDimension, DisclosureState],  # trigger
    tuple[tuple[CoverageDimension, DisclosureState], ...],  # inferred lines
    str,  # warning template
]

INFERENCE_RULES: list[InferenceRule] = [
    (
        (_D.OWN_DAMAGE_ALL_PERILS, DisclosureState.INCLUDED),
        (
            (_D.OWN_DAMAGE_COLLISION, DisclosureState.INCLUDED),
            (_D.OWN_DAMAGE_COMPREHENSIVE, DisclosureState.INCLUDED),
        ),
        "all perils coverage was disclosed as included; collision and comprehensive "
        "are inferred included as a result (all perils subsumes both), not separately observed",
    ),
    (
        (_D.OPCF_49_DCPD_OPT_OUT, DisclosureState.INCLUDED),
        ((_D.DCPD, DisclosureState.EXCLUDED),),
        "OPCF 49 (DCPD opt-out) was disclosed as included; DCPD is inferred excluded as a "
        "result — per BRIEF.md §6, collision and all-perils implications should be verified "
        "separately",
    ),
]


# --- RequestedBasis defaults for dimensions CoverageBenchmark doesn't cover -
#
# CoverageBenchmark has no field for these four; each default is a documented
# rationale, not a blanket fallback. Test-asserted to equal exactly the set of
# dimensions not otherwise derivable from a real CoverageBenchmark field.

BASIS_DEFAULTS: dict[CoverageDimension, DisclosureState] = {
    # Mandatory by law; per BRIEF.md §6, only medical, rehabilitation and
    # attendant care remain mandatory for new Ontario policies after July 1,
    # 2026 — not a limit we synthesize, so this dimension carries no
    # limit_cad in the basis.
    _D.ACCIDENT_BENEFITS_MANDATORY: DisclosureState.INCLUDED,
    # Mandatory Ontario coverage; BRIEF.md §6 requires included status and
    # limit details where returned.
    _D.UNINSURED_AUTOMOBILE: DisclosureState.INCLUDED,
    # The demo benchmark elects collision + comprehensive; specified perils
    # is the unchosen alternative peril basis.
    _D.OWN_DAMAGE_SPECIFIED_PERILS: DisclosureState.EXCLUDED,
    # Same reason as specified perils: collision + comprehensive was chosen.
    _D.OWN_DAMAGE_ALL_PERILS: DisclosureState.EXCLUDED,
    # The benchmark includes DCPD; electing the DCPD opt-out would
    # contradict the basis.
    _D.OPCF_49_DCPD_OPT_OUT: DisclosureState.EXCLUDED,
}


# --- optional AB short-key -> dimension map ----------------------------------
#
# IntakeProfile.coverage_benchmark.optional_ab_selections uses short keys
# (allquote.intake.OPTIONAL_AB_BENEFITS — the single source of truth for the
# 13 names, reused here rather than re-typed) that don't literally match the
# ab_opt_* dimension names.

AB_OPT_KEY_MAP: dict[str, CoverageDimension] = {
    "income_replacement": _D.AB_OPT_INCOME_REPLACEMENT,
    "non_earner": _D.AB_OPT_NON_EARNER,
    "caregiver": _D.AB_OPT_CAREGIVER,
    "lost_educational_expenses": _D.AB_OPT_LOST_EDUCATIONAL_EXPENSES,
    "expenses_of_visitors": _D.AB_OPT_EXPENSES_OF_VISITORS,
    "housekeeping": _D.AB_OPT_HOUSEKEEPING_HOME_MAINTENANCE,
    "damage_to_personal_items": _D.AB_OPT_DAMAGE_TO_PERSONAL_ITEMS,
    "death": _D.AB_OPT_DEATH,
    "funeral": _D.AB_OPT_FUNERAL,
    "dependant_care": _D.AB_OPT_DEPENDANT_CARE,
    "indexation": _D.AB_OPT_INDEXATION,
    "supplementary_medical": _D.AB_OPT_SUPPLEMENTARY_MEDICAL_REHAB_ATTENDANT_CARE,
    "catastrophic": _D.AB_OPT_CATASTROPHIC_IMPAIRMENT,
}

assert set(AB_OPT_KEY_MAP) == set(OPTIONAL_AB_BENEFITS), (
    "AB_OPT_KEY_MAP must cover exactly allquote.intake.OPTIONAL_AB_BENEFITS"
)
