"""Money-moving boundary regressions: proof failures, expense guards, reorg and replacement."""

import copy

import pytest
import z3
from test_v3_execution import execute, intent, prepare

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.execution.simulation.runner import rpc
from treasury_backend.modules.gas_credit.system import SystemGasLedger, gas_terms
from treasury_contracts.proof_v3 import prove_operation


def test_mvp_invalid_assumptions_counterexamples_and_unknown_never_verify(mvp, monkeypatch):
    proposal = intent(mvp)
    built, c, e, proof, *_ = prepare(mvp, proposal)
    assert [q["result"] for q in proof["queries"]] == ["SAT", "UNSAT", "UNSAT", "UNSAT"]
    invalid = copy.deepcopy(c)
    invalid["price_intervals"][0] = ["0", "0"]
    with pytest.raises(ValueError, match="INVALID_PRICE_BAND"):
        prove_operation(proposal, built, e, invalid)
    contradictory = copy.deepcopy(c)
    contradictory["share_rate_low"] = "2000000"
    with pytest.raises(ValueError, match="PROOF_FEASIBLE_PRICES_UNSAT"):
        prove_operation(proposal, built, e, contradictory)
    tight = copy.deepcopy(c)
    tight["proof_policy"]["max_relative_loss_bps"] = 0
    with pytest.raises(ValueError, match="PROOF_CHECK_MODE_SAT"):
        prove_operation(proposal, built, e, tight)
    actual = z3.Solver

    class Unknown:
        def __init__(self):
            self.solver = actual()

        def set(self, **kw):
            self.solver.set(**kw)

        def add(self, *args):
            self.solver.add(*args)

        def sexpr(self):
            return self.solver.sexpr()

        def check(self):
            return z3.unknown

    monkeypatch.setattr("treasury_contracts.proof_v3.z3.Solver", Unknown)
    with pytest.raises(ValueError, match="PROOF_FEASIBLE_PRICES_UNKNOWN"):
        prove_operation(proposal, built, e, c)


def test_mvp_reorg_removes_confirmation_and_retains_gas_hold(mvp):
    ex = mvp["execution"]
    snap = rpc(ex.chain.w3, "evm_snapshot", [])
    result = execute(mvp, intent(mvp, "TOKEN_PAYMENT", "1000000"))
    assert result["status"] == "CONFIRMED"
    assert rpc(ex.chain.w3, "evm_revert", [snap])
    outcome = ex.reconcile(result["tx_hash"])
    assert outcome["status"] == "REORGED"
    expense = SystemGasLedger(ex.store.db_path, ex.chain.settings).history()[0]
    assert expense["state"] == "HELD" and expense["actual_cost_wei"] == "0"


def test_mvp_unknown_broadcast_and_replacement_are_not_success(mvp, monkeypatch):
    ex = mvp["execution"]
    built, c, e, p, operation, phi, signature = prepare(
        mvp, intent(mvp, "TOKEN_PAYMENT", "1000000")
    )
    w3 = ex.chain.w3
    original = w3.eth.send_raw_transaction

    def offline(_):
        raise ConnectionError("controlled test RPC outage")

    monkeypatch.setattr(w3.eth, "send_raw_transaction", offline)
    result = ex.execute(built, operation, phi, signature)
    assert result["status"] == "SUBMITTED_UNKNOWN"
    assert ex.submission_hash(built["build_id"]) == result["tx_hash"]
    monkeypatch.setattr(w3.eth, "send_raw_transaction", original)
    account = mvp["relayer"]
    tx = {
        "from": account.address,
        "to": account.address,
        "value": 0,
        "gas": 21000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": 31337,
    }
    replacement = account.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(replacement.raw_transaction)
    )
    assert receipt.status == 1
    assert ex.reconcile(result["tx_hash"])["status"] == "REPLACED_UNVERIFIED"
    assert not ex.chain.vault.functions.usedNonce(int(operation.nonce)).call()


def test_mvp_insufficient_relayer_and_fee_caps_fail_before_journal(mvp):
    ex = mvp["execution"]
    w3 = ex.chain.w3
    with pytest.raises(ControlError, match="RELAYER_GAS_LIMIT"):
        gas_terms(ex.chain.settings, w3, mvp["relayer"].address, 20_000_000)
    cap = ex.chain.settings.model_copy(update={"max_tx_fee_wei": 1})
    with pytest.raises(ControlError, match="RELAYER_FEE_LIMIT"):
        gas_terms(cap, w3, mvp["relayer"].address, 300000)
    rpc(w3, "anvil_setBalance", [mvp["relayer"].address, "0x0"])
    with pytest.raises(ControlError, match="RELAYER_INSUFFICIENT_AVAX"):
        gas_terms(ex.chain.settings, w3, mvp["relayer"].address, 300000)
    assert ex.submission_hash("never-built") is None


def test_mvp_gas_daily_reservation_is_atomic_with_submission(mvp):
    ex = mvp["execution"]
    built, c, e, p, operation, phi, signature = prepare(
        mvp, intent(mvp, "TOKEN_PAYMENT", "1000000")
    )
    ex.chain.settings = ex.chain.settings.model_copy(update={"max_daily_gas_expense_wei": 1})
    nonce = ex.chain.w3.eth.get_transaction_count(mvp["relayer"].address)
    with pytest.raises(ControlError, match="RELAYER_DAILY_GAS_LIMIT"):
        ex.execute(built, operation, phi, signature)
    assert ex.submission_hash(built["build_id"]) is None
    assert ex.chain.w3.eth.get_transaction_count(mvp["relayer"].address) == nonce
    assert not SystemGasLedger(ex.store.db_path, ex.chain.settings).history()
