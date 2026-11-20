"""Read-only MVP readiness, including the retired public demo wallet. No keys or broadcasts."""

import argparse
import json
import sys
from pathlib import Path

from web3 import Web3

from treasury_backend.modules.execution.chain import contract
from treasury_backend.modules.execution.dex.lfj import LFJClient
from treasury_backend.operations.env import PUBLIC_RPC
from treasury_backend.paths import ROOT
from treasury_contracts.rpc import evm_web3

sys.path.insert(0, str(ROOT))
from tools.operations.audit_mvp import audit  # noqa: E402

DEMO_ADDRESS = "0xf23bE4A69B162DdC0F7D5456172212d294b233c7"
HISTORICAL_SWAP = "0x315a9bff8ba111487d295903ebd0f6389b1baefd40ea9526fc33bc014a9656ba"


def inspect(rpc_url):
    result = audit(rpc_url)
    w3 = evm_web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    n = result["block_number"]
    old = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text())
    u = contract(w3, "MockUSDC", old["token_in"])
    w = contract(w3, "MockWAVAX", old["token_out"])
    result["accounts"]["retired_demo_wallet"] = {
        "address": DEMO_ADDRESS,
        "native_avax_wei": str(w3.eth.get_balance(DEMO_ADDRESS, n)),
        "usdc_base_units": str(u.functions.balanceOf(DEMO_ADDRESS).call(block_identifier=n)),
        "wavax_base_units": str(w.functions.balanceOf(DEMO_ADDRESS).call(block_identifier=n)),
        "is_eoa": not bool(w3.eth.get_code(DEMO_ADDRESS, n)),
        "system_role": False,
    }
    oracle = result["oracle"]
    if oracle.get("oracle_feeds"):
        h = w3.eth.get_block(n)
        avax = next(f for f in oracle["oracle_feeds"] if f["asset"] == old["token_out"].lower())
        result["mvp_signing_oracle_window"] = {
            "avax_round_age_seconds": h.timestamp - avax["updated_at"],
            "owner_max_age_seconds": result["proof_policy"]["max_oracle_age"],
            "within_owner_window_at_source_block": h.timestamp - avax["updated_at"]
            <= result["proof_policy"]["max_oracle_age"],
            "source": "UNMODIFIED_CHAINLINK_ROUND",
        }
    dex = LFJClient(w3, u.address)
    result["route_probes"] = []
    for reverse, amount in ((False, 1), (True, 10**15)):
        quote = dex.quote(amount, n, reverse=reverse)
        try:
            verified = dex.verified_quote(amount, n, result["lfj_route"], reverse=reverse)
            status, reason = "APPROVED_V1_ROUTE", None
            output = verified["amount_out_base_units"]
        except Exception as exc:
            status, reason, output = "REJECTED_BEFORE_BROADCAST", getattr(exc, "code", type(exc).__name__), None
        result["route_probes"].append({
            "direction": "WAVAX_TO_USDC" if reverse else "USDC_TO_WAVAX",
            "amount_in_base_units": str(amount), "status": status, "reason": reason,
            "selected_pairs": quote["pairs"], "selected_versions": quote["versions"],
            "approved_output_base_units": output,
        })
    receipt = w3.eth.get_transaction_receipt(HISTORICAL_SWAP)
    tx = w3.eth.get_transaction(HISTORICAL_SWAP)
    result["historical_public_swap"] = {
        "hash": HISTORICAL_SWAP, "block": receipt.blockNumber, "status": receipt.status,
        "canonical": w3.eth.get_block(receipt.blockNumber).hash == receipt.blockHash,
        "to": tx["to"], "sender": tx["from"], "gas_used": str(receipt.gasUsed),
        "scope": "Historical V2 forward swap; not the new MVP payment or reverse deployment",
    }
    plan_path = ROOT / "docs/audit/mvp-unsigned-migration-plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        result["proposed_mvp_contracts"] = {
            "status": "UNSIGNED_PREDICTIONS_ONLY",
            "vault": plan["predicted_vault"], "adapter": plan["predicted_adapter"],
            "vault_has_code": bool(w3.eth.get_code(plan["predicted_vault"], n)),
            "adapter_has_code": bool(w3.eth.get_code(plan["predicted_adapter"], n)),
        }
    if Web3.to_hex(w3.eth.get_block(n).hash) != result["block_hash"]:
        raise ValueError("REORG_DURING_AUDIT")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rpc", default=PUBLIC_RPC)
    p.add_argument("--output", type=Path, default=ROOT / "docs/audit/mvp-readiness-public-state.json")
    args = p.parse_args()
    result = inspect(args.rpc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "source": result["source"], "block": result["block_number"], "broadcast": False,
        "demo_wallet": result["accounts"]["retired_demo_wallet"],
        "oracle": result.get("mvp_signing_oracle_window", result["oracle"]),
        "routes": result["route_probes"], "proposed_mvp_contracts": result.get("proposed_mvp_contracts"),
        "historical_swap_verified": result["historical_public_swap"]["canonical"]
        and result["historical_public_swap"]["status"] == 1,
    }, indent=2))


if __name__ == "__main__":
    main()
