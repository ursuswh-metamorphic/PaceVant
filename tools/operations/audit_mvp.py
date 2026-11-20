"""Read-only public Fuji inventory. Never loads .env, signs, or sends transactions."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from web3 import Web3

from treasury_backend.modules.execution.chain import contract
from treasury_backend.modules.execution.dex.lfj import LFJClient
from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
from treasury_backend.paths import ROOT
from treasury_contracts.rpc import evm_web3


def audit(rpc_url):
    manifest = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text(encoding="utf-8"))
    w3 = evm_web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if w3.eth.chain_id != 43113:
        raise ValueError("CHAIN_MISMATCH")
    block = w3.eth.get_block("latest")
    n = block.number
    addresses = {role: manifest[role] for role in ("owner", "attestor", "relayer")}
    addresses["policy_vault"] = manifest["vault_address"]
    usdc = contract(w3, "MockUSDC", manifest["token_in"])
    wavax = contract(w3, "MockWAVAX", manifest["token_out"])
    vault = contract(w3, "PolicyVault", manifest["vault_address"])
    result = {
        "source": "PUBLIC_FUJI_READ_ONLY",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "chain_id": 43113,
        "block_number": n,
        "block_hash": Web3.to_hex(block.hash),
        "broadcast": False,
        "accounts": {},
        "code_identity": {},
        "roles_match_manifest": True,
    }
    for role, address in addresses.items():
        result["accounts"][role] = {
            "address": address,
            "native_avax_wei": str(w3.eth.get_balance(address, n)),
            "usdc_base_units": str(usdc.functions.balanceOf(address).call(block_identifier=n)),
            "wavax_base_units": str(wavax.functions.balanceOf(address).call(block_identifier=n)),
            "is_eoa": len(w3.eth.get_code(address, n)) == 0,
        }
    for role in ("owner", "attestor"):
        result["roles_match_manifest"] &= (
            getattr(vault.functions, role)().call(block_identifier=n).lower()
            == addresses[role].lower()
        )
    result["three_distinct_eoas"] = (
        len({addresses[r].lower() for r in ("owner", "attestor", "relayer")}) == 3
    )
    for name, address in (
        ("PolicyVault", addresses["policy_vault"]),
        ("LFJSwapAdapter", manifest["router"]),
        ("USDC", manifest["token_in"]),
        ("WAVAX", manifest["token_out"]),
    ):
        actual = Web3.to_hex(Web3.keccak(w3.eth.get_code(address, n)))
        result["code_identity"][name] = {
            "actual_hash": actual,
            "manifest_hash": manifest["bytecode_hashes"][name],
            "matches": actual == manifest["bytecode_hashes"][name],
        }
    fields = (
        "paused",
        "policyActive",
        "activePolicyHash",
        "policyVersion",
        "policyExpiresAt",
        "maxApprovalTtl",
        "maxPerSwap",
        "maxSpendPerDay",
    )
    result["policy"] = {
        name: getattr(vault.functions, name)().call(block_identifier=n) for name in fields
    }
    result["policy"]["activePolicyHash"] = Web3.to_hex(result["policy"]["activePolicyHash"])
    from treasury_backend.modules.execution.v3.context import PROOF_KEYS

    proof = dict(
        zip(PROOF_KEYS, vault.functions.proofPolicy().call(block_identifier=n), strict=True)
    )
    proof["oracle_source_hash"] = Web3.to_hex(proof["oracle_source_hash"])
    result["proof_policy"] = {
        k: str(v) if isinstance(v, int) and not isinstance(v, bool) and v > 2**53 - 1 else v
        for k, v in proof.items()
    }
    s = vault.functions.sessions(manifest["session_id"]).call(block_identifier=n)
    result["session"] = {
        "id": manifest["session_id"],
        "policy_hash": Web3.to_hex(s[0]),
        "starts_at": s[1],
        "expires_at": s[2],
        "risk_limit_usd_e8": str(s[3]),
        "risk_used_usd_e8": str(s[4]),
        "active": s[5],
        "currently_authorized": s[5]
        and s[1] <= block.timestamp < s[2]
        and s[0] == vault.functions.activePolicyHash().call(block_identifier=n),
    }
    route = LFJClient(w3, manifest["token_in"]).v1_route(n)
    result["lfj_route"] = route
    result["token_decimals"] = {
        "USDC": usdc.functions.decimals().call(block_identifier=n),
        "WAVAX": wavax.functions.decimals().call(block_identifier=n),
    }
    adapter = contract(w3, "LFJSwapAdapter", manifest["router"])
    try:
        reverse = adapter.functions.quote(wavax.address, usdc.address, 10**12).call(
            block_identifier=n
        )
        result["reverse_adapter_probe"] = {"supported": True, "quote": str(reverse)}
    except Exception:
        result["reverse_adapter_probe"] = {
            "supported": False,
            "reason": "DEPLOYED_ADAPTER_REVERTS_REVERSE_QUOTE",
        }
    try:
        result["oracle"] = (
            ChainlinkPriceProvider(rpc_url, vault.address).read(n).model_dump(mode="json")
        )
        ri, ro = map(int, route["reserves"])
        if route["token0"].lower() != usdc.address.lower():
            ri, ro = ro, ri
        amount = 10**15
        quote = amount * 997 * ri // (ro * 1000 + amount * 997)
        from fractions import Fraction

        fair = Fraction(
            amount * int(result["oracle"]["price_wavax_usd_e8"]) * 10**6,
            10**18 * int(result["oracle"]["price_usdc_usd_e8"]),
        )
        result["reverse_economic_reference"] = {
            "amount_wavax_base_units": str(amount),
            "pool_quote_usdc_base_units": str(quote),
            "chainlink_fair_usdc_base_units_floor": str(fair.numerator // fair.denominator),
            "relative_loss_bps_floor": str(int((1 - Fraction(quote, 1) / fair) * 10000)),
            "within_owner_relative_loss_limit": quote * 10000
            >= fair * (10000 - proof["max_relative_loss_bps"]),
        }
    except Exception as exc:
        result["oracle"] = {
            "status": "UNVERIFIED",
            "reason": getattr(exc, "code", "RPC_OR_ORACLE_UNAVAILABLE"),
        }
    if w3.eth.get_block(n).hash != block.hash:
        raise ValueError("REORG_DURING_AUDIT")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rpc", default="https://api.avax-test.network/ext/bc/C/rpc")
    p.add_argument("--output", type=Path, default=ROOT / "docs/audit/mvp-public-state.json")
    args = p.parse_args()
    try:
        result = audit(args.rpc)
    except Exception as exc:
        result = {
            "source": "PUBLIC_FUJI_READ_ONLY",
            "status": "UNVERIFIED",
            "broadcast": False,
            "reason": getattr(exc, "code", type(exc).__name__),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
