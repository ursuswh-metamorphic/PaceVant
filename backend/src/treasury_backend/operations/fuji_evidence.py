"""Export independently checkable public-chain evidence without credentials."""

import json

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError, Web3RPCError

from treasury_backend.modules.execution.chain import contract
from treasury_backend.modules.execution.dex.lfj import ROUTER
from treasury_backend.modules.persistence import Store
from treasury_contracts.v2 import SignedPDRV2, message_v2

from .contracts import deployed
from .env import atomic_json
from .errors import OpsError


def collect(p, workflow_id):
    data, w3, vault = deployed(p)
    if p.network != "fuji" or "anvil" in w3.client_version.lower():
        raise OpsError("Public Fuji evidence cannot be exported from Anvil/local runs")
    store = Store(p.control_data / "control.sqlite3")
    workflow = store.workflow(workflow_id)
    attempts = store.attempts(workflow_id)
    confirmed = next((e for e in reversed(workflow["timeline"]) if e["stage"] == "CONFIRMED"), None)
    if confirmed is None:
        raise OpsError("Evidence requires a CONFIRMED workflow")
    receipt = w3.eth.get_transaction_receipt(confirmed["receipt"]["tx_hash"])
    tx = w3.eth.get_transaction(receipt.transactionHash)
    bundle = next(a for a in attempts if a["decision"]["decision_id"] == confirmed["decision_id"])
    with store.connection() as db:
        row = db.execute("SELECT signed_pdr FROM attestations WHERE decision_id=?", (confirmed["decision_id"],)).fetchone()
    pdr = SignedPDRV2.model_validate_json(row[0])
    signer = Account.recover_message(message_v2(pdr.domain, pdr.approval), signature=pdr.signature)
    encoded = vault.encode_abi("executeApprovedSwapV2", args=[pdr.approval.abi_tuple,
        bundle["build"]["router_calldata"], pdr.phi.abi_tuple, pdr.signature])
    n = receipt.blockNumber
    tokens = [contract(w3, "IERC20Metadata", data[name]) for name in ("token_in", "token_out")]
    before = [t.functions.balanceOf(vault.address).call(block_identifier=n - 1) for t in tokens]
    after = [t.functions.balanceOf(vault.address).call(block_identifier=n) for t in tokens]
    approval = pdr.approval
    day = w3.eth.get_block(n).timestamp // 86400
    budget_before = vault.functions.sessions(approval.sessionId).call(block_identifier=n - 1)[4]
    budget_after = vault.functions.sessions(approval.sessionId).call(block_identifier=n)[4]
    global_before = vault.functions.globalDailyRiskUsedUsdE8(day).call(block_identifier=n - 1)
    global_after = vault.functions.globalDailyRiskUsedUsdE8(day).call(block_identifier=n)
    checks = {
        "chain_43113": w3.eth.chain_id == 43113,
        "successful_receipt": receipt.status == 1,
        "relayer_is_configured_wallet": tx["from"].lower() == data["relayer"].lower(),
        "recipient_is_vault": tx["to"].lower() == vault.address.lower(),
        "calldata_is_exact_signed_call": Web3.to_hex(tx["input"]) == encoded,
        "signer_is_attestor": signer.lower() == data["attestor"].lower(),
        "nonce_consumed": vault.functions.usedNonce(int(approval.nonce)).call(block_identifier=n),
        "exact_input_delta": after[0] - before[0] == -int(approval.amountIn),
        "output_at_least_minimum": after[1] - before[1] >= int(approval.minAmountOut),
        "vault_allowance_cleared": all(t.functions.allowance(vault.address, data["router"]).call(block_identifier=n) == 0 for t in tokens),
        "adapter_allowance_cleared": tokens[0].functions.allowance(data["router"], ROUTER).call(block_identifier=n) == 0,
        "session_debit_matches_proof": budget_after - budget_before == int(approval.riskDebitUsdE8),
        "global_debit_matches_proof": global_after - global_before == int(approval.riskDebitUsdE8),
        "three_unsat_obligations": all(bundle["proof"][k] == "UNSAT" for k in ("check_mode", "compile_mode", "risk_bound")),
    }

    def rejects(label, payload, block, expected):
        try:
            w3.eth.call({"from": tx["from"], "to": vault.address, "data": payload}, block_identifier=block)
        except (ContractLogicError, Web3RPCError) as exc:
            # A transport/archive error is never counted as a successful negative test.
            raw = json.dumps([getattr(exc, "data", None), getattr(exc, "rpc_response", None), str(exc)], default=str)
            selector = Web3.to_hex(Web3.keccak(text=expected)[:4])
            return {"case": label, "block_number": block, "expected_error": expected,
                    "selector": selector, "passed": selector in raw, "broadcast": False}
        return {"case": label, "passed": False, "broadcast": False}

    bad_data = bundle["build"]["router_calldata"][:-2] + ("01" if bundle["build"]["router_calldata"][-2:] != "01" else "02")
    changed_call = vault.encode_abi("executeApprovedSwapV2", args=[approval.abi_tuple, bad_data, pdr.phi.abi_tuple, pdr.signature])
    bad_signature = Web3.to_hex(Account.create().sign_message(message_v2(pdr.domain, approval)).signature)
    wrong_signer = vault.encode_abi("executeApprovedSwapV2", args=[approval.abi_tuple,
        bundle["build"]["router_calldata"], pdr.phi.abi_tuple, bad_signature])
    negatives = [rejects("replay", encoded, n, "NonceReplay()"),
                 rejects("tampered_router_calldata", changed_call, n - 1, "HashMismatch()"),
                 rejects("unauthorized_signer", wrong_signer, n - 1, "BadSignature()")]
    report = {
        "schema_version": "fuji-live-evidence-v1", "workflow_id": workflow_id,
        "status": workflow["status"], "chain_id": 43113, "public_chain": True,
        "planner": {k: v for k, v in workflow.items() if k.startswith("planner_")},
        "wallets": {k: data[k] for k in ("owner", "attestor", "relayer")},
        "contracts": {k: data[k] for k in ("vault_address", "router", "token_in", "token_out")},
        "transaction": {"hash": Web3.to_hex(receipt.transactionHash), "block": n,
            "block_hash": Web3.to_hex(receipt.blockHash), "gas_used": str(receipt.gasUsed),
            "explorer": "https://testnet.snowtrace.io/tx/" + Web3.to_hex(receipt.transactionHash)},
        "token_deltas_base_units": [str(a - b) for a, b in zip(after, before, strict=True)],
        "checks": checks, "negative_eth_calls": negatives,
        "all_checks_passed": all(checks.values()) and all(x["passed"] for x in negatives),
        "proof": bundle["proof"], "oracle_snapshot": bundle["portfolio"],
        "simulation": bundle["simulation"],
        "limitations": ["Testnet reference USD valuations; no redemption or real-dollar claim.",
            "Stress uses hypothetical external actor funding and attestor overrides ONLY on isolated Anvil forks.",
            "Bounded SMT model plus concrete EVM tests; not a complete security audit."],
    }
    path = p.control_data / ("evidence-" + workflow_id + ".json")
    atomic_json(path, report)
    return report, path
