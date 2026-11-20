"""Read-only Owner renewal bundle. No keys, signing, broadcast or contract redeployment."""

import argparse
import json
from pathlib import Path

from web3 import Web3

from treasury_backend.modules.execution.chain import contract
from treasury_backend.operations.env import PUBLIC_RPC
from treasury_backend.paths import ROOT
from treasury_contracts.crypto import content_hash
from treasury_contracts.mvp import MvpManifest
from treasury_contracts.rpc import evm_web3


def prepare(w3, manifest, cfg):
    manifest.verify_owner()
    if w3.eth.chain_id != manifest.chain_id:
        raise ValueError("CHAIN_MISMATCH")
    for name, expected in manifest.code_hashes.items():
        if Web3.to_hex(Web3.keccak(w3.eth.get_code(Web3.to_checksum_address(getattr(manifest, name))))) != expected:
            raise ValueError("CODE_IDENTITY_CHANGED")
    vault = contract(w3, "PolicyVaultMVP", manifest.treasury)
    if vault.functions.owner().call().lower() != manifest.owner:
        raise ValueError("OWNER_MISMATCH")
    h = w3.eth.get_block("latest")
    duration = cfg["session_duration_seconds"]
    if not 60 <= duration <= 604800:
        raise ValueError("REVIEW_SESSION_DURATION")
    owner = Web3.to_checksum_address(manifest.owner)
    nonce = w3.eth.get_transaction_count(owner, "pending")
    session = content_hash({"MVP_RENEWAL":manifest.treasury, "block":Web3.to_hex(h.hash), "nonce":nonce})
    commitment = content_hash({"previous_policy":Web3.to_hex(vault.functions.activePolicyHash().call()),
                               "new_session":session, "reviewed_config":cfg})
    expiry = h.timestamp + duration
    proof = vault.functions.proofPolicy().call()
    functions = [
        ("Renew policy lifetime; invalidate old sessions", vault.functions.configurePolicy(commitment,
            vault.functions.maxPerSwap().call(), vault.functions.maxSpendPerDay().call(), vault.functions.maxSlippageBps().call(), expiry)),
        ("Create replacement session", vault.functions.createSession(session, h.timestamp, expiry, proof[6])),
        ("Authorize only the two financial operations", vault.functions.authorizeMvpSession(session, 3,
            int(cfg["session_swap_usd_e8"]), int(cfg["session_payment_usdc"]), cfg["max_actions"], cfg["rebalance_cooldown_seconds"])),
    ]
    return {"status":"OWNER_REVIEW_REQUIRED", "broadcast":False, "owner_key_accessed":False,
        "chain_id":manifest.chain_id, "source_block":h.number, "owner_start_nonce":nonce,
        "predicted_vault":manifest.treasury, "predicted_adapter":manifest.adapter,
        "existing_roles":{r:getattr(manifest, r) for r in ("owner", "attestor", "relayer")},
        "session_id":session, "draft_policy_expires_at":expiry, "config":cfg,
        "transactions":[{"label":label, "owner_signature_required":True, "transaction":{
            "chainId":manifest.chain_id, "from":owner, "to":vault.address, "nonce":nonce+i,
            "value":"0x0", "data":fn._encode_transaction_data()}} for i, (label, fn) in enumerate(functions)],
        "next_steps":["Stop new requests; resolve pending journals before Owner policy rotation",
            "Owner reviews and signs this bundle outside serving; no thresholds/payees/daily counters are reset",
            "Run seal_mvp_manifest.py --plan <this bundle> after inclusion, then Owner signs the new manifest",
            "Install signed manifest atomically and restart the single backend, preserving all persistent data"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--rpc", default=PUBLIC_RPC)
    p.add_argument("--config", type=Path, default=ROOT / "fixtures/mvp/OWNER_REVIEW_REQUIRED.json")
    p.add_argument("--output", type=Path, default=ROOT / "data/mvp-owner-renewal.json")
    args = p.parse_args()
    w3 = evm_web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout":20}))
    result = prepare(w3, MvpManifest.model_validate_json(args.manifest.read_bytes()), json.loads(args.config.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"broadcast":False, "owner_transactions":3, "bundle":str(args.output), "session_id":result["session_id"]}))


if __name__ == "__main__":
    main()
