"""Complete MVP workflow regressions: real local EVM and PGS, scripted semantic provider."""

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from eth_keys import keys
from test_v3_execution import execute, intent, prepare
from v3_provider import ProtocolFixture

from treasury_backend.modules.alignment.engine import TaskShield
from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.modules.persistence import Store
from treasury_backend.modules.signing.service import Attestor
from treasury_backend.modules.temporal.service import TemporalService
from treasury_backend.modules.workflows.autonomy import AutonomousTreasury
from treasury_backend.modules.workflows.treasury import TreasuryWorkflows
from treasury_backend.operations.execution import send
from treasury_contracts.proof_v3 import prove_operation


@pytest.fixture
def workflows(mvp, tmp_path):
    def clock():
        return int(time.time())

    store = Store(tmp_path / "mvp-control.sqlite3")
    shield = TaskShield(
        store,
        ShieldConfig(mode="wallet_pipeline", context_chars=100000, max_calls=300),
        ProtocolFixture(),
        clock,
    )
    control = SimpleNamespace(
        store=store,
        shield=shield,
        clock=clock,
        temporal=TemporalService(store, shield, "LOCAL", clock),
        attestor=Attestor(store, keys.PrivateKey(mvp["attestor"].key), clock),
    )
    yield TreasuryWorkflows(control, mvp["execution"])
    shield.close()


def test_mvp_both_swap_directions_and_receipt_payment(mvp, workflows):
    forward = workflows.run(intent(mvp), "forward")
    assert forward["status"] == "CONFIRMED", forward.get("reason_code")
    reverse = workflows.run(
        intent(
            mvp, amount=str(10**18), token_in=mvp["manifest"].wavax, token_out=mvp["manifest"].usdc
        ),
        "reverse",
    )
    assert reverse["status"] == "CONFIRMED", reverse.get("reason_code")
    payment = workflows.run(intent(mvp, "TOKEN_PAYMENT", "1000000"), "payment")
    assert payment["status"] == "CONFIRMED", payment.get("reason_code")
    proof = next(e["evidence"] for e in payment["timeline"] if e["stage"] == "PROOF")
    assert proof["risk_debit_usd_e8"] == "0"
    assert proof["phi"]["receipt_credit"] == "1000000"
    assert payment["outcome"]["payee_received"] == "1000000"
    assert payment["outcome"]["system_gas_expense"]["payer"] == "SYSTEM_RELAYER"


def test_mvp_only_three_roles_and_owner_is_payee(mvp):
    m = mvp["manifest"]
    assert len({m.owner, m.attestor, m.relayer}) == 3
    assert m.payee_candidates == (m.owner,)
    assert m.shares == "0x" + "00" * 20


def test_mvp_payment_session_cap_is_independent_of_risk(mvp, workflows):
    for i in range(2):
        assert (
            workflows.run(intent(mvp, "TOKEN_PAYMENT", "25000000"), f"pay-{i}")["status"]
            == "CONFIRMED"
        )
    result = workflows.run(intent(mvp, "TOKEN_PAYMENT", "1000000"), "exhausted")
    assert result["status"] == "REJECTED", result
    assert mvp["contracts"][0].functions.sessions(mvp["session_id"]).call()[4] == 0


def test_mvp_concurrent_retries_one_spend(mvp, workflows):
    proposal = intent(mvp, "TOKEN_PAYMENT", "1000000")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: workflows.run(proposal, "same"), range(2)))
    assert all(r["status"] == "CONFIRMED" for r in results), [r.get("reason_code") for r in results]
    assert len({r["outcome"]["tx_hash"] for r in results}) == 1
    assert mvp["execution"].context(mvp["session_id"])["authority"]["actions"] == 1


