"""V3 operations run on real EVM, including disposable pinned-fork simulations."""

import time

import pytest
from eth_account import Account
from web3 import Web3

from treasury_contracts.proof_v3 import prove_operation
from treasury_contracts.v3 import Constraints, Operation, OperationIntent, operation_message


def intent(data, operation="TOKEN_SWAP", amount="100000000", **overrides):
    m = data["manifest"]
    fields = {"operation": operation, "chain_id": 31337, "treasury": m.treasury, "session_id": data["session_id"],
              "token_in": m.usdc, "token_out": m.wavax, "recipient": m.treasury, "amount": amount,
              "deadline": int(time.time()) + 150, "objective": "Execute the exact authorized local treasury operation"}
    if operation == "TOKEN_PAYMENT":
        fields.update(token_out=m.usdc, recipient=data["payee"])
    if operation == "VAULT_DEPOSIT":
        fields.update(token_out=m.shares)
    if operation == "VAULT_WITHDRAW":
        fields.update(token_in=m.shares, token_out=m.usdc)
    return OperationIntent.model_validate(fields | overrides)


def prepare(data, proposal):
    execution = data["execution"]
    context = execution.context(data["session_id"])
    build = execution.build(proposal, context)
    effects = execution.simulate(build, context)
    proof = prove_operation(proposal, build, effects, context)
    phi = Constraints.model_validate(proof["phi"])
    operation = Operation.model_validate(build["operation"] | {
        "evidenceRoot": proof["evidence_root"], "proofContextHash": proof["proof_hash"],
        "constraintsHash": phi.hash, "riskDebitUsdE8": proof["risk_debit_usd_e8"],
        "spendDebitUsdE8": proof["spend_debit_usd_e8"]})
    signature = Web3.to_hex(Account.sign_message(operation_message(31337, proposal.treasury, operation), data["attestor"].key).signature)
    return build, context, effects, proof, operation, phi, signature


def execute(data, proposal):
    build, context, effects, proof, operation, phi, signature = prepare(data, proposal)
    ex = data["execution"]
    ex.revalidate(proposal, build, context)
    final = ex.preflight(build, context, operation, phi, signature)
    assert final["exact_signed_preflight"] and not final["simulation_overrides"]
    result = ex.execute(build, operation, phi, signature)
    assert result["status"] == "CONFIRMED", result
    assert result["actual_deltas"] == effects["deltas"]
    assert result["public_chain_receipt"] is False
    return result


def test_v3_all_transaction_groups_and_reverse(v3):
    m = v3["manifest"]
    execute(v3, intent(v3))
    execute(v3, intent(v3, amount=str(10**18), token_in=m.wavax, token_out=m.usdc))
    payment = execute(v3, intent(v3, "TOKEN_PAYMENT", "10000000"))
    assert payment["payee_received"] == "10000000"
    deposit = execute(v3, intent(v3, "VAULT_DEPOSIT", "100000000"))
    assert int(deposit["actual_deltas"][2]) > 0
    withdrawal = execute(v3, intent(v3, "VAULT_WITHDRAW", "10000000"))
    assert int(withdrawal["actual_deltas"][0]) > 0


def test_v3_unknown_payee_rejected_before_simulation(v3):
    proposal = intent(v3, "TOKEN_PAYMENT", "10000000", recipient=Account.create().address)
    with pytest.raises(ValueError, match="PAYEE_NOT_ALLOWED"):
        v3["execution"].build(proposal, v3["execution"].context(v3["session_id"]))


def test_v3_proof_revalidation_is_stable(v3):
    from treasury_contracts.proof_v3 import prove_operation
    proposal = intent(v3)
    build, context, effects, proof, *_ = prepare(v3, proposal)
    other = prove_operation(proposal, build, effects, context)
    assert other == proof, [k for k in proof if proof[k] != other[k]]
