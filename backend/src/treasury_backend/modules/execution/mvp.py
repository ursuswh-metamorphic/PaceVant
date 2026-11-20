"""Two-operation execution port reusing the fixed-operation builder, simulator and journal."""

import time
from urllib.parse import urlsplit

from web3 import Web3

from treasury_backend.modules.execution.chain import contract, plain
from treasury_backend.modules.execution.storage import Store
from treasury_backend.modules.execution.v3 import V3Execution
from treasury_backend.modules.execution.v3.context import AUTH_KEYS, PROOF_KEYS
from treasury_contracts.crypto import content_hash
from treasury_contracts.proof_v3 import price_intervals
from treasury_contracts.rpc import evm_web3


class MvpChain:
    is_mvp = True

    def __init__(self, settings, manifest, *, live_enabled=False):
        manifest.verify_owner()
        if manifest.environment == "REAL_FUJI_EXECUTION":
            import json

            from treasury_backend.paths import ROOT

            existing = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text())
            if any(
                getattr(manifest, r) != existing[r].lower()
                for r in ("owner", "attestor", "relayer")
            ):
                raise ValueError("MVP_REQUIRES_EXISTING_THREE_SYSTEM_EOAS")
        self.settings, self.manifest, self.live_enabled = settings, manifest, live_enabled
        self.w3 = evm_web3(
            Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": settings.rpc_timeout})
        )
        self.vault = contract(self.w3, "PolicyVaultMVP", manifest.treasury)
        self.usdc = contract(self.w3, "MockUSDC", manifest.usdc)
        self.wavax = contract(self.w3, "MockWAVAX", manifest.wavax)
        self.adapter = contract(
            self.w3,
            "MockSwapAdapter" if manifest.environment == "LOCAL_TEST" else "LFJSwapAdapterV3",
            manifest.adapter,
        )
        self.isolated()

    def isolated(self):
        """Compatibility port name: validates isolation OR explicitly enabled public Fuji deployment."""
        m, w3 = self.manifest, self.w3
        if w3.eth.chain_id != m.chain_id:
            raise ValueError("CHAIN_MISMATCH")
        local = w3.client_version.lower().startswith("anvil") and urlsplit(
            self.settings.rpc_url
        ).hostname in {"127.0.0.1", "localhost", "::1"}
        if m.environment in {"LOCAL_TEST", "ANVIL_FORK"} and not local:
            raise ValueError("MVP_REQUIRES_ISOLATED_ANVIL")
        if m.environment == "REAL_FUJI_EXECUTION" and (
            local or m.chain_id != 43113 or not self.live_enabled
        ):
            raise ValueError("MVP_PUBLIC_EXECUTION_NOT_AUTHORIZED")

    def context(self, session_id, *, require_active=True, allow_unpriced=False):
        self.isolated()
        m, w3 = self.manifest, self.w3
        h = w3.eth.get_block("latest")
        n = h.number
        now = max(h.timestamp, int(time.time()))

        def read(name, *args):
            return getattr(self.vault.functions, name)(*args).call(block_identifier=n)

        for name, expected in m.code_hashes.items():
            if (
                Web3.to_hex(
                    Web3.keccak(w3.eth.get_code(Web3.to_checksum_address(getattr(m, name)), n))
                )
                != expected
            ):
                raise ValueError("CODE_IDENTITY_CHANGED")
        for name in ("treasury", "adapter"):
            slot = int.from_bytes(Web3.keccak(text="eip1967.proxy.implementation"), "big") - 1
            if int.from_bytes(
                w3.eth.get_storage_at(Web3.to_checksum_address(getattr(m, name)), slot, n), "big"
            ):
                raise ValueError("UPGRADEABLE_TARGET_NOT_SUPPORTED")
        for role in ("owner", "attestor"):
            if read(role).lower() != getattr(m, role):
                raise ValueError("SYSTEM_ROLE_MISMATCH")
        if any(
            w3.eth.get_code(Web3.to_checksum_address(getattr(m, r)), n)
            for r in ("owner", "attestor", "relayer")
        ):
            raise ValueError("SYSTEM_ROLE_MUST_BE_EOA")
        if (
            read("usdc").lower() != m.usdc
            or read("wavax").lower() != m.wavax
            or read("proofAdapter").lower() != m.adapter
        ):
            raise ValueError("REGISTRY_MISMATCH")
        policy = dict(zip(PROOF_KEYS, read("proofPolicy"), strict=True))
        policy["oracle_source_hash"] = Web3.to_hex(policy["oracle_source_hash"])
        if require_active and m.environment != "LOCAL_TEST" and not policy["owner_approved"]:
            raise ValueError("OWNER_PROOF_POLICY_NOT_APPROVED")
        s = read("sessions", session_id)
        auth = dict(zip(AUTH_KEYS, read("authorities", session_id), strict=True))
        scopes = read("spendScopes", session_id)
        day = h.timestamp // 86400
        ph = Web3.to_hex(read("activePolicyHash"))
        if require_active and (
            read("paused") or not read("policyActive") or now >= read("policyExpiresAt")
        ):
            raise ValueError("POLICY_REVOKED")
        if require_active and (
            not s[5]
            or Web3.to_hex(s[0]) != ph
            or not s[1] <= now < s[2]
            or not auth["operation_mask"]
            or auth["actions"] >= auth["max_actions"]
        ):
            raise ValueError("SESSION_UNAVAILABLE")
        if (
            self.usdc.functions.decimals().call(block_identifier=n) != 6
            or self.wavax.functions.decimals().call(block_identifier=n) != 18
        ):
            raise ValueError("TOKEN_DECIMALS_MISMATCH")
        if m.environment == "LOCAL_TEST":
            if m.chain_id != 31337:
                raise ValueError("LOCAL_FIXTURE_PRICE_FORBIDDEN")
            pu, pw = int(m.local_usdc_price_e8), int(m.local_wavax_price_e8)
            oracle = {"source": "LOCAL_TEST_REFERENCE_ONLY", "price_timestamp": h.timestamp}
            oracle_valid_until = h.timestamp + policy["max_oracle_age"]
        else:
            from treasury_contracts.oracle import CIRCLE_USDC, SOURCE_HASH, WAVAX

            if (m.usdc, m.wavax) != (CIRCLE_USDC, WAVAX) or policy[
                "oracle_source_hash"
            ] != SOURCE_HASH:
                raise ValueError("ORACLE_TOKEN_IDENTITY_MISMATCH")
            try:
                pu, pw, oracle, oracle_valid_until = self.reference(n, policy, now)
            except Exception as error:
                if not allow_unpriced:
                    raise
                code = getattr(error, "code", "ORACLE_WINDOW_UNAVAILABLE")
                oracle = {"status": "UNVERIFIED", "reason": code}
                pu = pw = None
                oracle_valid_until = 0
        recipients = []
        from eth_abi import encode

        for payee in m.payee_candidates:
            cap, daily = read(
                "payees", Web3.to_checksum_address(m.usdc), Web3.to_checksum_address(payee)
            )
            if cap:
                key = Web3.keccak(
                    encode(["bytes32", "address"], [bytes.fromhex(session_id[2:]), payee])
                )
                recipients.append(
                    {
                        "token": m.usdc,
                        "recipient": payee,
                        "per_payment": str(cap),
                        "per_day": str(daily),
                        "per_session": str(
                            read("recipientSessionCaps", Web3.to_checksum_address(payee))
                        ),
                        "session_spent": str(read("sessionRecipientSpent", key)),
                        "daily_spent": str(read("payeeDailySpent", Web3.keccak(
                            encode(["uint256", "address", "address"], [day, m.usdc, payee])))),
                    }
                )
        c = {
            "mvp": True,
            "chain_id": m.chain_id,
            "treasury": m.treasury,
            "usdc": m.usdc,
            "wavax": m.wavax,
            "shares": m.shares,
            "adapter": m.adapter,
            "owner": m.owner,
            "attestor": m.attestor,
            "relayer": m.relayer,
            "policy_hash": ph,
            "policy_version": read("policyVersion"),
            "paused": read("paused"),
            "policy_active": read("policyActive"),
            "session_active": s[5],
            "session_starts_at": s[1],
            "session_id": session_id,
            "session_expires_at": s[2],
            "policy_expires_at": read("policyExpiresAt"),
            "block_number": n,
            "block_hash": Web3.to_hex(h.hash),
            "timestamp": h.timestamp,
            "server_time": now,
            "environment": m.environment,
            "balances": [str(v) for v in read("balances")],
            "authority": auth,
            "proof_policy": policy,
            "share_unit": "1",
            "share_rate": "1000000",
            "share_rate_low": "1000000",
            "share_rate_high": "1000000",
            "oracle": oracle,
            "oracle_valid_until": oracle_valid_until,
            "nominal_prices": [str(pu), str(pw)] if pu is not None else None,
            "price_intervals": price_intervals(pu, pw, policy["oracle_band_bps"], 1000000, 1000000) if pu is not None else None,
            "max_slippage_bps": read("maxSlippageBps"),
            "max_ttl": min(read("maxApprovalTtl"), self.settings.max_ttl),
            "max_operation_usd_e8": str(read("maxOperationUsdE8")),
            "max_wavax_exposure_bps": read("maxWavaxExposureBps"),
            "spend_remaining": str(max(0, auth["spend_limit_usd_e8"] - auth["spend_used_usd_e8"])),
            "daily_spend_remaining": str(
                max(0, read("maxDailySpendUsdE8") - read("dailySpentUsdE8", day))
            ),
            "swap_spend_remaining": str(max(0, scopes[0] - scopes[1])),
            "payment_spend_remaining_usdc": str(max(0, scopes[2] - scopes[3])),
            "daily_swap_remaining": str(
                max(0, read("maxDailySwapUsdE8") - read("dailySwapSpentUsdE8", day))
            ),
            "daily_payment_remaining_usdc": str(
                max(0, read("maxDailyPaymentUsdc") - read("dailyPaymentSpentUsdc", day))
            ),
            "max_payment_usdc": str(read("maxPaymentUsdc")),
            "risk_remaining": str(max(0, s[3] - s[4])),
            "global_risk_remaining": str(
                max(0, policy["global_daily_risk_usd_e8"] - read("globalDailyRiskUsedUsdE8", day))
            ),
            "recipient_allowlist": recipients,
            "adapter_allowed": read("allowedRouters", Web3.to_checksum_address(m.adapter)),
            "token_allowlist": {
                token: read("allowedTokens", Web3.to_checksum_address(token))
                for token in (m.usdc, m.wavax)
            },
            "relayer_avax_wei": str(w3.eth.get_balance(Web3.to_checksum_address(m.relayer), n)),
            "manifest_hash": content_hash(m.model_dump(mode="json")),
        }
        from treasury_backend.modules.gas_credit.system import SystemGasLedger

        c["gas_spent_or_reserved_wei"] = str(
            SystemGasLedger(
                self.settings.data_dir / "state.sqlite3", self.settings
            ).reserved_or_spent(m.chain_id, m.relayer, day)
        )
        c["max_tx_fee_wei"] = str(self.settings.max_tx_fee_wei)
        c["max_gas_price_wei"] = str(self.settings.max_gas_price_wei)
        c["max_daily_execution_cost_usd_e8"] = m.max_daily_execution_cost_usd_e8
        if w3.eth.get_block(n).hash != h.hash:
            raise ValueError("REORG_DURING_READ")
        return plain(c)

    def reference(self, block, policy, now):
        from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider

        observed = ChainlinkPriceProvider(self.settings.rpc_url, self.manifest.treasury).read(block)
        avax = next(f for f in observed.oracle_feeds if f.asset == self.manifest.wavax)
        if now - avax.updated_at > policy["max_oracle_age"]:
            raise ValueError("ORACLE_WINDOW_UNAVAILABLE")
        valid_until = min(avax.updated_at + policy["max_oracle_age"],
                          *(f.updated_at + f.max_age_seconds for f in observed.oracle_feeds))
        return (int(observed.price_usdc_usd_e8), int(observed.price_wavax_usd_e8),
                observed.model_dump(mode="json"), valid_until)


