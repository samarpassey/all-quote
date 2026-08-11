from pathlib import Path

from allquote import batch, results_store
from allquote.schemas import Status
from tests.fixtures import build_market_record, build_vaulted_profile


def _records() -> list:
    return [
        # derived lane
        build_market_record(
            registry_id="d-1", distinct_rate_source_id="src-d-1",
            quote_url=None, requirements=["human"],
        ),
        # contact lane: will raise inside the injected contact_runner (B4)
        build_market_record(
            registry_id="c-fail", distinct_rate_source_id="src-c-fail",
            quote_url="https://example.invalid/fail", distribution_type="direct",
            product_scope="standard_PPA",
        ),
        # contact lane: succeeds
        build_market_record(
            registry_id="c-ok", distinct_rate_source_id="src-c-ok",
            quote_url="https://example.invalid/ok", distribution_type="broker",
            product_scope="unknown",
        ),
    ]


def _ok_quote_result_dict(registry_id: str) -> dict:
    return {
        "market_id": registry_id,
        "quote_result": {
            "source": {
                "registry_id": registry_id, "brand_or_program": "TestBrand",
                "legal_underwriter": "Test Underwriter Co.", "insurer_group": "Test Group",
                "licensed_intermediary": None, "distinct_rate_source_id": f"src-{registry_id}",
            },
            "outcome": {"status": "blocked", "is_exact_quote": False, "failure_reason": "captcha", "next_action": None},
            "coverage": {"requested": {}, "returned": {}, "variance_from_benchmark": []},
            "discounts": {"applied": [], "available_not_selected": [], "conditional": []},
            "validity": {"quote_reference_id": None, "effective_date": None, "expiry_date": None, "verification_may_change_premium": True},
            "evidence": {
                "timestamp": "2026-08-12T00:00:00Z", "source_url_or_phone": "https://example.invalid/ok",
                "evidence_artifact": "data/evidence/test/ok.png", "evidence_hash": "a" * 64,
            },
            "confidence": "low",
            "privacy": {"fields_disclosed": [], "consent_receipt_id": None, "retention_deadline": None},
            "price": None,
        },
    }


def test_one_failing_contact_route_never_aborts_the_batch(tmp_path):
    vault_path = tmp_path / "vault.enc"
    profile, _ = build_vaulted_profile(vault_path, "test-vault-key-not-real")

    def fake_contact_runner(market_id: str, model: str) -> dict:
        if market_id == "c-fail":
            raise RuntimeError("simulated subprocess spawn failure")
        return {
            "market_id": market_id, "killed": False, "returncode": 0,
            "quote_result": _ok_quote_result_dict(market_id)["quote_result"],
        }

    run_id = batch.run_batch(
        records=_records(),
        profile=profile,
        contact_runner=fake_contact_runner,
        evidence_root=tmp_path / "evidence",
        vault_path=vault_path,
        vault_key="test-vault-key-not-real",
        runs_root=tmp_path / "runs",
    )

    results = {r["distinct_rate_source_id"]: r for r in results_store.list_results(run_id, runs_root=tmp_path / "runs")}

    assert set(results) == {"src-d-1", "src-c-fail", "src-c-ok"}

    # the failing route produced a real, evidence-backed unreachable result —
    # not a batch crash and not a silently dropped route.
    failed = results["src-c-fail"]
    assert failed["quote_result"]["outcome"]["status"] == Status.UNREACHABLE.value
    assert "simulated subprocess spawn failure" in failed["quote_result"]["outcome"]["failure_reason"]
    assert failed["quote_result"]["evidence"]["evidence_artifact"]
    assert Path(failed["quote_result"]["evidence"]["evidence_artifact"]).exists()

    # the other two routes were unaffected by the failure.
    assert results["src-d-1"]["origin"] == "derived"
    assert results["src-c-ok"]["quote_result"]["outcome"]["status"] == "blocked"

    # every result normalized through the real normalize_quote path.
    for r in results.values():
        assert r["normalized_quote"]["market_id"]


def test_derived_route_writes_real_evidence_with_derived_provenance(tmp_path):
    vault_path = tmp_path / "vault.enc"
    profile, _ = build_vaulted_profile(vault_path, "test-vault-key-not-real")
    record = build_market_record(
        registry_id="d-1", distinct_rate_source_id="src-d-1", quote_url=None, requirements=["human"],
    )
    from allquote.normalize_basis import derive_requested_basis
    from datetime import datetime, timezone

    basis = derive_requested_basis(profile.coverage_benchmark, requested_basis_id="basis-test", captured_at=datetime.now(timezone.utc))

    qr, nq = batch.run_derived_route(
        record, profile=profile, run_id="test-run", basis=basis,
        evidence_root=tmp_path / "evidence", vault_path=vault_path, vault_key="test-vault-key-not-real",
    )

    assert qr.outcome.status == Status.MANUAL_HANDOFF  # "human" in requirements
    assert Path(qr.evidence.evidence_artifact).exists()
    assert nq.status == Status.MANUAL_HANDOFF
    assert all(line.provenance == "derived" for line in nq.lines)
