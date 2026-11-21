"""Small public source observation. This does not authorize a judge transaction."""

import json
from datetime import datetime, timezone

from web3 import Web3

from treasury_backend.modules.execution.chain import contract
from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
from treasury_backend.paths import ROOT
from treasury_contracts.rpc import evm_web3


def observe(rpc_url, manifest_file=None):
    old = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text())
    contract_name='PolicyVault'
    if manifest_file:
        from treasury_contracts.mvp import MvpManifest

        manifest=MvpManifest.model_validate(json.loads(manifest_file.read_text(encoding='utf-8')))
        manifest.verify_owner()
        if manifest.environment!='REAL_FUJI_EXECUTION':
            raise ValueError('PUBLIC_MANIFEST_REQUIRED')
        old={'vault_address':manifest.treasury,'token_in':manifest.usdc,'token_out':manifest.wavax,
            'owner':manifest.owner,'attestor':manifest.attestor,'relayer':manifest.relayer,
            'bytecode_hashes':{'PolicyVault':manifest.code_hashes['treasury']}}
        contract_name='PolicyVaultMVP'
    w3 = evm_web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout":5}))
    if w3.eth.chain_id != 43113:
        raise ValueError("CHAIN_MISMATCH")
    h = w3.eth.get_block("latest")
    n = h.number
    if Web3.to_hex(Web3.keccak(w3.eth.get_code(Web3.to_checksum_address(old["vault_address"]), n))) != old["bytecode_hashes"]["PolicyVault"]:
        raise ValueError("SOURCE_CODE_IDENTITY_CHANGED")
    vault = contract(w3, contract_name, old["vault_address"])
    usdc, wavax = contract(w3,"MockUSDC",old["token_in"]), contract(w3,"MockWAVAX",old["token_out"])
    proof = vault.functions.proofPolicy().call(block_identifier=n)
    oracle = {"status":"UNAVAILABLE", "source":"CHAINLINK_FUJI"}
    try:
        prices = ChainlinkPriceProvider(rpc_url, vault.address).read(n)
        avax = next(f for f in prices.oracle_feeds if f.asset == old["token_out"].lower())
        age = h.timestamp - avax.updated_at
        oracle.update(status="FRESH" if age <= proof[5] else "STALE_FOR_OWNER_WINDOW", updated_at=avax.updated_at, age_seconds=age)
    except Exception:
        pass
    result = {"status":"VERIFIED_READ", "observed_at":datetime.now(timezone.utc).isoformat(), "block_number":n, "chain_id":43113,
        "balances":{"usdc":str(usdc.functions.balanceOf(vault.address).call(block_identifier=n)),
                    "wavax":str(wavax.functions.balanceOf(vault.address).call(block_identifier=n))},
        "policy":{"paused":vault.functions.paused().call(block_identifier=n), "active":vault.functions.policyActive().call(block_identifier=n),
            "expires_at":vault.functions.policyExpiresAt().call(block_identifier=n), "max_relative_loss_bps":proof[1], "oracle_band_bps":proof[3]},
        "oracle":oracle, "addresses":{"treasury":old["vault_address"], **{r:old[r] for r in ("owner","attestor","relayer")}}}
    if w3.eth.get_block(n).hash != h.hash:
        raise ValueError("REORG_DURING_READ")
    return result
