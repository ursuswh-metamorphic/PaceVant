"""Actual EVM execution, durable process observations, failure and retry boundaries."""
# ruff: noqa: F811
from test_mvp_workflows import workflows  # noqa: F401
from test_v3_execution import intent

from treasury_backend.modules.workflows.observability import public_value
from treasury_contracts.crypto import content_hash
from treasury_contracts.proof_v3 import prove_operation
from treasury_contracts.v3 import OperationIntent


def test_real_payment_explains_signing_and_settlement_without_changing_proof(mvp, workflows):
    result = workflows.run(intent(mvp, "TOKEN_PAYMENT", "1000000"), "observable-payment")
    assert result["status"] == "CONFIRMED", result.get("reason_code")
    events = result["activity"]
    checks = {e["check_id"]: e for e in events if e["kind"] == "check"}
    for name in ("EXACT_INTENT", "CALL_DECODED", "ITAG_GRAPH", "ITAG_SEMANTIC", "Z3_FEASIBLE_PRICES",
                 "STATE_REVALIDATION", "SIGN_ONCE", "PROOF_REVALIDATION", "JOURNAL_RESERVED",
                 "BROADCAST", "RECEIPT_BINDINGS", "VAULT_EFFECTS", "GAS_SETTLEMENT"):
        assert checks[name]["status"] == "PASS", (name, checks.get(name))
    assert checks["JOURNAL_RESERVED"]["sequence"] < checks["BROADCAST"]["sequence"]
    assert checks["Z3_FEASIBLE_PRICES"]["observed"] == "SAT"
    assert checks["Z3_CHECK_MODE"]["observed"] == "UNSAT"
    assert all(e.get("duration_ms", 0) >= 0 for e in events)
    assert len(result["timeline"]) == 11
    evidence = {e["stage"]: e["evidence"] for e in result["timeline"]}
    proof = prove_operation(OperationIntent.model_validate(result["intent"]),
                            evidence["BUILD"], evidence["SIMULATION"], evidence["OWNER_AUTHORITY"])
    assert proof == evidence["PROOF"]
    assert evidence["ATTESTATION"]["signed_fields"]["proofContextHash"] == proof["proof_hash"]
    assert checks["VAULT_EFFECTS"]["observed"]["evidence_root"] == content_hash(evidence["SIMULATION"])
    assert all(word not in str(events) for word in ("private_key", "owner_signature", "raw_transaction", "'signature'"))
    assert workflows.execution.on_activity is None


def test_rejected_payee_has_a_real_failed_stage_and_no_signature(mvp, workflows):
    proposal = intent(mvp, "TOKEN_PAYMENT", "1000000").model_copy(update={"recipient": mvp["manifest"].relayer})
    result = workflows.run(proposal, "observable-rejection")
    assert result["status"] == "REJECTED"
    assert result["reason_code"] == "PAYEE_NOT_ALLOWED"
    assert any(e["stage"] == "BUILD" and e["kind"] == "completed" and e["status"] == "FAIL" for e in result["activity"])
    assert not any(e["stage"] == "ATTESTATION" for e in result["timeline"])
    assert not result.get("outcome")


def test_retry_retains_the_same_signature_submission_and_process_history(mvp, workflows):
    proposal = intent(mvp, "TOKEN_PAYMENT", "1000000")
    first = workflows.run(proposal, "observable-retry")
    second = workflows.run(proposal, "observable-retry")
    assert first["status"] == second["status"] == "CONFIRMED"
    assert first["outcome"]["tx_hash"] == second["outcome"]["tx_hash"]
    assert first["activity"] == second["activity"]


def test_process_redaction_preserves_public_hashes_but_excludes_signing_capability():
    value = public_value({"proof_hash": "0x" + "ab"*32, "nonce": "123", "private_key": "secret",
                          "nested": {"signature": "signed-data", "api_key": "secret", "owner_signature": "secret", "amount": "10000"}})
    assert value == {"proof_hash": "0x" + "ab"*32, "nonce": "123", "nested": {"amount": "10000"}}
