import json
import runpy
from pathlib import Path

import pytest
from eth_keys import keys

from app.attestor import Attestor
from app.domain import EconomicRiskAssessment
from app.errors import ControlError
from app.models import Alignment, ChainContext, Mandate
from app.sde import decide
from app.storage import Store
from treasury_contracts.models import Baseline, SimulationEvidence, StressTest
from treasury_contracts.proof import PGSProofEngine
from treasury_contracts.v2 import keccak

ROOT = Path(__file__).resolve().parents[3]
make_case = runpy.run_path(str(ROOT / "tests/integration/test_proof_v2.py"))["case"]


def inputs():
    b, e, p, r, o, s, now = make_case()
    proof = PGSProofEngine().prove(b, e, p, r, o, s, now)
    data = json.loads((ROOT / "fixtures/mock/mandate.json").read_text())
    owner = "0x" + "55" * 20
    m = Mandate.model_validate(
        data
        | dict(
            chain_id=31337,
            vault_address=b.vault_address,
            owner=owner,
            router=b.router,
            token_in=b.token_in,
            token_out=b.token_out,
            policy_hash=b.policy_hash,
            expires_at=now + 600,
            proof_policy=p.model_dump(mode="json"),
            registry=r.model_dump(mode="json"),
            session_id=s.session_id,
        )
    )
    c = ChainContext(
        deployment="LOCAL",
        chain_id=31337,
        vault_address=b.vault_address,
        owner=owner,
        router=b.router,
        token_in=b.token_in,
        token_out=b.token_out,
        token_in_decimals=6,
        token_out_decimals=18,
        policy_hash=b.policy_hash,
        policy_version=1,
        policy_expires_at=now + 600,
        paused=False,
        attestor="0x" + "66" * 20,
        relayer="0x" + "77" * 20,
        block_number=10,
        block_timestamp=now,
        bytecode_hash=keccak(b"code"),
        nonce_used=False,
        max_usdc_per_swap_base_units=m.max_usdc_per_swap_base_units,
        max_usdc_spend_per_day_base_units=m.max_usdc_spend_per_day_base_units,
        proof_policy=p,
        registry=r,
        proof_session=s,
    )
    sim = SimulationEvidence(
        effects_v2=e,
        intent_id=b.intent_id,
        build_id=b.build_id,
        chain_id=b.chain_id,
        vault_address=b.vault_address,
        policy_hash=b.policy_hash,
        calldata_hash=b.calldata_hash,
        nonce=b.nonce,
        deadline=b.deadline,
        fork_block=10,
        bytecode_hash=c.bytecode_hash,
        simulation_mode="LOCAL_TEST_ATTESTOR",
        baseline=Baseline(
            execution_status="SUCCESS",
            token_in_delta_base_units="-100000000",
            token_out_delta_base_units=str(5 * 10**18),
            unexpected_transfer=False,
            unauthorized_approval=False,
            gas_used="200000",
        ),
        stress_tests=[
            StressTest(
                scenario_id=name,
                status="SUCCESS_SAFE",
                scenario_hash=keccak(name.encode()),
                output_base_units=str(5 * 10**18),
            )
            for name in m.required_stress
        ],
        verification_status="COMPLETE",
        source="REAL_LOCAL_SIM",
        artifact_refs=[],
        evidence_manifest_ref="TEST_ONLY",
        evidence_root=e.hash,
    )
    from treasury_contracts.models import TransactionProposal

    proposal = TransactionProposal(
        intent_id=b.intent_id,
        mandate_id=m.mandate_id,
        mandate_version=m.version,
        action="SWAP_EXACT_INPUT",
        chain_id=b.chain_id,
        vault_address=b.vault_address,
        router=b.router,
        token_in=b.token_in,
        token_out=b.token_out,
        amount_in_base_units=b.amount_in_base_units,
        slippage_bps=40,
        recipient=b.vault_address,
        deadline=b.deadline,
        user_goal_reason="TEST_ONLY",
    )
    aligned = Alignment(verdict="ALIGNED", reason_codes=[], evidence_refs=[])
    risk = EconomicRiskAssessment(
        intent_id=b.intent_id,
        build_id=b.build_id,
        snapshot_id="TEST_ONLY_snapshot",
        result="PASS",
        projected_wavax_exposure_bps=1000,
        max_wavax_exposure_bps=2500,
        violations=[],
    )
    return b, m, c, sim, proposal, aligned, risk, proof, now


