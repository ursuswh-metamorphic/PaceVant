import json
from web3 import Web3
from ..errors import PlaneError
from ..settings import ROOT, Settings


def artifact(name):
    path = ROOT / "out" / f"{name}.sol" / f"{name}.json"
    if not path.is_file():
        raise PlaneError("CONFIGURATION_ERROR", "Run npm run b:compile first", 503)
    return json.loads(path.read_text(encoding="utf-8"))


def contract(w3, name, address):
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=artifact(name)["abi"])


def plain(value):
    if isinstance(value, bytes):
        return Web3.to_hex(value)
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(x) for x in value]
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 9007199254740991:
        return str(value)
    return value


class Chain:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.w3 = Web3(
            Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": settings.rpc_timeout})
        )
        self.deployment = json.loads(settings.deployment_file.read_text(encoding="utf-8"))
        self.chain_id = self.w3.eth.chain_id
        if self.chain_id != self.deployment["chain_id"] or (
            settings.mode == "fuji" and self.chain_id != 43113
        ):
            raise PlaneError("CHAIN_MISMATCH", "RPC/deployment chain mismatch", 503)
        if settings.mode == "local":
            if not self.w3.client_version.lower().startswith("anvil"):
                raise PlaneError("CONFIGURATION_ERROR", "Local mode requires Anvil", 503)
            from urllib.parse import urlparse

            if urlparse(settings.rpc_url).hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
                "anvil",
            }:
                raise PlaneError(
                    "CONFIGURATION_ERROR",
                    "Local mode requires a private dev endpoint",
                    503,
                )
        self.vault = contract(self.w3, "PolicyVault", self.deployment["vault_address"])
        self.adapter_version = self.deployment.get("adapter_version", "mock-swap-v1")
        self.is_lfj = self.adapter_version == "lfj-v1-fuji-v1"
        if self.adapter_version not in {"mock-swap-v1", "lfj-v1-fuji-v1"} or (
            settings.mode == "fuji" and not self.is_lfj
        ):
            raise PlaneError(
                "CONFIGURATION_ERROR",
                "Fuji requires a verified LFJ adapter; mock execution is local only",
                503,
            )
        if self.is_lfj and (settings.mode != "fuji" or self.chain_id != 43113):
            raise PlaneError("CHAIN_MISMATCH", "LFJ requires Fuji profile and chain 43113", 503)
        self.adapter_contract_name = "LFJSwapAdapter" if self.is_lfj else "MockSwapAdapter"
        self.token_contract_name = "IERC20Metadata" if self.is_lfj else None
        self.router = contract(self.w3, self.adapter_contract_name, self.deployment["router"])
        self.usdc = contract(
            self.w3, self.token_contract_name or "MockUSDC", self.deployment["token_in"]
        )
        self.wavax = contract(
            self.w3, self.token_contract_name or "MockWAVAX", self.deployment["token_out"]
        )
        for name, obj in [
            ("PolicyVault", self.vault),
            (self.adapter_contract_name, self.router),
            ("USDC" if self.is_lfj else "MockUSDC", self.usdc),
            ("WAVAX" if self.is_lfj else "MockWAVAX", self.wavax),
        ]:
            from ..crypto import keccak

            if (
                keccak(self.w3.eth.get_code(obj.address))
                != self.deployment["bytecode_hashes"][name]
            ):
                raise PlaneError("HASH_MISMATCH", "Deployed bytecode changed", 503)
        if (self.usdc.functions.decimals().call(), self.wavax.functions.decimals().call()) != (
            6,
            18,
        ):
            raise PlaneError(
                "TOKEN_DECIMALS_MISMATCH",
                "Treasury currently requires verified 6/18 decimal tokens",
                503,
            )
        if self.is_lfj:
            self.verify_lfj(self.w3.eth.block_number)

    def verify_lfj(self, block):
        from ..dex.lfj import LFJClient, ROUTER, USDC, WAVAX, call
        from ..crypto import keccak

        for name, obj in [
            ("PolicyVault", self.vault),
            ("LFJSwapAdapter", self.router),
            ("USDC", self.usdc),
            ("WAVAX", self.wavax),
        ]:
            if (
                keccak(self.w3.eth.get_code(obj.address, block))
                != self.deployment["bytecode_hashes"][name]
            ):
                raise PlaneError(
                    "HASH_MISMATCH", "Current treasury/adapter/token bytecode changed", 503
                )

        if (self.usdc.address, self.wavax.address) != (USDC, WAVAX):
            raise PlaneError("TOKEN_NOT_ALLOWED", "Wrong Fuji LFJ token identities")
        for signature, expected in [("usdc()", USDC), ("wavax()", WAVAX)]:
            (value,) = call(
                self.w3, self.vault.address, signature, returns=("address",), block=block
            )
            if value.lower() != expected.lower():
                raise PlaneError(
                    "TOKEN_NOT_ALLOWED", "Vault token configuration differs from LFJ manifest"
                )
        client = LFJClient(self.w3)
        route = client.v1_route(block)
        expected = self.deployment["lfj_route"]
        if any(
            route[k] != expected[k]
            for k in (
                "lfj_router",
                "lfj_quoter",
                "pair",
                "factory",
                "version",
                "bin_step",
                "token_path",
                "bytecode_hashes",
            )
        ):
            raise PlaneError("HASH_MISMATCH", "LFJ deployment route changed", 503)
        for signature, address in [
            ("authorizedVault()", self.vault.address),
            ("lfjRouter()", ROUTER),
            ("pair()", route["pair"]),
            ("usdc()", USDC),
            ("wavax()", WAVAX),
        ]:
            (value,) = call(
                self.w3, self.router.address, signature, returns=("address",), block=block
            )
            if value.lower() != address.lower():
                raise PlaneError("HASH_MISMATCH", "Adapter immutable configuration mismatch", 503)
        return route

    def context(self):
        b = self.w3.eth.get_block("latest")
        n = b.number

        def call(name):
            return getattr(self.vault.functions, name)().call(block_identifier=n)

        return {
            "chain_id": self.chain_id,
            "vault_address": self.vault.address,
            "router": self.router.address,
            "token_in": self.usdc.address,
            "token_out": self.wavax.address,
            "policy_hash": Web3.to_hex(call("activePolicyHash")),
            "policy_active": call("policyActive"),
            "policy_version": call("policyVersion"),
            "policy_expires_at": call("policyExpiresAt"),
            "attestor": call("attestor"),
            "owner": call("owner"),
            "paused": call("paused"),
            "max_per_swap_base_units": str(call("maxPerSwap")),
            "max_spend_per_day_base_units": str(call("maxSpendPerDay")),
            "max_slippage_bps": call("maxSlippageBps"),
            "max_approval_ttl": call("maxApprovalTtl"),
            "block_number": n,
            "block_hash": Web3.to_hex(b.hash),
            "timestamp": b.timestamp,
            "mode": self.settings.mode,
            "supported_action": "SWAP_EXACT_INPUT",
        }

    def balances(self, block="latest"):
        return {
            "usdc_base_units": str(
                self.usdc.functions.balanceOf(self.vault.address).call(block_identifier=block)
            ),
            "wavax_base_units": str(
                self.wavax.functions.balanceOf(self.vault.address).call(block_identifier=block)
            ),
            "allowance_base_units": str(
                self.usdc.functions.allowance(self.vault.address, self.router.address).call(
                    block_identifier=block
                )
            ),
        }

    def snapshot(self, context=None):
        from ..crypto import content_hash

        c = context or self.context()
        result = {
            "chain_id": self.chain_id,
            "vault_address": self.vault.address,
            "block_number": c["block_number"],
            "block_hash": c["block_hash"],
            "timestamp": c["timestamp"],
            "policy_hash": c["policy_hash"],
            **self.balances(c["block_number"]),
            "utc_day": c["timestamp"] // 86400,
            "daily_spent_usdc_base_units": str(
                self.vault.functions.dailySpentUsdc(c["timestamp"] // 86400).call(
                    block_identifier=c["block_number"]
                )
            ),
            "max_spend_per_day_base_units": c["max_spend_per_day_base_units"],
            "provenance": "CHAIN_READS_NO_PRICE_OR_EXPOSURE_ASSERTION",
        }
        return {"snapshot_id": "snapshot_" + content_hash(result)[2:], **result}
