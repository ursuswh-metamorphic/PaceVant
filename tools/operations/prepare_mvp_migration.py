"""READ-ONLY unsigned migration plan. No owner key argument, wallet loading or broadcast code."""

import argparse
import json
from pathlib import Path

import rlp
from web3 import Web3

from treasury_backend.modules.execution.chain import artifact, contract
from treasury_backend.modules.execution.dex.lfj import LFJClient
from treasury_backend.paths import ROOT
from treasury_contracts.crypto import content_hash
from treasury_contracts.rpc import evm_web3


def predicted(owner, nonce):
    return Web3.to_checksum_address(
        Web3.keccak(rlp.encode([bytes.fromhex(owner[2:]), nonce]))[-20:]
    )


def prepare(w3, cfg):
    if w3.eth.chain_id != 43113:
        raise ValueError("CHAIN_MISMATCH")
    old = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text())
    owner = Web3.to_checksum_address(old["owner"])
    vault = contract(w3, "PolicyVault", old["vault_address"])
    h = w3.eth.get_block("latest")
    n = h.number
    for name, address in (
        ("PolicyVault", old["vault_address"]),
        ("LFJSwapAdapter", old["router"]),
        ("USDC", old["token_in"]),
        ("WAVAX", old["token_out"]),
    ):
        if Web3.to_hex(Web3.keccak(w3.eth.get_code(address, n))) != old["bytecode_hashes"][name]:
            raise ValueError("SOURCE_CODE_IDENTITY_CHANGED")
    if vault.functions.owner().call(block_identifier=n).lower() != owner.lower():
        raise ValueError("OWNER_MISMATCH")
    route = LFJClient(w3, old["token_in"]).v1_route(n)
    first = w3.eth.get_transaction_count(owner, "pending")
    # Revoke current session and pause first. Every transaction still requires owner signature.
    new_vault = predicted(owner, first + 2)
    new_adapter = predicted(owner, first + 3)
    mv = w3.eth.contract(address=new_vault, abi=artifact("PolicyVaultMVP")["abi"])
    txs = []

    def add(label, to, data):
        txs.append(
            {
                "label": label,
                "transaction": {
                    "from": owner,
                    "to": to,
                    "chainId": 43113,
                    "nonce": first + len(txs),
                    "value": "0x0",
                    "data": data,
                },
                "owner_signature_required": True,
            }
        )

    def call(label, fn):
        add(label, fn.address, fn._encode_transaction_data())

    call("Revoke old active session", vault.functions.revokeSession(old["session_id"]))
    call("Pause old vault", vault.functions.pause())
    for name, args, label in (
        (
            "PolicyVaultMVP",
            (owner, old["attestor"], old["token_in"], old["token_out"]),
            "Deploy two-operation vault",
        ),
        (
            "LFJSwapAdapterV3",
            (new_vault, route["lfj_router"], route["pair"], old["token_in"], old["token_out"]),
            "Deploy bidirectional direct V1 adapter",
        ),
    ):
        a = artifact(name)
        factory = w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"]["object"])
        add(label, None, factory.constructor(*args).data_in_transaction)
    call("Allow exact new adapter", mv.functions.setRouter(new_adapter, True))
    proof = list(vault.functions.proofPolicy().call(block_identifier=n))
    previous_reverse_cap = proof[0]
    proof[0] = int(cfg["max_wavax_per_swap"])
    call(
        "Preserve economic thresholds; explicitly approve reverse amount cap",
        mv.functions.configureProofPolicy(new_adapter, tuple(proof)),
    )
    call(
        "Preserve approval TTL",
        mv.functions.setApprovalTtl(vault.functions.maxApprovalTtl().call(block_identifier=n)),
    )
    call(
        "Configure separate swap/payment budgets",
        mv.functions.configureMVP(
            int(cfg["max_swap_usd_e8"]),
            int(cfg["daily_swap_usd_e8"]),
            int(cfg["max_payment_usdc"]),
            int(cfg["daily_payment_usdc"]),
            cfg["max_wavax_exposure_bps"],
        ),
    )
    call(
        "Approve existing Owner EOA as fixed payment receiver",
        mv.functions.setMvpPayee(
            owner,
            int(cfg["max_payment_usdc"]),
            int(cfg["recipient_session_usdc"]),
            int(cfg["recipient_daily_usdc"]),
        ),
    )
    duration = cfg.get("policy_duration_seconds", 86400)
    if not 60 <= cfg["session_duration_seconds"] <= duration <= 604800:
        raise ValueError("REVIEW_POLICY_SESSION_DURATION")
    expiry = h.timestamp + duration
    commitment = content_hash(
        {
            "MVP_OWNER_REVIEW": cfg,
            "source_vault": old["vault_address"],
            "source_block_hash": Web3.to_hex(h.hash),
        }
    )
    call(
        "Activate versioned MVP policy",
        mv.functions.configurePolicy(
            commitment,
            int(cfg["max_per_swap_usdc"]),
            int(cfg["max_usdc_daily_outflow"]),
            vault.functions.maxSlippageBps().call(block_identifier=n),
            expiry,
        ),
    )
    session = content_hash({"MVP_SESSION": new_vault, "source_block_hash": Web3.to_hex(h.hash)})
    call(
        "Create owner session",
        mv.functions.createSession(
            session, h.timestamp, h.timestamp + cfg["session_duration_seconds"], proof[6]
        ),
    )
    call(
        "Authorize only swap/payment/rebalance scope",
        mv.functions.authorizeMvpSession(
            session,
            19,
            int(cfg["session_swap_usd_e8"]),
            int(cfg["session_payment_usdc"]),
            cfg["max_actions"],
            cfg["rebalance_cooldown_seconds"],
        ),
    )
    u = contract(w3, "MockUSDC", old["token_in"])
    available = u.functions.balanceOf(owner).call(block_identifier=n)
    if int(cfg["fund_from_owner_usdc"]) > available:
        raise ValueError("OWNER_USDC_NOT_AVAILABLE")
    call(
        "Explicit owner funding (review separately)",
        u.functions.transfer(new_vault, int(cfg["fund_from_owner_usdc"])),
    )
    optional = []
    for token in (old["token_in"], old["token_out"]):
        t = contract(w3, "MockUSDC", token)
        balance = t.functions.balanceOf(vault.address).call(block_identifier=n)
        if balance:
            optional.append(
                {
                    "label": "Optional old-vault asset recovery after pause",
                    "token": token,
                    "amount": str(balance),
                    "to": vault.address,
                    "data": vault.functions.withdraw(
                        token, new_vault, balance
                    )._encode_transaction_data(),
                    "owner_signature_required": True,
                    "broadcast": False,
                }
            )
    return {
        "status": "OWNER_REVIEW_REQUIRED",
        "broadcast": False,
        "owner_key_accessed": False,
        "chain_id": 43113,
        "source_block": n,
        "source_block_hash": Web3.to_hex(h.hash),
        "owner_start_nonce": first,
        "existing_roles": {r: old[r] for r in ("owner", "attestor", "relayer")},
        "source_vault": old["vault_address"],
        "predicted_vault": new_vault,
        "predicted_adapter": new_adapter,
        "session_id": session,
        "draft_policy_expires_at": expiry,
        "explicit_policy_change": {
            "max_wavax_per_swap": {"old": str(previous_reverse_cap), "proposed": str(proof[0])}
        },
        "unchanged_economic_thresholds": True,
        "config": cfg,
        "transactions": txs,
        "optional_asset_recovery": optional,
        "activation_requirements": [
            "Recheck owner nonce; regenerate after any owner transaction or expiry",
            "Owner reviews and separately signs every transaction; this tool never sends",
            "Verify deployed code and all roles, policy/session/budgets after inclusion",
            "Create code-hash-pinned MvpManifest using ONLY these three existing roles",
            "Owner signs Manifest.signing_message() outside the serving process",
            "Install PACEVANT_MVP_MANIFEST_FILE and explicitly enable PACEVANT_MVP_LIVE_ENABLED=1",
            "Re-read balances, oracles and pool economics; do not relax failed gates",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rpc", default="https://api.avax-test.network/ext/bc/C/rpc")
    p.add_argument("--config", type=Path, default=ROOT / "fixtures/mvp/OWNER_REVIEW_REQUIRED.json")
    p.add_argument(
        "--output", type=Path, default=ROOT / "docs/audit/mvp-unsigned-migration-plan.json"
    )
    args = p.parse_args()
    cfg = json.loads(args.config.read_text())
    w3 = evm_web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 20}))
    result = prepare(w3, cfg)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "broadcast": False,
                "plan": str(args.output),
                "owner_transactions": len(result["transactions"]),
                "owner_start_nonce": result["owner_start_nonce"],
                "predicted_vault": result["predicted_vault"],
                "predicted_adapter": result["predicted_adapter"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
