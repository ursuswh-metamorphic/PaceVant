"""Pinned owner policy and registry reads. V3 rollout is restricted to isolated Anvil."""

import time
from urllib.parse import urlsplit

from web3 import Web3

from treasury_backend.modules.execution.chain import contract, plain
from treasury_contracts.crypto import content_hash
from treasury_contracts.proof_v3 import price_intervals
from treasury_contracts.rpc import evm_web3
from treasury_contracts.v3 import Manifest

PROOF_KEYS = ("max_wavax_per_swap", "max_relative_loss_bps", "fixed_loss_usd_e8", "oracle_band_bps",
              "tolerance_bps", "max_oracle_age", "max_session_risk_usd_e8", "global_daily_risk_usd_e8",
              "oracle_source_hash", "owner_approved")
AUTH_KEYS = ("operation_mask", "spend_limit_usd_e8", "spend_used_usd_e8", "max_actions", "actions", "cooldown", "last_rebalance")


class V3Chain:
    def __init__(self, settings, manifest: Manifest):
        manifest.verify_owner()
        self.settings, self.manifest = settings, manifest
        self.w3 = evm_web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": settings.rpc_timeout}))
        self.vault = contract(self.w3, "PolicyVaultV3", manifest.treasury)
        self.usdc = contract(self.w3, "MockUSDC", manifest.usdc)
        self.wavax = contract(self.w3, "MockWAVAX", manifest.wavax)
        self.shares = contract(self.w3, "DemoERC4626", manifest.shares)
        self.adapter = contract(self.w3, "MockSwapAdapter" if manifest.chain_id == 31337 else "LFJSwapAdapterV3", manifest.adapter)
        self.isolated()

    def isolated(self):
        if (urlsplit(self.settings.rpc_url).hostname not in {"127.0.0.1", "localhost", "::1"}
                or not self.w3.client_version.lower().startswith("anvil")
                or self.w3.eth.chain_id != self.manifest.chain_id):
            raise ValueError("V3_REQUIRES_ISOLATED_ANVIL")

    def context(self, session_id, *, require_active=True):
        self.isolated()
        w3, m = self.w3, self.manifest
        header = w3.eth.get_block("latest")
        n, now = header.number, max(header.timestamp, int(time.time()))
        def read(name, *args):
            return getattr(self.vault.functions, name)(*args).call(block_identifier=n)
        for name, expected in m.code_hashes.items():
            actual = Web3.to_hex(Web3.keccak(w3.eth.get_code(Web3.to_checksum_address(getattr(m, name)), n)))
            if actual != expected:
                raise ValueError("CODE_IDENTITY_CHANGED")
        for name in ("treasury", "adapter", "shares"):
            # Proxies need implementation-aware governance; this initial rollout refuses them.
            slot = int.from_bytes(Web3.keccak(text="eip1967.proxy.implementation"), "big") - 1
            if int.from_bytes(w3.eth.get_storage_at(Web3.to_checksum_address(getattr(m, name)), slot, n), "big"):
                raise ValueError("UPGRADEABLE_TARGET_NOT_SUPPORTED")
        if (read("owner").lower() != m.owner or read("attestor").lower() != m.attestor
                or read("usdc").lower() != m.usdc or read("wavax").lower() != m.wavax
                or read("approvedVault").lower() != m.shares or read("proofAdapter").lower() != m.adapter):
            raise ValueError("REGISTRY_MISMATCH")
        policy = dict(zip(PROOF_KEYS, read("proofPolicy"), strict=True))
        policy["oracle_source_hash"] = Web3.to_hex(policy["oracle_source_hash"])
        session = read("sessions", session_id)
        auth = dict(zip(AUTH_KEYS, read("authorities", session_id), strict=True))
        active_hash = Web3.to_hex(read("activePolicyHash"))
        if require_active and (read("paused") or not read("policyActive") or now >= read("policyExpiresAt")):
            raise ValueError("POLICY_REVOKED")
        if require_active and (not session[5] or Web3.to_hex(session[0]) != active_hash or now < session[1] or now >= session[2]
                or auth["operation_mask"] == 0 or auth["actions"] >= auth["max_actions"]):
            raise ValueError("SESSION_UNAVAILABLE")
        if self.usdc.functions.decimals().call(block_identifier=n) != 6 or self.wavax.functions.decimals().call(block_identifier=n) != 18:
            raise ValueError("TOKEN_DECIMALS_MISMATCH")
        low, high, unit = read("minAssetsPerShare"), read("maxAssetsPerShare"), read("shareUnit")
        rate = self.shares.functions.convertToAssets(unit).call(block_identifier=n)
        if self.shares.functions.asset().call(block_identifier=n).lower() != m.usdc or not low <= rate <= high:
            raise ValueError("VAULT_RATE_OUT_OF_BOUNDS")
        if m.environment == "LOCAL_FORK":
            from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
            from treasury_contracts.oracle import CIRCLE_USDC, WAVAX
            if (m.usdc, m.wavax) != (CIRCLE_USDC, WAVAX):
                raise ValueError("ORACLE_TOKEN_IDENTITY_MISMATCH")
            observation = ChainlinkPriceProvider(self.settings.rpc_url, m.treasury).read(n)
            pu, pw = int(observation.price_usdc_usd_e8), int(observation.price_wavax_usd_e8)
            oracle = observation.model_dump(mode="json")
        else:
            if m.chain_id != 31337:
                raise ValueError("LOCAL_FIXTURE_PRICE_FORBIDDEN")
            pu, pw = int(m.local_usdc_price_e8), int(m.local_wavax_price_e8)
            oracle = {"source": "LOCAL_TEST_REFERENCE_ONLY", "block": n, "price_timestamp": header.timestamp}
        day = header.timestamp // 86400
        result = {"chain_id": m.chain_id, "treasury": m.treasury, "usdc": m.usdc, "wavax": m.wavax,
                  "shares": m.shares, "adapter": m.adapter, "attestor": m.attestor, "relayer": m.relayer,
                  "policy_hash": active_hash, "policy_version": read("policyVersion"),
                  "paused": read("paused"), "policy_active": read("policyActive"), "session_active": session[5],
                  "token_allowlist": {m.usdc: read("allowedTokens", Web3.to_checksum_address(m.usdc)),
                                      m.wavax: read("allowedTokens", Web3.to_checksum_address(m.wavax))},
                  "adapter_allowed": read("allowedRouters", Web3.to_checksum_address(m.adapter)),
                  "session_id": session_id, "session_expires_at": session[2], "policy_expires_at": read("policyExpiresAt"),
                  "block_number": n, "block_hash": Web3.to_hex(header.hash), "timestamp": header.timestamp,
                  "environment": m.environment, "balances": [str(v) for v in read("balances")],
                  "authority": auth, "proof_policy": policy, "share_unit": str(unit), "share_rate": str(rate),
                  "share_rate_low": str(low), "share_rate_high": str(high), "oracle": oracle,
                  "nominal_prices": [str(pu), str(pw)],
                  "price_intervals": price_intervals(pu, pw, policy["oracle_band_bps"], low, high),
                  "max_slippage_bps": read("maxSlippageBps"), "max_ttl": min(read("maxApprovalTtl"), self.settings.max_ttl),
                  "max_operation_usd_e8": str(read("maxOperationUsdE8")),
                  "max_wavax_exposure_bps": read("maxWavaxExposureBps"),
                  "spend_remaining": str(max(0, auth["spend_limit_usd_e8"] - auth["spend_used_usd_e8"])),
                  "daily_spend_remaining": str(max(0, read("maxDailySpendUsdE8") - read("dailySpentUsdE8", day))),
                  "risk_remaining": str(max(0, session[3] - session[4])),
                  "global_risk_remaining": str(max(0, policy["global_daily_risk_usd_e8"] - read("globalDailyRiskUsedUsdE8", day))),
                  "manifest_hash": content_hash(m.model_dump(mode="json"))}
        result["recipient_allowlist"] = [{"token": token, "recipient": payee, "per_payment": str(limits[0]), "per_day": str(limits[1])}
                                         for token in (m.usdc, m.wavax, "0x" + "00" * 20) for payee in m.payee_candidates
                                         if (limits := read("payees", Web3.to_checksum_address(token), Web3.to_checksum_address(payee)))[0] > 0]
        if w3.eth.get_block(n).hash != header.hash:
            raise ValueError("REORG_DURING_READ")
        return plain(result)
