"""Receipt reconciliation must not count one reverted transaction twice."""

from types import SimpleNamespace

import pytest

from treasury_backend.core.domain import SecurityDecision
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.persistence import Store

POLICY = "0x" + "11" * 32
NOW = 1_700_000_000


def decision(store, number):
    workflow = f"workflow_{number}"
    value = SecurityDecision(
        decision_id=f"decision_{number}",
        intent_id=f"intent_{number}",
        build_id=None,
        verdict="APPROVE",
        reason_codes=[],
        policy_hash=POLICY,
        calldata_hash=None,
        simulation_evidence_root=None,
        mandate_version=1,
        snapshot_id=None,
        created_at=NOW,
        expires_at=NOW + 30,
    )
    store.start(workflow, {})
    store.record(workflow, "APPROVED", value, {"mandate": {"policy_hash": POLICY}}, 0, {})
    return workflow, value


def outcome(store, number, state="REVERTED"):
    workflow, value = decision(store, number)
    with store.connection(write=True) as conn:
        conn.execute(
            "INSERT INTO attestations VALUES (?, ?, ?, ?, ?, ?, ?)",
            (value.decision_id, "scope", str(number), state, NOW, NOW + 30, "{}"),
        )
    details = {
        "receipt": {
            "tx_hash": "0x" + f"{number:064x}",
            "revert_reason": "POSTCONDITION_FAILED" if state == "REVERTED" else None,
        }
    }
    store.event(workflow, state, NOW, decision_id=value.decision_id, **details)
    return workflow, value, details


@pytest.mark.parametrize(
    "case", ["one_reconciled_revert", "two_distinct_reverts", "then_confirmed"]
)
def test_quarantine_uses_latest_outcome_per_attestation(tmp_path, case):
    store = Store(tmp_path / "state.sqlite3")
    workflow, value, details = outcome(store, 1)
    # A reorg moves the same receipt back through SUBMITTED before reconfirmation.
    assert store.transition(workflow, value.decision_id, "REVERTED", "SUBMITTED", NOW)
    assert store.transition(workflow, value.decision_id, "SUBMITTED", "REVERTED", NOW, **details)
    if case == "two_distinct_reverts":
        outcome(store, 2)
    elif case == "then_confirmed":
        outcome(store, 2, "CONFIRMED")
    workflow, value = decision(store, 3)
    signed = []

    def sign():
        signed.append(True)
        return SimpleNamespace(model_dump_json=lambda: "{}", typed_data_hash=POLICY), NOW

    def reserve():
        return store.reserve_signature(
            id_=value.decision_id,
            workflow_id=workflow,
            scope="scope",
            nonce="3",
            now=NOW,
            expires_at=NOW + 30,
            sign=sign,
        )

    if case == "two_distinct_reverts":
        with pytest.raises(ControlError, match="SIGNER_QUARANTINED"):
            reserve()
        assert not signed
    else:
        reserve()
        assert signed == [True]
