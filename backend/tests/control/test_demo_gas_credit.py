"""No network: billing invariants consume explicitly constructed verifier reports."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from treasury_backend.config.demo import DemoSettings
from treasury_backend.modules.gas_credit import CreditError, GasCreditLedger

USER, VAULT, RELAYER = ["0x" + x * 40 for x in ("1", "2", "3")]
TX, BLOCK = "0x" + "a" * 64, "0x" + "b" * 64


def setup(tmp_path, credit=1000, cap=600):
    cfg = DemoSettings(True, USER, "x" * 32, credit, cap)
    return GasCreditLedger(
        tmp_path / "state.sqlite3", cfg, chain_id=43113, vault=VAULT, relayer=RELAYER
    )


def reserve(gas, build="build_a", tx=TX, maximum=600, balance=10000):
    with gas.db() as db:
        db.execute("BEGIN IMMEDIATE")
        gas.reserve(db, build, tx, maximum, balance)


def report(**changes):
    values = dict(
        tx_hash=TX,
        verification_status="VERIFIED",
        receipt_status="SUCCESS",
        canonical=True,
        gas_verified=True,
        confirmations=2,
        chain_id=43113,
        vault_address=VAULT,
        gas_payer=RELAYER,
        build_id="build_a",
        gas_used="100",
        effective_gas_price_wei="3",
        gas_cost_wei="300",
        block_hash=BLOCK,
    )
    return SimpleNamespace(**(values | changes))


def test_request_dedup_concurrent_and_goal_change(tmp_path):
    gas = setup(tmp_path)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: gas.begin_request("request-key-1", "goal"), range(2)))
    assert sum(new for _, new in results) == 1
    assert results[0][0]["workflow_id"] == results[1][0]["workflow_id"]
    with pytest.raises(CreditError, match="IDEMPOTENCY_CONFLICT"):
        gas.begin_request("request-key-1", "different goal")
    with pytest.raises(CreditError, match="REQUEST_IN_PROGRESS"):
        gas.begin_request("request-key-2", "goal")


@pytest.mark.parametrize("receipt_status", ["SUCCESS", "REVERTED"])
def test_actual_fee_once_across_polls_and_restart(tmp_path, receipt_status):
    gas = setup(tmp_path)
    row, _ = gas.begin_request("request-key", "goal")
    gas.bind_build(row["workflow_id"], "build_a")
    reserve(gas)
    assert gas.account()["reserved_wei"] == "600"
    assert gas.account()["spent_wei"] == "0"
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: gas.reconcile(report(receipt_status=receipt_status)), range(8)))
    restarted = setup(tmp_path, credit=2000)  # Env change is not a top-up.
    restarted.reconcile(report(receipt_status=receipt_status))
    a = restarted.account()
    assert (a["allocated_wei"], a["spent_wei"], a["reserved_wei"], a["available_wei"]) == (
        "1000",
        "300",
        "0",
        "700",
    )
    assert len([e for e in a["ledger"] if e["kind"] == "GAS_DEBIT"]) == 1
    assert a["transactions"][0]["receipt_status"] == receipt_status


@pytest.mark.parametrize(
    "changes",
    [
        {"verification_status": "PENDING"},
        {"verification_status": "UNAVAILABLE"},
        {"confirmations": 1},
        {"gas_verified": False},
        {"canonical": False},
    ],
)
def test_pending_and_unverified_do_not_release_or_charge(tmp_path, changes):
    gas = setup(tmp_path)
    reserve(gas)
    gas.reconcile(report(**changes))
    a = gas.account()
    assert (a["spent_wei"], a["reserved_wei"]) == ("0", "600")


def test_reorg_reverses_charge_but_retains_hold_then_reinclusion(tmp_path):
    gas = setup(tmp_path)
    reserve(gas)
    gas.reconcile(report())
    gas.reconcile(report(verification_status="REORGED", canonical=False))
    a = gas.account()
    assert (a["spent_wei"], a["reserved_wei"], a["available_wei"]) == ("0", "600", "400")
    gas.reconcile(report())  # Even a repeated canonical block can become canonical again.
    gas.reconcile(report())
    a = gas.account()
    assert a["spent_wei"] == "300"
    assert sum(int(x["delta_wei"]) for x in a["ledger"]) == 700


@pytest.mark.parametrize(
    "changes",
    [
        {"gas_payer": USER},
        {"chain_id": 1},
        {"build_id": "other"},
        {"gas_cost_wei": "301"},
        {"gas_used": "1000", "gas_cost_wei": "3000"},
    ],
)
def test_wrong_receipt_cannot_charge(tmp_path, changes):
    gas = setup(tmp_path)
    reserve(gas)
    with pytest.raises(CreditError):
        gas.reconcile(report(**changes))
    assert gas.account()["spent_wei"] == "0"


def test_reservation_and_raw_journal_transaction_roll_back_together(tmp_path):
    gas = setup(tmp_path)
    with pytest.raises(RuntimeError):
        with gas.db() as db:
            db.execute("BEGIN IMMEDIATE")
            gas.reserve(db, "build_a", TX, 600, 10000)
            raise RuntimeError("submission insert failed before broadcast")
    assert gas.account()["reserved_wei"] == "0"


def test_insufficient_credit_physical_balance_and_fee_ceiling(tmp_path):
    gas = setup(tmp_path)
    with pytest.raises(CreditError, match="RELAYER_GAS_INSUFFICIENT"):
        reserve(gas, balance=599)
    with pytest.raises(CreditError, match="TRANSACTION_FEE_LIMIT"):
        reserve(gas, maximum=601)
    reserve(gas)
    with pytest.raises(CreditError, match="GAS_CREDIT_INSUFFICIENT"):
        reserve(gas, build="build_b", tx="0x" + "c" * 64)
    assert gas.account()["reserved_wei"] == "600"


def test_account_scope_does_not_silently_change(tmp_path):
    gas = setup(tmp_path)
    with pytest.raises(CreditError, match="SCOPE_CHANGED"):
        GasCreditLedger(
            gas.path,
            replace(gas.config, address=VAULT),
            chain_id=43113,
            vault=VAULT,
            relayer=RELAYER,
        )
