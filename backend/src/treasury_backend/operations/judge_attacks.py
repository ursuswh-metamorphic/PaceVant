"""Fixed adversarial eth_call probes against the deployed Fuji vault. Never signs or sends.

Use historical canonical state so the original signed call is a successful control;
an expired signature, used nonce, or unavailable RPC must not count as detection.
"""

import copy
import time

from web3 import Web3
from web3.exceptions import ContractCustomError

from treasury_backend.modules.execution.chain import contract
from treasury_contracts.mvp import MvpManifest
from treasury_contracts.rpc import evm_web3

CASES = {
    "payment-amount": ("payment", "BadSignature()", "amount", "20000"),
    "payment-replay": ("payment", "NonceReplay()", "nonce", None),
    "swap-slippage": ("swap", "BadSignature()", "minOutput", "1"),
    "swap-route": ("swap", "BadSignature()", "target", "0x0000000000000000000000000000000000000Bad"),
}
SEEDS = {
    "payment": "0x10f6a04e22179f4186459e3738c61597048e9b2aac724c01347ba306f4470b8c",
    "swap": "0xa708f44e355b6926c02693282f8ca6514fd043199ae8d23d3a031d64f82e4b2d",
}


def run_attack(case, rpc_url, manifest_file, job_id):
    scenario, expected_error, field, replacement = CASES[case]
    manifest = MvpManifest.model_validate_json(manifest_file.read_bytes())
    manifest.verify_owner()
    if manifest.environment != "REAL_FUJI_EXECUTION":
        raise ValueError("PUBLIC_MANIFEST_REQUIRED")
    w3 = evm_web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if w3.eth.chain_id != 43113:
        raise ValueError("CHAIN_MISMATCH")
    vault = contract(w3, "PolicyVaultMVP", manifest.treasury)
    seed = SEEDS[scenario]
    tx, receipt = w3.eth.get_transaction(seed), w3.eth.get_transaction_receipt(seed)
    header = w3.eth.get_block(receipt.blockNumber)
    parent = receipt.blockNumber - 1
    if (receipt.status != 1 or receipt.blockHash != header.hash
            or tx["to"].lower() != manifest.treasury or tx["from"].lower() != manifest.relayer):
        raise ValueError("ATTACK_CONTROL_IDENTITY_INVALID")
    for block in (parent, "latest"):
        code = w3.eth.get_code(vault.address, block)
        if Web3.to_hex(Web3.keccak(code)) != manifest.code_hashes["treasury"]:
            raise ValueError("CODE_IDENTITY_CHANGED")
    fn, arguments = vault.decode_function_input(tx["input"])
    if fn.fn_name != "executeOperation" or arguments["a"]["kind"] != (2 if scenario == "payment" else 1):
        raise ValueError("ATTACK_CONTROL_OPERATION_INVALID")
    original = arguments["a"]
    # A successful control is mandatory on every run, before evaluating the attack.
    call = {"from": tx["from"], "to": vault.address, "data": Web3.to_hex(tx["input"]), "gas": tx["gas"]}
    w3.eth.call(call, block_identifier=parent)
    mutated = copy.deepcopy(arguments)
    attack_block = parent
    if case == "payment-replay":
        attack_block = receipt.blockNumber
        if not vault.functions.usedNonce(original["nonce"]).call(block_identifier=attack_block):
            raise ValueError("ATTACK_REPLAY_CONTROL_INVALID")
    else:
        mutated["a"][field] = int(replacement) if field in {"amount", "minOutput"} else Web3.to_checksum_address(replacement)
        if mutated["a"][field] == original[field]:
            raise ValueError("ATTACK_MUTATION_MISSING")
    # web3's decoded named structs must be encoded as ABI-ordered tuples.
    inputs = fn.abi["inputs"]
    operation = tuple(mutated["a"][c["name"]] for c in inputs[0]["components"])
    constraints = tuple(mutated["phi"][c["name"]] for c in inputs[1]["components"])
    data = vault.functions.executeOperation(operation, constraints, mutated["signature"])._encode_transaction_data()
    expected_selector = Web3.to_hex(Web3.keccak(text=expected_error)[:4])
    observed = None
    try:
        w3.eth.call(call | {"data": data}, block_identifier=attack_block)
    except ContractCustomError as error:
        observed = error.args[0] if error.args else None
    verified = isinstance(observed, str) and observed.lower() == expected_selector.lower()
    if w3.eth.get_block(receipt.blockNumber).hash != header.hash:
        raise ValueError("REORG_DURING_ATTACK_CHECK")
    evidence = {
        "case": case, "method": "eth_call", "control": "SUCCESS", "seed_tx_hash": seed,
        "source_block": attack_block, "control_block": parent, "canonical_seed_receipt": True,
        "expected_error": expected_error, "expected_selector": expected_selector, "observed_selector": observed,
        "field": field, "original": str(original[field]), "candidate": str(mutated["a"][field]),
        "same_original_signature": True, "broadcast": False, "signing_keys_used": False,
        "scope": "Historical public Fuji state; contract enforcement, not LLM attack detection or a new public transaction",
    }
    now = int(time.time())
    intent = {"operation": "TOKEN_PAYMENT" if scenario == "payment" else "TOKEN_SWAP", "amount": str(original["amount"]),
        "token_in": original["tokenIn"], "token_out": original["tokenOut"], "recipient": original["recipient"],
        "treasury": manifest.treasury, "objective": case, "deadline": original["deadline"],
        "session_id": Web3.to_hex(original["sessionId"]), "chain_id": 43113}
    reason = "ATTACK_" + ("NONCE_REPLAY" if case == "payment-replay" else "BAD_SIGNATURE") if verified else "ATTACK_NOT_BLOCKED_AS_EXPECTED"
    return {"environment": "REAL_FUJI_EXECUTION", "execution_kind": "HISTORICAL_ETH_CALL", "attack": case,
        "status": "REJECTED" if verified else "FAILED", "reason_code": reason,
        "public_chain_broadcast": False, "terminal": True, "phase": "FINISHED", "active_stage": "EXACT_SIGNED_PREFLIGHT",
        "semantic_scope": "CONTRACT_ENFORCEMENT_ONLY", "scope": evidence["scope"], "attack_evidence": evidence,
        "source_block": attack_block,
        "workflow": {"workflow_id": job_id, "status": "REJECTED" if verified else "FAILED", "created_at": now,
            "intent": intent, "reason_code": reason, "timeline": [
                {"stage": "OWNER_AUTHORITY", "created_at": now, "evidence": {
                    "manifest_verified": True, "code_identity_verified": True,
                    "treasury": manifest.treasury, "usdc": manifest.usdc, "wavax": manifest.wavax,
                    "source_block": attack_block, "scope": evidence["scope"]}},
                {"stage": "EXACT_SIGNED_PREFLIGHT", "created_at": now, "evidence": evidence},
                {"stage": "REJECTION_OR_RECOVERY", "created_at": now, "evidence": {"code": reason, "signed": False}},
            ]}}
