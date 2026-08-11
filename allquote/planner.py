"""Route planner. See PLAN.md Task 7 / the approved Phase 1 plan.

Pure functions over `MarketRecord` rows only: no I/O beyond the records the
caller passes in, no LLM calls, no network calls. All I/O (evidence writes,
QuoteResult persistence, executor invocation) belongs to the Phase 3 batch
runner, not here.

Unit of work is the DISTINCT rate source (79), not the registry row (111):
several registry rows can share one `distinct_rate_source_id` (e.g. a
hand-curated `route-*` row and its raw `seed-*` Appendix A counterpart, or
several aggregator `panel-*` disclosures naming the same underwriter).
BRIEF.md's market_completion and comparable_quote_yield metrics divide by
distinct rate sources, so planning one route per distinct source keeps the
queue population and the metric denominator the same set. The non-primary
rows in a group are deliberately left untouched in the registry — Task 8b's
dedupe resolver is what formally assigns `duplicate_rate_source` to them,
once real QuoteResults exist to resolve against.
"""

from dataclasses import dataclass
from typing import Literal

from allquote.schemas import MarketRecord, Status

Lane = Literal["contact", "derived"]
ModelTier = Literal["smart", "cheap", "none"]

# The 4 routes already verified (registry.verify() stamped last_verified_at)
# ahead of this task, and the ones the Loom walkthrough will show.
DEMO_CRITICAL_REGISTRY_IDS = frozenset(
    {"route-sonnet", "route-belairdirect", "route-caa-insurance", "route-td-insurance"}
)

# Scopes we have positive evidence are not standard PPA. "unknown" is
# deliberately excluded: it means not-yet-verified, not "verified
# non-standard" — see resolve_derived_outcome's rule 2.
KNOWN_NONSTANDARD_SCOPES = frozenset(
    {"nonstandard_PPA", "high_net_worth", "collector", "commercial_specialty"}
)


def infer_estimate_capable(record: MarketRecord) -> bool:
    """HEURISTIC, not evidence — affects run order only, never a safety
    decision. Approximates "gives an indicative price without an
    identity/database lookup" from distribution_type + product_scope +
    quote_url presence.

    The registry's `requirements` field cannot answer this: "licence" in
    requirements means the form asks for a licence number, which is not the
    same fact as "the site performs a live identity/MTO lookup before
    showing a price" (docs/GUARDRAILS.md's identity-checkpoint is a
    specific, different trigger). Distinguishing them requires browsing a
    live page, which Phase 1 planning does not do. gates.py remains the
    sole authority on what a route actually does at execution time — a
    wrong guess here costs priority, never safety.
    """
    return (
        record.quote_url is not None
        and record.distribution_type in ("direct", "agent")
        and record.product_scope == "standard_PPA"
    )


@dataclass(frozen=True)
class PlannedRoute:
    distinct_rate_source_id: str
    registry_id: str
    # Other registry rows sharing this distinct_rate_source_id, deliberately
    # not queued. Recorded (not just decided in memory) so a run report can
    # show these were suppressed as known duplicates, not missed, and so
    # Task 8b's dedupe resolver knows what was already attempted under this id.
    suppressed_registry_ids: tuple[str, ...]
    lane: Lane
    tier: int | None  # 1, 2, or 3 for lane="contact"; None for lane="derived"
    model_tier: ModelTier


@dataclass(frozen=True)
class DerivedOutcome:
    status: Status
    reason: str
    cited_fields: dict[str, object]


def _select_primary(rows: list[MarketRecord]) -> tuple[MarketRecord, list[MarketRecord]]:
    """Within one distinct_rate_source_id group, pick the representative
    row: quote_url present > "route-" prefix > "panel-" prefix > "seed-"
    prefix > lexicographic registry_id, as tiebreak. `route-*` rows are
    hand-curated with real requirements/automation_notes; `seed-*` rows are
    the raw Appendix A dump with mostly empty fields — preferring the more
    specific row gives resolve_derived_outcome() better evidence to cite.
    """

    def rank(r: MarketRecord) -> int:
        if r.quote_url:
            return 0
        if r.registry_id.startswith("route-"):
            return 1
        if r.registry_id.startswith("panel-"):
            return 2
        return 3

    ordered = sorted(rows, key=lambda r: (rank(r), r.registry_id))
    return ordered[0], ordered[1:]


def _classify(record: MarketRecord) -> tuple[Lane, int | None, ModelTier]:
    if record.quote_url is None:
        return "derived", None, "none"
    if record.registry_id in DEMO_CRITICAL_REGISTRY_IDS:
        return "contact", 2, "smart"
    if infer_estimate_capable(record):
        return "contact", 1, "smart"
    return "contact", 3, "cheap"


