"""Read-only contract checks against a previously confirmed, journaled transaction."""

import json

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError, Web3RPCError

from treasury_contracts.v2 import SignedPDRV2, message_v2

from .errors import PlaneError


def contract_checks(chain, store, tx_hash):
    w3, vault = chain.w3, chain.vault
    if w3.eth.chain_id != chain.chain_id:
        raise PlaneError("CHAIN_MISMATCH", "RPC chain changed", 503)
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    tx = w3.eth.get_transaction(tx_hash)
    n = receipt.blockNumber
    if (receipt.status != 1 or w3.eth.get_block(n).hash != receipt.blockHash
            or w3.eth.block_number - n + 1 < chain.settings.required_confirmations):
        raise PlaneError("RECEIPT_UNVERIFIED", "A canonical confirmed success is required", 409)
    pdr = SignedPDRV2.model_validate(store.get("submitted-pdr", tx_hash))
    build = store.get("build", pdr.build_id)
    original = vault.encode_abi("executeApprovedSwapV2", args=[
        pdr.approval.abi_tuple, build["router_calldata"], pdr.phi.abi_tuple, pdr.signature])
    if (tx["to"].lower() != vault.address.lower()
            or pdr.domain.verifyingContract.lower() != vault.address.lower()
            or pdr.domain.chainId != chain.chain_id
            or tx["from"].lower() != chain.deployment["relayer"].lower()
            or Web3.to_hex(tx["input"]) != original):
        raise PlaneError("HASH_MISMATCH", "Recorded transaction does not match this vault/build", 409)

    def check(label, payload, block, expected):
        selector = Web3.to_hex(Web3.keccak(text=expected)[:4])
        result = {"case": label, "block_number": block, "expected_error": expected,
                  "selector": selector, "broadcast": False, "gas_charged_wei": "0"}
        try:
            w3.eth.call({"from": tx["from"], "to": vault.address, "data": payload},
                        block_identifier=block)
        except (ContractLogicError, Web3RPCError) as exc:
            raw = json.dumps([getattr(exc, "data", None), getattr(exc, "rpc_response", None),
                              str(exc)], default=str)
            passed = selector in raw
            return result | {"status": "PASS" if passed else "INCONCLUSIVE"}
        except Exception:
            return result | {"status": "INCONCLUSIVE"}
        return result | {"status": "FAIL"}

    data = build["router_calldata"]
    changed = data[:-2] + ("01" if data[-2:] != "01" else "02")
    altered = vault.encode_abi("executeApprovedSwapV2", args=[
        pdr.approval.abi_tuple, changed, pdr.phi.abi_tuple, pdr.signature])
    signature = Web3.to_hex(Account.create().sign_message(message_v2(pdr.domain, pdr.approval)).signature)
    wrong_signer = vault.encode_abi("executeApprovedSwapV2", args=[
        pdr.approval.abi_tuple, data, pdr.phi.abi_tuple, signature])
    cases = [check("nonce_replay", original, n, "NonceReplay()"),
             check("altered_calldata", altered, n - 1, "HashMismatch()"),
             check("unauthorized_signer", wrong_signer, n - 1, "BadSignature()")]
    # Detect a reorg during historical checks as well as before them.
    if w3.eth.get_block(n).hash != receipt.blockHash:
        for case in cases:
            case["status"] = "INCONCLUSIVE"
    return {"source": "PUBLIC_CHAIN_ETH_CALL" if chain.chain_id == 43113 else "LOCAL_ETH_CALL",
            "tx_hash": tx_hash, "chain_id": chain.chain_id, "reference_block": n,
            "reference_block_hash": Web3.to_hex(receipt.blockHash), "broadcast": False,
            "gas_charged_wei": "0", "checks": cases,
            "all_passed": all(c["status"] == "PASS" for c in cases)}