class MvpExecution(V3Execution):
    protocol = "PACEVANT_MVP"

    def display_context(self, session_id):
        # Unpriced balances are useful for diagnosis, never authorization input.
        return self.chain.context(session_id, require_active=False, allow_unpriced=True)

    def preview_swap(self, amount, context, *, reverse=False):
        """Read-only route/reference check. Does not allocate a nonce or attest."""
        if self.manifest.environment == "LOCAL_TEST":
            i, o = (self.manifest.wavax, self.manifest.usdc) if reverse else (self.manifest.usdc, self.manifest.wavax)
            quote = self.chain.adapter.functions.quote(Web3.to_checksum_address(i), Web3.to_checksum_address(o), amount).call(
                block_identifier=context["block_number"])
        else:
            from treasury_backend.modules.execution.dex.lfj import LFJClient

            client = LFJClient(self.chain.w3, self.manifest.usdc)
            route = client.v1_route(context["block_number"])
            quote = int(client.verified_quote(amount, context["block_number"], route, reverse=reverse)["amount_out_base_units"])
        from fractions import Fraction

        pu, pw = map(int, context["nominal_prices"])
        fair = Fraction(amount * pw * 10**6, pu * 10**18) if reverse else Fraction(amount * pu * 10**18, pw * 10**6)
        if quote <= 0 or quote * 10000 < fair * (10000 - context["proof_policy"]["max_relative_loss_bps"]):
            raise ValueError("ORACLE_PRICE_DEVIATION")
        return str(quote)

    def __init__(self, settings, manifest, store=None, *, live_enabled=False):
        self.chain = MvpChain(settings, manifest, live_enabled=live_enabled)
        self.store = store or Store(settings.data_dir)
        self.manifest = manifest