def plan_routes(records: list[MarketRecord]) -> list[PlannedRoute]:
    """Groups `records` by distinct_rate_source_id, selects one
    representative row per group, classifies it into a lane/tier/model
    tier, and orders the result: derived-lane first (zero-cost, no browser,
    banks evidence-backed terminal statuses immediately), then contact-lane
    tier 1, tier 2, tier 3 — front-loaded so an interrupted batch still has
    the outcomes the acceptance gates need. Each bucket is sorted by
    distinct_rate_source_id for a deterministic, reproducible queue.
    """
    groups: dict[str, list[MarketRecord]] = {}
    for record in records:
        assert record.distinct_rate_source_id is not None, (
            f"{record.registry_id} has no distinct_rate_source_id — "
            "registry.assign_distinct_rate_source_ids() should have set one at seed time"
        )
        groups.setdefault(record.distinct_rate_source_id, []).append(record)

    planned: list[PlannedRoute] = []
    for distinct_id, rows in groups.items():
        primary, others = _select_primary(rows)
        lane, tier, model_tier = _classify(primary)
        planned.append(
            PlannedRoute(
                distinct_rate_source_id=distinct_id,
                registry_id=primary.registry_id,
                suppressed_registry_ids=tuple(sorted(r.registry_id for r in others)),
                lane=lane,
                tier=tier,
                model_tier=model_tier,
            )
        )

    def sort_key(p: PlannedRoute) -> tuple[int, str]:
        # derived (bucket 0) before contact tier 1/2/3 (buckets 1/2/3)
        bucket = 0 if p.lane == "derived" else p.tier
        return (bucket, p.distinct_rate_source_id)

    return sorted(planned, key=sort_key)


# --- derived-lane outcome resolution (P2) ---------------------------------
#
# Every rule fires on a POSITIVE, known registry fact — never on the
# absence or negation of one. A missing/unresearched field is not evidence
# that a channel or requirement does not exist; it stays `unresolved`.
# Rules are evaluated top to bottom; the first match wins.


def resolve_derived_outcome(record: MarketRecord) -> DerivedOutcome:
    """Pure rule-table resolution for a derived-lane row (no quote_url).
    Never contacts anything. Returns the status this row should carry plus
    the specific fields the conclusion rests on, for the caller (Phase 3
    batch runner) to write as a real EvidenceRecord with provenance="derived".
    """
    if record.status == Status.NOT_CURRENTLY_WRITING:
        return DerivedOutcome(
            status=Status.NOT_CURRENTLY_WRITING,
            reason="registry status was already recorded as not_currently_writing",
            cited_fields={"status": record.status.value},
        )

    if "membership" in record.requirements:
        return DerivedOutcome(
            status=Status.AFFINITY_RESTRICTED,
            reason=(
                "registry requirements include 'membership' and the intake profile "
                "carries no membership field to satisfy it"
            ),
            cited_fields={"requirements": list(record.requirements)},
        )

    if record.product_scope in KNOWN_NONSTANDARD_SCOPES:
        return DerivedOutcome(
            status=Status.SPECIALTY_ONLY,
            reason=f"registry product_scope is verified non-standard: {record.product_scope}",
            cited_fields={"product_scope": record.product_scope},
        )

    if record.distribution_type == "residual":
        return DerivedOutcome(
            status=Status.MANUAL_HANDOFF,
            reason="registry distribution_type is residual — accessed only via licensed intermediary",
            cited_fields={"distribution_type": record.distribution_type},
        )

    if "human" in record.requirements or record.licensed_intermediary is not None:
        return DerivedOutcome(
            status=Status.MANUAL_HANDOFF,
            reason=(
                "registry requirements include 'human' or a licensed_intermediary is named on file"
            ),
            cited_fields={
                "requirements": list(record.requirements),
                "licensed_intermediary": record.licensed_intermediary,
            },
        )

    if record.public_phone_route:
        # Currently unreachable: public_phone_route is unpopulated across
        # the entire registry as of this task. Left in place, not deleted,
        # because it becomes live the moment Task 9 research populates real
        # phone routes — do not remove this as "dead code."
        return DerivedOutcome(
            status=Status.CALLBACK_REQUIRED,
            reason=f"registry lists a public phone route: {record.public_phone_route}",
            cited_fields={"public_phone_route": record.public_phone_route},
        )

    return DerivedOutcome(
        status=Status.UNRESOLVED,
        reason=(
            "no positively-verified channel: quote_url is absent and public_phone_route "
            "has never been researched for this row (the field is unpopulated across the "
            "whole registry, a known gap in registry research — not evidence that no phone "
            "route exists for this market)"
        ),
        cited_fields={
            "quote_url": record.quote_url,
            "public_phone_route": record.public_phone_route,
            "requirements": list(record.requirements),
            "product_scope": record.product_scope,
            "distribution_type": record.distribution_type,
        },
    )
