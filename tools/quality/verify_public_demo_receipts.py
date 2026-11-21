"""Independently reconcile the UI acceptance receipts with public Fuji ERC20 logs."""

import argparse
import json
from pathlib import Path

from web3 import Web3
from web3.logs import DISCARD

from treasury_backend.modules.execution.chain import contract
from treasury_backend.operations.env import PUBLIC_RPC
from treasury_contracts.mvp import MvpManifest
from treasury_contracts.rpc import evm_web3


def verify(args):
    report = json.loads(args.report.read_text())
    manifest = MvpManifest.model_validate_json(args.manifest.read_bytes())
    manifest.verify_owner()
    w3 = evm_web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 20}))
    if w3.eth.chain_id != 43113 or manifest.environment != "REAL_FUJI_EXECUTION":
        raise ValueError("PUBLIC_FUJI_REQUIRED")
    vault = contract(w3, "PolicyVaultMVP", manifest.treasury)
    tokens = [contract(w3, "MockUSDC", manifest.usdc), contract(w3, "MockWAVAX", manifest.wavax)]
    results = []
    for entry in report["normal"]:
        job = entry["job"]
        intent, outcome = job["workflow"]["intent"], job["workflow"]["outcome"]
        tx, receipt = w3.eth.get_transaction(outcome["tx_hash"]), w3.eth.get_transaction_receipt(outcome["tx_hash"])
        header = w3.eth.get_block(receipt.blockNumber)
        confirmations = w3.eth.block_number-receipt.blockNumber+1
        if (receipt.status != 1 or header.hash != receipt.blockHash or confirmations < 2
            or tx["to"].lower() != manifest.treasury or tx["from"].lower() != manifest.relayer):
            raise ValueError("CANONICAL_RECEIPT_BINDING_FAILED")
        function, arguments = vault.decode_function_input(tx["input"])
        operation = arguments["a"]
        if (function.fn_name != "executeOperation" or str(operation["amount"]) != intent["amount"]
            or operation["recipient"].lower() != intent["recipient"].lower()
            or Web3.to_hex(operation["sessionId"]) != intent["session_id"]):
            raise ValueError("EXACT_OPERATION_BINDING_FAILED")
        deltas = []
        payee_received = 0
        for index, token in enumerate(tokens):
            delta = 0
            for event in token.events.Transfer().process_receipt(receipt, errors=DISCARD):
                if event["address"].lower() != token.address.lower():
                    continue
                sender, recipient, amount = event["args"]["from"].lower(), event["args"]["to"].lower(), int(event["args"]["value"])
                delta += amount * (int(recipient == manifest.treasury)-int(sender == manifest.treasury))
                if index == 0 and sender == manifest.treasury and recipient == intent["recipient"].lower():
                    payee_received += amount
            deltas.append(delta)
        if deltas != list(map(int, outcome["actual_deltas"][:2])):
            raise ValueError("UI_ACTUAL_DELTA_MISMATCH")
        payment = entry["scenario"] == "payment"
        if deltas[0] != -int(intent["amount"]) or (payee_received != int(intent["amount"]) if payment else deltas[1] <= 0):
            raise ValueError("TOKEN_EFFECTS_MISMATCH")
        results.append({"scenario": entry["scenario"], "job_id": job["job_id"], "tx_hash": outcome["tx_hash"],
            "status": 1, "canonical": True, "confirmations": confirmations, "block": receipt.blockNumber,
            "vault_token_deltas": list(map(str, deltas)), "payee_received_usdc": str(payee_received),
            "gas_used": receipt.gasUsed, "actual_fee_wei": str(receipt.gasUsed*receipt.effectiveGasPrice),
            "session_id": intent["session_id"]})
    if {entry["scenario"] for entry in results} != {"payment", "swap"}:
        raise ValueError("BOTH_NORMAL_OPERATIONS_REQUIRED")
    result = {"status": "PASS", "source": "INDEPENDENT_PUBLIC_FUJI_RECEIPTS_AND_ERC20_LOGS", "chain_id": 43113, "transactions": results}
    args.output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("docs/audit/live-adversarial-20261121/report.json"))
    parser.add_argument("--manifest", type=Path, default=Path("deployments/mvp-fuji.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/audit/live-adversarial-20261121/chain-reconciliation.json"))
    parser.add_argument("--rpc", default=PUBLIC_RPC)
    print(json.dumps(verify(parser.parse_args()), indent=2))


if __name__ == "__main__":
    main()