def test_mvp_owner_revokes_previously_signed_payment(mvp):
    build, c, e, p, operation, phi, signature = prepare(
        mvp, intent(mvp, "TOKEN_PAYMENT", "1000000")
    )
    vault = mvp["contracts"][0]
    send(mvp["execution"].chain.w3, mvp["owner"], vault.functions.revokeSession(mvp["session_id"]))
    with pytest.raises(Exception):
        vault.functions.executeOperation(operation.abi_tuple, phi.abi_tuple, signature).call()
    assert not vault.functions.usedNonce(int(operation.nonce)).call()


def test_mvp_rebalance_uses_only_swaps(mvp, workflows):
    agent = AutonomousTreasury(workflows)
    agent.configure(True, mvp["session_id"])
    result = agent.tick()
    assert result["status"] == "CONFIRMED", result.get("reason_code")
    assert result["intent"]["operation"] == "TOKEN_SWAP"
    again = agent.tick()
    assert again["reason"] in {"REBALANCE_COOLDOWN", "WITHIN_TARGET_BAND"}


@pytest.mark.parametrize("operation", ["VAULT_DEPOSIT", "VAULT_WITHDRAW"])
def test_mvp_disabled_operation_cannot_reach_builder_or_signer(mvp, workflows, operation):
    with pytest.raises(Exception, match="MVP_UNSUPPORTED_OPERATION"):
        workflows.run(intent(mvp, operation), "disabled")


def test_mvp_bad_effects_and_payment_overcredit_are_not_proofs(mvp):
    proposal = intent(mvp, "TOKEN_PAYMENT", "1000000")
    build, c, e, p, *_ = prepare(mvp, proposal)
    with pytest.raises(ValueError, match="UNEXPECTED_DISABLED_ASSET_MOVEMENT"):
        prove_operation(proposal, build, e | {"deltas": ["-1000000", "0", "1", "0"]}, c)
    with pytest.raises(ValueError, match="RECEIPT_NOT_MET"):
        prove_operation(proposal, build, e | {"received": "500000"}, c)


def test_mvp_concurrent_distinct_payments_cannot_exceed_session_cap(mvp,workflows):
    proposal=intent(mvp,"TOKEN_PAYMENT","25000000")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda i:workflows.run(proposal,f"distinct-{i}"),range(3)))
    assert [r["status"] for r in results].count("CONFIRMED")==2
    assert [r["status"] for r in results].count("REJECTED")==1
    assert mvp["contracts"][0].functions.spendScopes(mvp["session_id"]).call()[3]==50*10**6


def test_mvp_receipt_observer_runs_with_autonomy_disabled(mvp,workflows,monkeypatch):
    w3=mvp["execution"].chain.w3
    original=w3.eth.wait_for_transaction_receipt
    def receipt_timeout(*args,**kwargs):raise TimeoutError("controlled test timeout after broadcast")
    monkeypatch.setattr(w3.eth,"wait_for_transaction_receipt",receipt_timeout)
    result=workflows.run(intent(mvp,"TOKEN_PAYMENT","1000000"),"monitor")
    assert result["status"]=="SUBMITTED_UNKNOWN",result
    monkeypatch.setattr(w3.eth,"wait_for_transaction_receipt",original)
    agent=AutonomousTreasury(workflows);assert not agent.state()["enabled"]
    agent.reconcile_outcomes()
    observed=workflows.store.get(result["workflow_id"])
    assert observed["status"]=="CONFIRMED"
    assert observed["outcome"]["system_gas_expense"]["actual_cost_wei"]!="0"


def test_mvp_preserves_specific_existing_route_gate_reason(mvp,workflows,monkeypatch):
    from treasury_backend.modules.execution.errors import PlaneError
    def blocked(*args):raise PlaneError("LFJ_UNSUPPORTED_ROUTE","Selected route is outside the approved V1 pool",409)
    monkeypatch.setattr(mvp["execution"],"build",blocked)
    result=workflows.run(intent(mvp),"blocked-quoter")
    assert result["status"]=="REJECTED" and result["reason_code"]=="LFJ_UNSUPPORTED_ROUTE"
