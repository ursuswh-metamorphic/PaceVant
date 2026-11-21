"""Operator-only Fuji demo recycling and seven-day renewal. Default is read-only.

Run with the web worker stopped and pending submissions reconciled. Private keys
stay on the operator machine. Retrying a batch reuses its original signed bytes.
USDC returns/top-ups never reset the contract's daily spend counters.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values
from eth_account import Account
from filelock import FileLock
from prepare_mvp_renewal import prepare
from web3 import Web3

from treasury_backend.modules.execution.chain import contract
from treasury_backend.operations.env import PUBLIC_RPC, atomic_json
from treasury_backend.operations.owner_transactions import send_owner_transaction
from treasury_backend.paths import ROOT
from treasury_contracts.mvp import MvpManifest
from treasury_contracts.rpc import evm_web3


def inventory(w3, manifest, vault, token, *, minimum_block=0):
    height = w3.eth.block_number
    until = time.monotonic()+60
    while height < minimum_block:
        if time.monotonic() >= until:
            raise ValueError("CONFIRMATION_BLOCK_PENDING_REUSE_JOURNAL")
        time.sleep(1)
        height = w3.eth.block_number
    session = vault.functions.sessions(manifest.default_session_id).call(block_identifier=height)
    return {"block": height, "session_expires_at": session[2],
        "authority": list(vault.functions.authorities(manifest.default_session_id).call(block_identifier=height)),
        "spend_scope": list(vault.functions.spendScopes(manifest.default_session_id).call(block_identifier=height)),
        "wallets": {role: {"address": getattr(manifest, role),
            "usdc_base_units": str(token.functions.balanceOf(Web3.to_checksum_address(getattr(manifest, role))).call(block_identifier=height)),
            "avax_wei": str(w3.eth.get_balance(Web3.to_checksum_address(getattr(manifest, role)), height))}
            for role in ("treasury", "owner", "attestor", "relayer")}}


def maintain(args):
    manifest = MvpManifest.model_validate_json(args.manifest.read_bytes())
    manifest.verify_owner()
    w3 = evm_web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 20}))
    if manifest.environment != "REAL_FUJI_EXECUTION" or w3.eth.chain_id != 43113 or w3.client_version.lower().startswith("anvil"):
        raise ValueError("PUBLIC_FUJI_REQUIRED")
    for name, expected in manifest.code_hashes.items():
        if Web3.to_hex(Web3.keccak(w3.eth.get_code(Web3.to_checksum_address(getattr(manifest, name))))) != expected:
            raise ValueError("CODE_IDENTITY_CHANGED")
    vault = contract(w3, "PolicyVaultMVP", manifest.treasury)
    token = contract(w3, "MockUSDC", manifest.usdc)
    if vault.functions.owner().call().lower() != manifest.owner or token.functions.decimals().call() != 6:
        raise ValueError("REGISTRY_MISMATCH")
    before = inventory(w3, manifest, vault, token)
    batch_file = args.journal / "batch.json"
    if batch_file.exists():
        batch = json.loads(batch_file.read_text())
        if batch["treasury"] != manifest.treasury or batch["renew_requested"] != args.renew:
            raise ValueError("BATCH_IDENTITY_MISMATCH")
    else:
        # These two demo accounts were provisioned with exactly 20 test USDC.
        # Return only their subsequent demo payment receipts, keeping reserves.
        transfers = []
        balance = int(before["wallets"]["treasury"]["usdc_base_units"])
        for role in ("attestor", "relayer"):
            excess = max(0, int(before["wallets"][role]["usdc_base_units"]) - 20_000_000)
            if excess > 1_000_000:
                raise ValueError("DEMO_RECEIPTS_EXCEED_REVIEWED_CAP")
            if excess:
                transfers.append({"role": role, "amount": excess})
                balance += excess
        topup = max(0, 5_000_000 - balance)
        if topup:
            transfers.append({"role": "owner", "amount": topup})
        if args.renew:
            # Preserve all current policy limits; grant a bounded weekly budget.
            scope = vault.functions.spendScopes(manifest.default_session_id).call()
            auth = vault.functions.authorities(manifest.default_session_id).call()
            renewal = prepare(w3, manifest, {"owner_reviewed": True, "session_duration_seconds": 604800,
                "session_swap_usd_e8": str(scope[0]), "session_payment_usdc": "5000000",
                "max_actions": auth[3], "rebalance_cooldown_seconds": auth[5]})
        else:
            renewal = None
        batch = {"chain_id": 43113, "treasury": manifest.treasury, "before": before,
            "renew_requested": args.renew, "transfers": transfers, "renewal": renewal}
    if not args.broadcast:
        return {"status": "READ_ONLY_PLAN", "broadcast": False, **batch}
    args.journal.mkdir(parents=True, exist_ok=True)
    atomic_json(batch_file, batch)
    env = dotenv_values(args.env)
    accounts = {role: Account.from_key(env[key]) for role, key in (
        ("owner", "B_FUJI_OWNER_PRIVATE_KEY"), ("attestor", "PACEVANT_ATTESTOR_KEY"), ("relayer", "B_FUJI_RELAYER_PRIVATE_KEY"))}
    del env
    if any(account.address.lower() != getattr(manifest, role) for role, account in accounts.items()):
        raise ValueError("SIGNER_IDENTITY_MISMATCH")
    profile = SimpleNamespace(control_data=args.journal, chain_id=43113)
    scope_id = hashlib.sha256(json.dumps(batch, sort_keys=True).encode()).hexdigest()
    receipts = []

    def send(role, label, to, data):
        account = accounts[role]
        def build():
            nonce = w3.eth.get_transaction_count(account.address, "pending")
            if nonce != w3.eth.get_transaction_count(account.address, "latest"):
                raise ValueError("SIGNER_HAS_PENDING_TRANSACTION")
            price = w3.eth.gas_price
            tx = {"from": account.address, "to": Web3.to_checksum_address(to), "value": 0,
                "data": data, "nonce": nonce, "chainId": 43113, "gasPrice": price}
            tx["gas"] = w3.eth.estimate_gas(tx)*12//10 + 10000
            if not 0 < price <= 5_000_000_000 or tx["gas"]*price > 1_000_000_000_000_000:
                raise ValueError("GAS_CAP_EXCEEDED")
            return tx
        receipt = send_owner_transaction(profile, w3, account, scope_id, label, build)
        canonical = w3.eth.get_transaction_receipt(receipt["tx_hash"])
        if w3.eth.get_block(canonical.blockNumber).hash != canonical.blockHash:
            raise ValueError("REORG_REQUIRES_REVIEW")
        receipts.append({"role": role, "step": label, **receipt})

    for transfer in batch["transfers"]:
        role, amount = transfer["role"], transfer["amount"]
        send(role, "recycle-"+role, token.address, token.functions.transfer(vault.address, amount)._encode_transaction_data())
    renewal = batch["renewal"]
    if renewal:
        for label, entry in zip(("renew-policy", "create-session", "authorize-session"), renewal["transactions"], strict=True):
            tx = entry["transaction"]
            if tx["to"].lower() != manifest.treasury or tx["chainId"] != 43113 or int(tx["value"], 16) != 0:
                raise ValueError("RENEWAL_TARGET_MISMATCH")
            send("owner", label, tx["to"], tx["data"])
        session = vault.functions.sessions(renewal["session_id"]).call()
        if not session[5] or session[0] != vault.functions.activePolicyHash().call():
            raise ValueError("NEW_SESSION_NOT_ACTIVE")
        manifest = manifest.model_copy(update={"default_session_id": renewal["session_id"], "owner_signature": "0x"})
        manifest = manifest.model_copy(update={"owner_signature": Web3.to_hex(accounts["owner"].sign_message(manifest.signing_message()).signature)})
        manifest.verify_owner()
        atomic_json(args.manifest, manifest.model_dump(mode="json"))
    after = inventory(w3, manifest, vault, token, minimum_block=max((r["block"] for r in receipts), default=0)+1)
    expected_balance = int(batch["before"]["wallets"]["treasury"]["usdc_base_units"])+sum(t["amount"] for t in batch["transfers"])
    if int(after["wallets"]["treasury"]["usdc_base_units"]) != expected_balance:
        raise ValueError("TREASURY_ACTUAL_RECEIPT_MISMATCH")
    result = {"status": "CONFIRMED", "broadcast": True, "chain_id": 43113,
        "before": batch["before"], "after": after, "transactions": receipts,
        "session_id": manifest.default_session_id, "owner_key_on_server": False,
        "scope": "Operator demo-fund recycling/top-up and bounded session renewal; no economic thresholds or daily counters changed"}
    atomic_json(args.output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT/"deployments/mvp-fuji.json")
    parser.add_argument("--env", type=Path, default=ROOT/".env")
    parser.add_argument("--rpc", default=PUBLIC_RPC)
    parser.add_argument("--journal", type=Path, required=True, help="Reuse the same directory on retry")
    parser.add_argument("--output", type=Path, default=ROOT/"docs/audit/demo-week-maintenance-20261121.json")
    parser.add_argument("--renew", action="store_true")
    parser.add_argument("--broadcast", action="store_true")
    args = parser.parse_args()
    args.journal.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(args.journal)+".lock", timeout=0):
        result = maintain(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
