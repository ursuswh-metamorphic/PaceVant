"""READ-ONLY post-deployment manifest verification. Owner signs outside this process."""

import argparse
import json
from pathlib import Path

from web3 import Web3

from treasury_backend.modules.execution.chain import contract
from treasury_backend.paths import ROOT
from treasury_contracts.crypto import content_hash
from treasury_contracts.mvp import MvpManifest
from treasury_contracts.rpc import evm_web3


def inspect_manifest(w3, plan):
    if w3.eth.chain_id != plan["chain_id"]:
        raise ValueError("CHAIN_MISMATCH")
    v = contract(w3, "PolicyVaultMVP", plan["predicted_vault"])
    if not w3.eth.get_code(v.address):
        raise ValueError("MVP_NOT_DEPLOYED")
    roles = plan["existing_roles"]
    for role in ("owner", "attestor"):
        if getattr(v.functions, role)().call().lower() != roles[role].lower():
            raise ValueError("SYSTEM_ROLE_MISMATCH")
    if v.functions.proofAdapter().call().lower() != plan["predicted_adapter"].lower():
        raise ValueError("ADAPTER_MISMATCH")
    session = v.functions.sessions(plan["session_id"]).call()
    if not session[5] or session[0] != v.functions.activePolicyHash().call():
        raise ValueError("SESSION_NOT_ACTIVE")
    ids = {
        "treasury": v.address,
        "usdc": v.functions.usdc().call(),
        "wavax": v.functions.wavax().call(),
        "adapter": plan["predicted_adapter"],
    }
    if any(not w3.eth.get_code(Web3.to_checksum_address(address)) for address in ids.values()):
        raise ValueError("CONTRACT_CODE_MISSING")
    return MvpManifest(
        environment="REAL_FUJI_EXECUTION" if w3.eth.chain_id == 43113 else "LOCAL_TEST",
        chain_id=w3.eth.chain_id,
        **ids,
        **roles,
        default_session_id=plan["session_id"],
        payee_candidates=(roles["owner"],),
        max_daily_execution_cost_usd_e8=plan["config"]["max_daily_execution_cost_usd_e8"],
        code_hashes={
            name: Web3.to_hex(Web3.keccak(w3.eth.get_code(Web3.to_checksum_address(address))))
            for name, address in ids.items()
        },
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rpc", default="https://api.avax-test.network/ext/bc/C/rpc")
    p.add_argument(
        "--plan", type=Path, default=ROOT / "docs/audit/mvp-unsigned-migration-plan.json"
    )
    p.add_argument("--owner-signature", default="0x")
    p.add_argument("--output", type=Path, default=ROOT / "data/mvp-manifest.json")
    args = p.parse_args()
    w3 = evm_web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 20}))
    m = inspect_manifest(w3, json.loads(args.plan.read_text(encoding="utf-8")))
    message = "PACEVANT_MVP_MANIFEST:" + content_hash(
        m.model_dump(mode="json", exclude={"owner_signature"})
    )
    if args.owner_signature != "0x":
        m = m.model_copy(update={"owner_signature": args.owner_signature})
        m.verify_owner()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(m.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "broadcast": False,
                "owner_key_accessed": False,
                "manifest": str(args.output),
                "owner": m.owner,
                "owner_signing_message": message,
                "ready": args.owner_signature != "0x",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
