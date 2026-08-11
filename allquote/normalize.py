"""Raw executor output -> comparable output. See PLAN.md Task 8 / the
approved plan (docs/SCHEMAS.md "Normalizer derived models").

Orchestrates allquote.normalize_basis (RequestedBasis + coverage lines) and
allquote.normalize_compare (materiality, comparability, bounded-authority
status derivation, the pairwise ComparisonReport) into one entry point per
quote (`normalize_quote`) and the CLI.

Dedupe (re-deriving distinct_rate_source_id against real QuoteResults,
assigning duplicate_rate_source) is explicitly OUT of scope here — deferred
to a follow-up task per the approved plan; this module never touches
distinct_rate_source_id.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from allquote import evidence as evidence_mod
from allquote import intake
from allquote.normalize_basis import derive_requested_basis, map_observations_to_lines, unknown_line
from allquote.normalize_compare import (
    LICENSED_INTERMEDIARY_CHANNELS,
    PRICED_TRIAD,
    assess_comparability,
    build_comparison_report,
    derive_confidence,
    derive_priced_status,
)
from allquote.redact import safe_write_evidence
from allquote.schemas import (
    REQUESTABLE_DIMENSIONS,
    Comparability,
    CoverageObservation,
    NormalizedDiscount,
    NormalizedPremium,
    NormalizedQuote,
    NormalizedValidity,
    QuoteResult,
    RequestedBasis,
    Status,
)

EXPORT_DIR = Path("exports")

__all__ = [
    "normalize_quote",
    "build_comparison_report",
    "derive_requested_basis",
    "PRICED_TRIAD",
    "LICENSED_INTERMEDIARY_CHANNELS",
]


# --- premium / validity / discounts (QuoteResult -> Normalized*) --------------


def _build_premium(quote_result: QuoteResult, basis: RequestedBasis) -> NormalizedPremium:
    price = quote_result.price
    annual = price.annual_premium if price else None
    monthly = price.monthly_amount if price else None
    payment_basis = "annual" if annual is not None else ("monthly" if monthly is not None else "not_disclosed")
    return NormalizedPremium(
        annual_premium_cad=annual,
        monthly_premium_cad=monthly,
        annualized_from_monthly_cad=None,
        annualized_by_us=False,
        down_payment_cad=price.down_payment if price else None,
        instalment_count=None,
        instalment_amount_cad=None,
        finance_or_instalment_charges_cad=price.instalment_fee if price else None,
        taxes_or_fees_cad=price.taxes_fees if price else None,
        total_estimated_cost_cad=price.total_estimated if price else None,
        currency=price.currency if price else "CAD",
        term_months=basis.term_months,
        payment_basis=payment_basis,
    )


def _build_validity(quote_result: QuoteResult) -> NormalizedValidity:
    v = quote_result.validity
    return NormalizedValidity(
        quote_or_reference_id=v.quote_reference_id,
        effective_date=v.effective_date,
        expiry_or_guarantee_date=v.expiry_date,
        verification_may_change_premium=v.verification_may_change_premium,
    )


def _build_discounts(quote_result: QuoteResult) -> list[NormalizedDiscount]:
    d = quote_result.discounts
    out = [NormalizedDiscount(name=n, state="applied") for n in d.applied]
    out += [NormalizedDiscount(name=n, state="available_not_selected") for n in d.available_not_selected]
    out += [NormalizedDiscount(name=n, state="conditional_on_purchase") for n in d.conditional]
    return out


# --- top-level entry point ------------------------------------------------------


def normalize_quote(
    quote_result: QuoteResult,
    observations: list[CoverageObservation],
    basis: RequestedBasis,
    *,
    distribution_type: str,
    requested_basis_id: str,
    captured_at: datetime,
    evidence_ids: list[str] = (),
) -> tuple[QuoteResult, NormalizedQuote]:
    status = quote_result.outcome.status
    market_id = quote_result.source.registry_id
    rate_source_id = quote_result.source.distinct_rate_source_id

    if status not in PRICED_TRIAD:
        # Terminal status: pass through byte-identical. Bounded authority —
        # derive_priced_status() is never called on this path. No coverage
        # observations were ever captured for a terminal outcome (manual_handoff,
        # blocked, callback_required never reach a coverage-disclosing page), so
        # these unknown lines are provenance="derived", not "observed" — asserting
        # "observed" here would claim market contact that never happened.
        nq = NormalizedQuote(
            market_id=market_id,
            rate_source_id=rate_source_id,
            status=status,
            comparability=Comparability.NOT_COMPARABLE,
            requested_basis_id=requested_basis_id,
            lines=[unknown_line(dim, provenance="derived") for dim in REQUESTABLE_DIMENSIONS],
            binding_basis="none",
            premium=NormalizedPremium(payment_basis="not_disclosed", term_months=basis.term_months),
            validity=NormalizedValidity(),
            discounts=[],
            confidence="low",
            normalization_warnings=[],
            captured_at=captured_at,
            evidence_ids=list(evidence_ids),
        )
        return quote_result, nq

    lines, label_warnings = map_observations_to_lines(observations)
    is_exact_quote = quote_result.outcome.is_exact_quote
    if status == Status.ESTIMATE_ONLY:
        binding_basis = "indicative_assumption"
    elif is_exact_quote:
        binding_basis = "bound_offer"
    else:
        binding_basis = "indicative_assumption"

    provisional = NormalizedQuote(
        market_id=market_id,
        rate_source_id=rate_source_id,
        status=status,
        comparability=Comparability.NOT_COMPARABLE,  # placeholder; set below
        requested_basis_id=requested_basis_id,
        lines=lines,
        binding_basis=binding_basis,
        premium=_build_premium(quote_result, basis),
        validity=_build_validity(quote_result),
        discounts=_build_discounts(quote_result),
        confidence="low",  # placeholder; set below
        normalization_warnings=label_warnings,
        captured_at=captured_at,
        evidence_ids=list(evidence_ids),
    )

    comparability, comparability_warnings = assess_comparability(provisional, basis)
    final_status = derive_priced_status(status, comparability)
    confidence = derive_confidence(comparability, distribution_type, final_status)

    final = provisional.model_copy(
        update={
            "status": final_status,
            "comparability": comparability,
            "confidence": confidence,
            "normalization_warnings": label_warnings + comparability_warnings,
        }
    )
    updated_quote_result = quote_result.model_copy(
        update={"outcome": quote_result.outcome.model_copy(update={"status": final_status})}
    )
    return updated_quote_result, final


# --- CLI -------------------------------------------------------------------------


def _load_quote_input(path: Path) -> tuple[QuoteResult, list[CoverageObservation], str, list[str]]:
    """Each --quote-result file is {"quote_result": {...}, "observations":
    [...], "distribution_type": "...", "evidence_ids": [...]} — there is no
    persisted QuoteResult store (see the approved plan), so the CLI reads a
    self-contained JSON file per market rather than looking up an id."""
    data = json.loads(path.read_text())
    quote_result = QuoteResult(**data["quote_result"])
    observations = [CoverageObservation(**o) for o in data.get("observations", [])]
    distribution_type = data.get("distribution_type", "direct")
    evidence_ids = data.get("evidence_ids", [])
    return quote_result, observations, distribution_type, evidence_ids


def _cmd_compare(args: argparse.Namespace) -> int:
    profile = intake.load_profile()
    if profile is None:
        print(f"no stored intake profile at {intake.PROFILE_PATH} — submit the intake form first", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    basis = derive_requested_basis(
        profile.coverage_benchmark,
        requested_basis_id=f"basis-{uuid4().hex[:8]}",
        captured_at=now,
    )

    quotes: list[NormalizedQuote] = []
    for raw_path in args.quote_result:
        quote_result, observations, distribution_type, evidence_ids = _load_quote_input(Path(raw_path))
        _, nq = normalize_quote(
            quote_result,
            observations,
            basis,
            distribution_type=distribution_type,
            requested_basis_id=basis.requested_basis_id,
            captured_at=now,
            evidence_ids=evidence_ids,
        )
        quotes.append(nq)

    report = build_comparison_report(quotes, basis)
    report_json = report.model_dump_json(indent=2)

    # exports/: the plain, human-facing artifact — same convention as
    # registry.export_json (not redacted; ComparisonReport carries no
    # sensitive fields, only registry ids, coverage lines and premiums).
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_path = EXPORT_DIR / f"comparison_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    export_path.write_text(report_json)

    # data/evidence/: the audit-trail copy, through the one public write
    # path. A comparison spans multiple markets, but EvidenceRecord.registry_id
    # is a single-market FK by schema — the first input is the attribution
    # point.
    evidence_dir = Path("data/evidence") / "comparisons"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / export_path.name
    safe_write_evidence(report_json, "text", evidence_path, profile=profile)
    evidence_mod.write_evidence_record(
        registry_id=quotes[0].market_id if quotes else "comparison",
        kind="document",
        timestamp=now,
        source_url_or_phone="internal:normalizer",
        artifact_path=evidence_path,
        provenance="derived",
    )

    print(f"wrote {export_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m allquote.normalize")
    sub = parser.add_subparsers(dest="command", required=True)

    compare = sub.add_parser("compare", help="normalize and compare QuoteResult inputs")
    compare.add_argument("--quote-result", action="append", required=True, help="path to a quote-input JSON file")
    compare.set_defaults(func=_cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