@pytest.mark.parametrize(
    "failure", ["missing", "sat", "unknown", "call", "registry", "exposure", "stale", "alignment"]
)
def test_sde_refuses_without_all_proof_and_v1_gates(failure):
    b, m, c, sim, proposal, aligned, risk, p, now = inputs()
    if failure == "missing":
        p = None
    if failure == "sat":
        p = p.model_copy(update={"status": "VIOLATED", "check_mode": "SAT"})
    if failure == "unknown":
        p = p.model_copy(update={"status": "INCONCLUSIVE", "compile_mode": "UNKNOWN"})
    if failure == "call":
        b = b.model_copy(update={"nonce": "2"})
    if failure == "registry":
        p = p.model_copy(update={"registry_hash": keccak(b"other")})
    if failure == "exposure":
        risk = risk.model_copy(update={"result": "FAIL", "violations": ["TOKEN_EXPOSURE_LIMIT"]})
    if failure == "stale":
        now += 61
    if failure == "alignment":
        aligned = aligned.model_copy(update={"verdict": "MISALIGNED"})
    d = decide(m, proposal, aligned, c, now, built=b, evidence=sim, risk=risk, proof=p)
    assert d.verdict != "APPROVE"


@pytest.mark.parametrize(
    "mutation", ["valid", "proof", "solver", "evidence", "phi", "missing", "session", "call"]
)
def test_attestor_revalidates_bound_proof_before_signing(tmp_path, mutation):
    b, m, c, sim, proposal, aligned, risk, p, now = inputs()
    d = decide(m, proposal, aligned, c, now, built=b, evidence=sim, risk=risk, proof=p)
    assert d.verdict == "APPROVE"
    store = Store(tmp_path / "state.sqlite3")
    store.start("wf", {})
    store.record("wf", "APPROVED", d, {"mandate": m.model_dump()}, 0, {})
    attestor = Attestor(store, keys.PrivateKey((0x1234).to_bytes(32, "big")), lambda: now)
    if mutation == "proof":
        p = p.model_copy(update={"status": "VIOLATED"})
    if mutation == "solver":
        p = p.model_copy(update={"solver_version": "tampered"})
    if mutation == "evidence":
        p = p.model_copy(update={"evidence_root": keccak(b"other")})
    if mutation == "phi":
        p = p.model_copy(update={"phi": None})
    if mutation == "session":
        c = c.model_copy(
            update={
                "proof_session": c.proof_session.model_copy(update={"session_id": keccak(b"other")})
            }
        )
    if mutation == "call":
        b = b.model_copy(update={"nonce": "2"})

    def verify():
        return (p, c.proof_session) if mutation != "missing" else None

    if mutation == "valid":
        signed = attestor.attest(d.decision_id, "wf", d, b, "TEST_ONLY_scope", verify)
        assert signed.domain.version == "2" and signed.approval.proofContextHash == p.context_hash
    else:
        with pytest.raises(ControlError):
            attestor.attest(d.decision_id, "wf", d, b, "TEST_ONLY_scope", verify)
        with store.connection() as conn:
            assert conn.execute("SELECT count(*) FROM attestations").fetchone()[0] == 0


def test_idempotent_additive_database_migration(tmp_path):
    path = tmp_path / "old.sqlite3"
    a = Store(path)
    a.start("old", {"mode": "MOCK"})
    b = Store(path)
    assert b.workflow("old")["mode"] == "MOCK"
    with b.connection() as conn:
        assert conn.execute("SELECT count(*) FROM proof_artifacts").fetchone()[0] == 0


def test_configured_block_drift_does_not_bypass_temporal_expiry():
    b, m, c, sim, proposal, aligned, risk, proof, now = inputs()
    c = c.model_copy(update={"block_number": sim.fork_block + 20})
    assert (
        decide(m, proposal, aligned, c, now, built=b, evidence=sim, risk=risk, proof=proof).verdict
        != "APPROVE"
    )
    c = c.model_copy(update={"max_block_drift": 30})
    assert (
        decide(m, proposal, aligned, c, now, built=b, evidence=sim, risk=risk, proof=proof).verdict
        == "APPROVE"
    )
    assert (
        decide(
            m, proposal, aligned, c, now + 61, built=b, evidence=sim, risk=risk, proof=proof
        ).verdict
        != "APPROVE"
    )
