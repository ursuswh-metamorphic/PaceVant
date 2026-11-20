"""Owner-authorized operator housekeeping, not an AI financial operation.

Only Fuji, the retired demo source, and the existing Owner/Relayer are supported.
Default is read-only. --broadcast moves tokens to Owner, 0.02 AVAX to Owner,
then all remaining native AVAX after its exact EOA transfer fee to Relayer.
No Owner/Attestor/Relayer private key is read. Each signed send is journaled first.
"""

import argparse
import io
import json
import os
import time
from pathlib import Path

from dotenv import dotenv_values
from eth_account import Account
from web3 import Web3
from web3.exceptions import TransactionNotFound

from treasury_backend.modules.execution.chain import contract
from treasury_backend.operations.env import PUBLIC_RPC
from treasury_backend.paths import ROOT
from treasury_contracts.rpc import evm_web3

SOURCE = "0xf23bE4A69B162DdC0F7D5456172212d294b233c7"
OWNER_AVAX_WEI = 20_000_000_000_000_000
MAX_GAS_PRICE_WEI = 5_000_000_000
MAX_TX_FEE_WEI = 1_000_000_000_000_000


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def execute(args):
    old = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text())
    w3 = evm_web3(Web3.HTTPProvider(PUBLIC_RPC, request_kwargs={"timeout": 20}))
    if w3.eth.chain_id != 43113:
        raise ValueError("CHAIN_MISMATCH")
    owner, relayer = old["owner"], old["relayer"]
    if len({SOURCE.lower(), owner.lower(), relayer.lower()}) != 3:
        raise ValueError("WALLET_ROLE_MISMATCH")
    if any(w3.eth.get_code(a) for a in (SOURCE, owner, relayer)):
        raise ValueError("EOA_REQUIRED")
    tokens = {}
    for label, field, code_name, decimals in (
        ("USDC", "token_in", "USDC", 6), ("WAVAX", "token_out", "WAVAX", 18)
    ):
        token = contract(w3, "MockUSDC", old[field])
        if (Web3.to_hex(Web3.keccak(w3.eth.get_code(token.address))) != old["bytecode_hashes"][code_name]
                or token.functions.decimals().call() != decimals):
            raise ValueError("TOKEN_IDENTITY_MISMATCH")
        tokens[label] = token

    def balances():
        height = w3.eth.block_number
        return {"block": height, "wallets": {
            role: {"address": address, "avax_wei": str(w3.eth.get_balance(address, height)),
                   **{label.lower() + "_base_units": str(t.functions.balanceOf(address).call(block_identifier=height))
                      for label, t in tokens.items()}}
            for role, address in (("retired_demo", SOURCE), ("owner", owner), ("relayer", relayer))}}

    snapshot = balances()
    if not args.broadcast:
        return {"status": "READ_ONLY_PLAN", "broadcast": False, "chain_id": 43113, "before": snapshot,
                "allocation": {"all_usdc_and_wavax": owner, "owner_avax_wei": str(OWNER_AVAX_WEI),
                               "remaining_avax_after_fees": relayer}}
    selected = []
    with args.env_file.open(encoding="utf-8-sig") as source:
        for line in source:
            if line.partition("=")[0].strip() == "TREASURY_DEMO_USER_PRIVATE_KEY":
                selected.append(line)
    values = dotenv_values(stream=io.StringIO("".join(selected)), interpolate=False)
    key = values.get("TREASURY_DEMO_USER_PRIVATE_KEY")
    if not key:
        raise ValueError("DEMO_SOURCE_KEY_NOT_CONFIGURED")
    account = Account.from_key(key)
    del key, values, selected
    if account.address.lower() != SOURCE.lower():
        raise ValueError("DEMO_SOURCE_KEY_ADDRESS_MISMATCH")
    journal = json.loads(args.journal.read_text()) if args.journal.exists() else {
        "chain_id": 43113, "source": SOURCE, "owner": owner, "relayer": relayer,
        "before": snapshot, "steps": {}}
    if any(journal[k] != expected for k, expected in (
        ("chain_id", 43113), ("source", SOURCE), ("owner", owner), ("relayer", relayer)
    )):
        raise ValueError("JOURNAL_IDENTITY_MISMATCH")
    save(args.journal, journal)

    def confirmed(step):
        entry = journal["steps"][step]
        try:
            receipt = w3.eth.wait_for_transaction_receipt(entry["tx_hash"], timeout=60)
        except Exception:
            raise ValueError("BROADCAST_UNCERTAIN_REUSE_EXISTING_JOURNAL") from None
        if receipt.status != 1:
            raise ValueError("ON_CHAIN_REVERT_STOPPED")
        until = time.monotonic() + 60
        while w3.eth.block_number < receipt.blockNumber + 1:
            if time.monotonic() >= until:
                raise ValueError("CONFIRMATIONS_PENDING_REUSE_EXISTING_JOURNAL")
            time.sleep(1)
        if w3.eth.get_block(receipt.blockNumber).hash != receipt.blockHash:
            raise ValueError("REORG_STOPPED")
        tx = w3.eth.get_transaction(entry["tx_hash"])
        if (tx["from"].lower() != SOURCE.lower() or tx["to"].lower() != entry["to"].lower()
                or tx["nonce"] != entry["nonce"] or tx["value"] != int(entry["value_wei"])
                or Web3.to_hex(tx["input"]) != entry["data"]):
            raise ValueError("RECEIPT_TRANSACTION_MISMATCH")
        entry.update(status="CONFIRMED", block=receipt.blockNumber, block_hash=Web3.to_hex(receipt.blockHash),
                     gas_used=str(receipt.gasUsed), actual_fee_wei=str(receipt.gasUsed * receipt.effectiveGasPrice),
                     confirmations=w3.eth.block_number - receipt.blockNumber + 1)
        save(args.journal, journal)

    def send(step, to, value, data="0x", gas=None, gas_price=None):
        if step in journal["steps"]:
            confirmed(step)
            return
        nonce = w3.eth.get_transaction_count(SOURCE, "pending")
        if nonce != w3.eth.get_transaction_count(SOURCE, "latest"):
            raise ValueError("SOURCE_HAS_PENDING_TRANSACTION")
        price = gas_price if gas_price is not None else w3.eth.gas_price
        if not 0 < price <= MAX_GAS_PRICE_WEI:
            raise ValueError("GAS_PRICE_LIMIT")
        tx = {"chainId": 43113, "from": SOURCE, "to": to, "value": value,
              "data": data, "nonce": nonce, "gasPrice": price}
        gas = gas or (w3.eth.estimate_gas(tx) * 12 // 10 + 10000)
        if gas > 1_500_000 or gas * price > MAX_TX_FEE_WEI:
            raise ValueError("TRANSACTION_FEE_LIMIT")
        if w3.eth.get_balance(SOURCE, "pending") < value + gas * price:
            raise ValueError("SOURCE_GAS_INSUFFICIENT")
        tx["gas"] = gas
        signed = account.sign_transaction(tx)
        entry = {"tx_hash": Web3.to_hex(signed.hash), "to": to, "nonce": nonce,
                 "value_wei": str(value), "data": data, "raw_tx": Web3.to_hex(signed.raw_transaction),
                 "status": "JOURNALED_BEFORE_BROADCAST"}
        journal["steps"][step] = entry
        save(args.journal, journal)
        try:
            w3.eth.send_raw_transaction(signed.raw_transaction)
        except Exception:
            try:
                w3.eth.get_transaction(entry["tx_hash"])
            except TransactionNotFound:
                raise ValueError("BROADCAST_UNCERTAIN_REUSE_EXISTING_JOURNAL") from None
        confirmed(step)

    for label, token in tokens.items():
        step = label.lower() + "_to_owner"
        if step in journal["steps"]:
            confirmed(step)
            continue
        amount = token.functions.balanceOf(SOURCE).call()
        if amount:
            previous_source = amount
            previous_owner = token.functions.balanceOf(owner).call()
            fn = token.functions.transfer(owner, amount)
            send(step, token.address, 0, fn._encode_transaction_data())
            if (token.functions.balanceOf(SOURCE).call() != 0
                    or token.functions.balanceOf(owner).call() - previous_owner != previous_source):
                raise ValueError("TOKEN_ACTUAL_RECEIPT_MISMATCH")
            journal["steps"][step]["token_amount_base_units"] = str(amount)
            save(args.journal, journal)
    send("avax_to_owner", owner, OWNER_AVAX_WEI, gas=21000)
    if "avax_to_relayer" in journal["steps"]:
        confirmed("avax_to_relayer")
    else:
        # An EOA-to-EOA transfer uses exactly 21000 gas. Pin the same gas price
        # used for calculating the drain, rather than re-quoting inside send.
        original_price = w3.eth.gas_price
        if not 0 < original_price <= MAX_GAS_PRICE_WEI:
            raise ValueError("GAS_PRICE_LIMIT")
        balance = w3.eth.get_balance(SOURCE, "pending")
        value = balance - 21000 * original_price
        if value <= 0:
            raise ValueError("INSUFFICIENT_NATIVE_FOR_DRAIN")
        send("avax_to_relayer", relayer, value, gas=21000, gas_price=original_price)
    after = balances()
    source_after = after["wallets"]["retired_demo"]
    result = {"status": "CONFIRMED", "environment": "REAL_FUJI_EXECUTION", "broadcast": True,
              "chain_id": 43113, "scope": "Retired demo wallet consolidation; not an AI PolicyVault operation",
              "before": journal["before"], "after": after,
              "transactions": [{k: v for k, v in e.items() if k not in {"raw_tx", "data"}}
                               | {"step": s} for s, e in journal["steps"].items()],
              "all_known_source_assets_zero": all(source_after[k] == "0" for k in (
                  "avax_wei", "usdc_base_units", "wavax_base_units"))}
    if not result["all_known_source_assets_zero"]:
        result["status"] = "RESIDUAL_BALANCE_REQUIRES_REVIEW"
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broadcast", action="store_true")
    p.add_argument("--env-file", type=Path, default=ROOT / ".env")
    p.add_argument("--journal", type=Path, default=ROOT / "data/mvp-demo-consolidation-journal.json")
    p.add_argument("--output", type=Path, default=ROOT / "docs/audit/mvp-demo-funds-consolidation.json")
    args = p.parse_args()
    try:
        result = execute(args)
    except Exception as exc:
        message = str(exc)
        safe = message if len(message) <= 100 and message.replace("_", "").isalnum() and message.isupper() else type(exc).__name__
        result = {"status": "STOPPED_REVIEW_JOURNAL", "reason": safe, "broadcast_requested": args.broadcast}
    if args.broadcast:
        save(args.output, result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"CONFIRMED", "READ_ONLY_PLAN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
