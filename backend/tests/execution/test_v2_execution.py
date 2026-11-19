import time
import pytest
from eth_account import Account
from web3 import Web3

from treasury_backend.modules.execution.models import TransactionProposal, BuiltTransaction, SimulationEvidence, ExecutionRequest
from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.execution.simulation.runner import Simulator, rpc
from conftest import proposal
from v2_setup import activate
from treasury_contracts.proof import PGSProofEngine
from treasury_contracts.v2 import (
    Registry,
    ProofPolicy,
    SessionContext,
    OracleEvidence,
    Price,
    DomainV2,
    SignedPDRV2,
    approval_v2,
    message_v2,
    digest_v2,
    PreflightV2Request,
)


@pytest.mark.parametrize(
    ("reverse", "strict_stress"), [(False, False), (True, False), (False, True)]
)
def test_v2_guarded_simulation_proof_relayer_and_counters(plane, tmp_path, reverse, strict_stress):
    client, chain, keys, app = plane
    activate(chain, keys, tmp_path, {"tolerance_bps": 0} if strict_stress else None)
    c = chain.context()
    args = (
        {
            "token_in": chain.wavax.address,
            "token_out": chain.usdc.address,
            "amount_in_base_units": str(10**18),
        }
        if reverse
        else {}
    )
    b = BuiltTransaction.model_validate(
        app.state.builder.build(TransactionProposal.model_validate(proposal(chain, **args)))
    )
    sim = SimulationEvidence.model_validate(
        Simulator(chain, app.state.store).simulate(b.build_id, b.policy_hash)
    )
    assert sim.verification_status == "COMPLETE", sim
    assert sim.effects_v2 is not None
    registry = Registry.model_validate(c["registry"])
    policy = ProofPolicy.model_validate(c["proof_policy"])
    session = SessionContext.model_validate(c["proof_session"])
    oracle = OracleEvidence(
        chain_id=31337,
        vault=b.vault_address,
        source_hash=policy.oracle_source_hash,
        timestamp=c["timestamp"],
        block_number=c["block_number"],
        block_hash=c["block_hash"],
        prices=tuple(
            Price(
                asset=a.address,
                nominal_usd_e8=str(p),
                low_usd_e8=str(p * 99 // 100),
                high_usd_e8=str(p * 101 // 100),
            )
            for a in registry.assets
            for p in [10**8 if a.decimals == 6 else 20 * 10**8]
        ),
    )
    proof = PGSProofEngine().prove(
        b, sim.effects_v2, policy, registry, oracle, session, int(time.time())
    )
    assert proof.status == "VERIFIED", proof
    if strict_stress:
        before = chain.balances()
        request = PreflightV2Request(
            build_id=b.build_id, proof=proof, session_id=session.session_id
        )
        with pytest.raises(PlaneError) as error:
            app.state.simulator.preflight_v2(request)
        assert error.value.code == "REQUIRED_STRESS_NOT_SATISFIED"
        assert (
            chain.balances() == before and not chain.vault.functions.usedNonce(int(b.nonce)).call()
        )
        return
    a = approval_v2(b, sim.evidence_root, proof, session.session_id)
    d = DomainV2(chainId=31337, verifyingContract=b.vault_address)
    signature = Account.sign_message(message_v2(d, a), keys["attestor"]).signature
    signed = SignedPDRV2(
        decision_id="TEST_ONLY_decision",
        build_id=b.build_id,
        domain=d,
        approval=a,
        phi=proof.phi,
        signature=Web3.to_hex(signature),
        typed_data_hash=digest_v2(d, a),
    )
    prior = rpc(chain.w3, "evm_snapshot", [])
    result = app.state.relayer.execute(ExecutionRequest(build_id=b.build_id, signed_pdr=signed))
    chain.w3.eth.wait_for_transaction_receipt(result["tx_hash"])
    receipt = app.state.relayer.monitor(result["tx_hash"])
    assert receipt["status"] == "CONFIRMED" and receipt["revert_reason"] is None, receipt
    assert int(receipt["proof_session"]["used_usd_e8"]) == int(proof.risk_debit_usd_e8)
    assert chain.vault.functions.usedNonce(int(b.nonce)).call()
    assert chain.snapshot()["daily_spent_usdc_base_units"] == (
        "0" if reverse else b.amount_in_base_units
    )
    report = app.state.relayer.reconciliation(result["tx_hash"])
    assert report["verification_status"] == "VERIFIED", report
    assert report["gas_verified"] and report["nonce_used"]
    assert report["token_in_delta_base_units"] == f"-{b.amount_in_base_units}"
    assert report["token_out_delta_base_units"] == receipt["actual_token_out_delta_base_units"]
    original_settings = chain.settings
    chain.settings = original_settings.model_copy(update={"required_confirmations": report["confirmations"] + 1})
    try:
        waiting = app.state.relayer.reconciliation(result["tx_hash"])
        assert waiting["verification_status"] == "PENDING"
        assert waiting["reason_codes"] == ["INSUFFICIENT_CONFIRMATIONS"]
        rpc(chain.w3, "evm_mine", [])
        assert app.state.relayer.reconciliation(result["tx_hash"])["verification_status"] == "VERIFIED"
    finally:
        chain.settings = original_settings
    # Receipt is no longer canonical after a real local-chain rollback.
    assert rpc(chain.w3, "evm_revert", [prior])
    assert app.state.relayer.monitor(result["tx_hash"])["status"] == "PENDING"
    assert app.state.relayer.reconciliation(result["tx_hash"])["verification_status"] == "PENDING"
    assert not chain.vault.functions.usedNonce(int(b.nonce)).call()
