import ast
import json
from pathlib import Path

from allquote import planner, registry
from allquote.schemas import MarketRecord, Status
from tests.fixtures import build_market_record

FORBIDDEN_IMPORT_ROOTS = {
    "browser_use",
    "playwright",
    "httpx",
    "requests",
    "urllib",
    "anthropic",
    "socket",
}


def _planner_source() -> str:
    return Path(planner.__file__).read_text()


def test_no_llm_or_network_call_reachable_from_planner():
    tree = ast.parse(_planner_source())
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS), imported_roots


# --- plan_routes over the real seed registry ------------------------------


def _real_registry_records() -> list[MarketRecord]:
    raw = json.loads(Path("data/seed_registry.json").read_text())
    records = [MarketRecord.model_validate(row) for row in raw]
    return registry.assign_distinct_rate_source_ids(records)


def test_every_distinct_source_lands_in_exactly_one_lane():
    records = _real_registry_records()
    distinct_ids = {r.distinct_rate_source_id for r in records}

    planned = planner.plan_routes(records)

    assert len(planned) == len(distinct_ids) == 79
    assert {p.distinct_rate_source_id for p in planned} == distinct_ids
    assert all(p.lane in ("contact", "derived") for p in planned)
    # exactly one PlannedRoute per distinct source
    assert len({p.distinct_rate_source_id for p in planned}) == len(planned)


def test_suppressed_registry_ids_cover_the_non_primary_rows():
    records = _real_registry_records()
    planned = planner.plan_routes(records)

    total_queued = len(planned)
    total_suppressed = sum(len(p.suppressed_registry_ids) for p in planned)
    assert total_queued + total_suppressed == len(records)

    # every registry_id appears exactly once across (primary + suppressed)
    seen = [p.registry_id for p in planned]
    for p in planned:
        seen.extend(p.suppressed_registry_ids)
    assert len(seen) == len(records)
    assert set(seen) == {r.registry_id for r in records}


def test_tier2_demo_critical_routes_classified_correctly():
    records = _real_registry_records()
    planned = {p.registry_id: p for p in planner.plan_routes(records)}

    for registry_id in planner.DEMO_CRITICAL_REGISTRY_IDS:
        assert planned[registry_id].lane == "contact"
        assert planned[registry_id].tier == 2
        assert planned[registry_id].model_tier == "smart"


def test_derived_rule_table_exhaustive_or_unresolved():
    records = _real_registry_records()
    by_registry_id = {r.registry_id: r for r in records}
    derived_registry_ids = {
        p.registry_id for p in planner.plan_routes(records) if p.lane == "derived"
    }
    derived = [by_registry_id[registry_id] for registry_id in derived_registry_ids]
    assert derived  # sanity: the real registry does have derived-lane rows

    for record in derived:
        outcome = planner.resolve_derived_outcome(record)
        assert isinstance(outcome.status, Status)
        assert outcome.reason
        assert outcome.cited_fields


# --- tier ordering ---------------------------------------------------------


def test_tier_ordering_derived_then_1_then_2_then_3():
    tier1 = build_market_record(
        registry_id="r-tier1", distinct_rate_source_id="src-tier1",
        distribution_type="direct", product_scope="standard_PPA", quote_url="https://x/1",
    )
    tier2 = build_market_record(
        registry_id="route-sonnet", distinct_rate_source_id="src-tier2",
        distribution_type="direct", product_scope="standard_PPA", quote_url="https://x/2",
    )
    tier3 = build_market_record(
        registry_id="r-tier3", distinct_rate_source_id="src-tier3",
        distribution_type="broker", product_scope="unknown", quote_url="https://x/3",
    )
    derived = build_market_record(
        registry_id="r-derived", distinct_rate_source_id="src-derived",
        quote_url=None, requirements=["human"],
    )

    planned = planner.plan_routes([tier3, tier2, derived, tier1])

    lanes_tiers = [(p.lane, p.tier) for p in planned]
    assert lanes_tiers == [
        ("derived", None),
        ("contact", 1),
        ("contact", 2),
        ("contact", 3),
    ]


