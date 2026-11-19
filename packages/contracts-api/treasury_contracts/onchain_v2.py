"""Block-pinned owner policy, registry and session facts (never an approval)."""

import json
from pathlib import Path

from web3 import Web3

from .v2 import ZERO_HASH, Asset, ProofPolicy, Registry, SessionContext
from .rpc import read_functions


def read_v2_context(w3, vault_address, session_id=ZERO_HASH, block="latest", required=False):
    abi = json.loads((Path(__file__).parent / "abi/PolicyVault.json").read_text())
    if isinstance(abi, dict):
        abi = abi["abi"]
    vault = w3.eth.contract(address=Web3.to_checksum_address(vault_address), abi=abi)
    header = w3.eth.get_block(block)
    n = header.number
    try:
        enabled = vault.functions.v2Enabled().call(block_identifier=n)
    except Exception:
        if required:
            raise ValueError("V2 deployment unavailable") from None
        return {}
    if not enabled:
        if required:
            raise ValueError("proof enforcement disabled")
        return {}
    p, usdc, wavax, config_hash, registry_hash, s, global_used = read_functions(w3, [
        vault.functions.proofPolicy(), vault.functions.usdc(), vault.functions.wavax(),
        vault.functions.v2ConfigHash(), vault.functions.trackedRegistryHash(),
        vault.functions.sessions(session_id), vault.functions.globalDailyRiskUsedUsdE8(header.timestamp // 86400),
    ], n)
    policy = ProofPolicy(
        max_wavax_per_swap=str(p[0]),
        max_relative_loss_bps=p[1],
        fixed_loss_usd_e8=str(p[2]),
        oracle_band_bps=p[3],
        tolerance_bps=p[4],
        max_oracle_age=p[5],
        max_session_risk_usd_e8=str(p[6]),
        global_daily_risk_usd_e8=str(p[7]),
        oracle_source_hash=Web3.to_hex(p[8]),
        authorization="OWNER_APPROVED" if p[9] else "TEST_ONLY",
    )
    assets = []
    for address, decimals in ((usdc, 6), (wavax, 18)):
        token = w3.eth.contract(
            address=address,
            abi=[
                {
                    "type": "function",
                    "name": "decimals",
                    "stateMutability": "view",
                    "inputs": [],
                    "outputs": [{"type": "uint8"}],
                }
            ],
        )
        if token.functions.decimals().call(block_identifier=n) != decimals:
            raise ValueError("registry decimals mismatch")
        assets.append(Asset(address=address, decimals=decimals))
    registry = Registry(assets=tuple(sorted(assets, key=lambda a: a.address)))
    if policy.hash != Web3.to_hex(config_hash):
        raise ValueError("proof config hash mismatch")
    if registry.hash != Web3.to_hex(registry_hash):
        raise ValueError("registry hash mismatch")
    session = SessionContext(
        session_id=session_id,
        policy_hash=Web3.to_hex(s[0]),
        starts_at=s[1],
        expires_at=s[2],
        limit_usd_e8=str(s[3]),
        used_usd_e8=str(s[4]),
        active=s[5],
        global_limit_usd_e8=policy.global_daily_risk_usd_e8,
        global_used_usd_e8=str(global_used),
        block_number=n,
        block_hash=Web3.to_hex(header.hash),
        timestamp=header.timestamp,
    )
    # Detect a reorg during multi-call snapshot collection.
    if w3.eth.get_block(n).hash != header.hash:
        raise ValueError("snapshot reorg")
    return dict(
        proof_policy=policy.model_dump(mode="json"),
        registry=registry.model_dump(mode="json"),
        proof_session=session.model_dump(mode="json"),
    )