def test_infer_estimate_capable_heuristic():
    direct_standard = build_market_record(
        distribution_type="direct", product_scope="standard_PPA", quote_url="https://x/1"
    )
    assert planner.infer_estimate_capable(direct_standard) is True

    broker_unknown = build_market_record(
        distribution_type="broker", product_scope="unknown", quote_url="https://x/2"
    )
    assert planner.infer_estimate_capable(broker_unknown) is False

    no_url = build_market_record(
        distribution_type="direct", product_scope="standard_PPA", quote_url=None
    )
    assert planner.infer_estimate_capable(no_url) is False

    collector = build_market_record(
        distribution_type="MGA_program", product_scope="collector", quote_url="https://x/3"
    )
    assert planner.infer_estimate_capable(collector) is False


# --- _select_primary tiebreak, exercised through plan_routes --------------


def test_primary_selection_prefers_quote_url_over_prefix():
    seed_row = build_market_record(
        registry_id="seed-x", distinct_rate_source_id="src-shared",
        quote_url=None, requirements=[],
    )
    route_row = build_market_record(
        registry_id="route-x", distinct_rate_source_id="src-shared",
        quote_url="https://x/quote", distribution_type="direct", product_scope="standard_PPA",
    )
    planned = planner.plan_routes([seed_row, route_row])
    assert len(planned) == 1
    assert planned[0].registry_id == "route-x"
    assert planned[0].suppressed_registry_ids == ("seed-x",)


def test_primary_selection_prefers_route_over_panel_over_seed_when_no_quote_url():
    seed_row = build_market_record(
        registry_id="seed-x", distinct_rate_source_id="src-shared", quote_url=None, requirements=[]
    )
    panel_row = build_market_record(
        registry_id="panel-x", distinct_rate_source_id="src-shared", quote_url=None, requirements=[]
    )
    route_row = build_market_record(
        registry_id="route-x", distinct_rate_source_id="src-shared", quote_url=None,
        requirements=["human"],
    )
    planned = planner.plan_routes([seed_row, panel_row, route_row])
    assert planned[0].registry_id == "route-x"
    assert set(planned[0].suppressed_registry_ids) == {"seed-x", "panel-x"}


# --- resolve_derived_outcome: positive-value-only rule table --------------


def test_rule_membership_requires_positive_requirement():
    record = build_market_record(quote_url=None, requirements=["membership"])
    outcome = planner.resolve_derived_outcome(record)
    assert outcome.status == Status.AFFINITY_RESTRICTED


def test_rule_specialty_only_fires_on_known_nonstandard_scope_not_unknown():
    unknown_scope = build_market_record(quote_url=None, product_scope="unknown", requirements=[])
    assert planner.resolve_derived_outcome(unknown_scope).status != Status.SPECIALTY_ONLY

    nonstandard = build_market_record(
        quote_url=None, product_scope="nonstandard_PPA", requirements=[]
    )
    assert planner.resolve_derived_outcome(nonstandard).status == Status.SPECIALTY_ONLY


def test_rule_residual_distribution_is_manual_handoff():
    record = build_market_record(quote_url=None, distribution_type="residual", requirements=[])
    assert planner.resolve_derived_outcome(record).status == Status.MANUAL_HANDOFF


def test_rule_human_or_licensed_intermediary_is_manual_handoff():
    human = build_market_record(quote_url=None, requirements=["human"])
    assert planner.resolve_derived_outcome(human).status == Status.MANUAL_HANDOFF

    intermediary = build_market_record(
        quote_url=None, requirements=[], licensed_intermediary="Some Brokerage"
    )
    assert planner.resolve_derived_outcome(intermediary).status == Status.MANUAL_HANDOFF


def test_rule_phone_route_present_is_callback_required():
    record = build_market_record(
        quote_url=None, requirements=[], public_phone_route="1-800-555-0100"
    )
    assert planner.resolve_derived_outcome(record).status == Status.CALLBACK_REQUIRED


def test_no_matching_rule_falls_through_to_unresolved_not_manual_handoff():
    """The rule-6 fix: an unpopulated public_phone_route is not evidence
    that no phone route exists. Absence of a field must never resolve to a
    specific claim like manual_handoff."""
    bare_row = build_market_record(
        quote_url=None,
        requirements=[],
        public_phone_route=None,
        licensed_intermediary=None,
        distribution_type="direct",
        product_scope="standard_PPA",
    )
    outcome = planner.resolve_derived_outcome(bare_row)
    assert outcome.status == Status.UNRESOLVED


def test_not_currently_writing_status_is_preserved():
    record = build_market_record(quote_url=None, requirements=[], status=Status.NOT_CURRENTLY_WRITING)
    outcome = planner.resolve_derived_outcome(record)
    assert outcome.status == Status.NOT_CURRENTLY_WRITING
