"""Read-only, Fuji-only wallet/market observations. Never signs, submits, or approves swaps.

These observations are intentionally NOT fed into the trading authorizer: the
current vault uses demo tokens and does not have verified USD prices for every
asset. No mainnet RPC, static-price fallback, or transaction methods exist here.
"""
import os
import re
import time
from decimal import Decimal, InvalidOperation

import httpx
from eth_abi import decode
from eth_utils import keccak

FUJI_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
FUJI_CHAIN_ID = 43113
EXPLORER = "https://explorer-test.avax.network/c-chain"
# Avalanche docs: official Circle USDC on Fuji. Do not confuse with MockUSDC.
FUJI_USDC = "0x5425890298aed601595a70AB815c96711a31Bc65"
# Fuji test WAVAX contract; validate bytecode and decimals at runtime.
FUJI_WAVAX = "0xd00ae08403B9bbb9124bB305C09058E32C39A48c"
# Witnet's Fuji price router, as published in Witnet's Avalanche feed registry.
WITNET_FUJI_ROUTER = "0x1111AbA2164AcdC6D291b08DfB374280035E1111"
AVAX_USD_PAIR = keccak(text="Price-AVAX/USD-6")
BALANCE_OF = "0x70a08231"
DECIMALS = "0x313ce567"
VALUE_FOR = "0x" + keccak(text="valueFor(bytes32)")[:4].hex()
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
MAX_ORACLE_AGE_SECONDS = 30 * 60 * 60  # visibility only: published heartbeat is 24h
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"


class FujiReadError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require_address(address):
    if not isinstance(address, str) or not ADDRESS.fullmatch(address):
        raise FujiReadError("INVALID_WALLET_ADDRESS")
    return address.lower()


class FujiReader:
    """Single-block, read-only RPC calls, using the official Fuji endpoint only."""

    def __init__(self, client: httpx.Client, now=None):
        self.client = client
        self.now = int(time.time()) if now is None else int(now)
        self.call_id = 0

    def rpc(self, method, params):
        # This allowlist prevents accidental exposure of transaction RPC methods.
        if method not in {
            "eth_chainId", "eth_getBlockByNumber", "eth_getBalance",
            "eth_getCode", "eth_call",
        }:
            raise FujiReadError("UNSAFE_RPC_METHOD")
        self.call_id += 1
        try:
            response = self.client.post(
                FUJI_RPC,
                json={"jsonrpc": "2.0", "id": self.call_id, "method": method, "params": params},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or "error" in payload or "result" not in payload:
                raise ValueError("unexpected JSON-RPC result")
            return payload["result"]
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise FujiReadError("FUJI_RPC_UNAVAILABLE") from None

    def eth_call(self, to, data, block):
        result = self.rpc("eth_call", [{"to": to, "data": data}, block])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise FujiReadError("FUJI_BAD_CALL_RESULT")
        return bytes.fromhex(result[2:])

    def token_balance(self, token, holder, block, expected_decimals):
        if self.rpc("eth_getCode", [token, block]) in ("0x", None):
            raise FujiReadError("FUJI_TOKEN_NOT_DEPLOYED")
        raw_decimals = self.eth_call(token, DECIMALS, block)
        if len(raw_decimals) != 32 or int.from_bytes(raw_decimals, "big") != expected_decimals:
            raise FujiReadError("FUJI_TOKEN_DECIMALS_MISMATCH")
        encoded_holder = holder[2:].lower().zfill(64)
        raw_balance = self.eth_call(token, BALANCE_OF + encoded_holder, block)
        if len(raw_balance) != 32:
            raise FujiReadError("FUJI_BAD_BALANCE")
        return str(int.from_bytes(raw_balance, "big"))

    def oracle(self, block):
        """Witnet ERC-2362 (int256 price, uint256 updatedAt, uint256 status).

        Status=200 and an updated timestamp are REQUIRED; otherwise return a
        visible unusable result, never an invented price or a stale fallback.
        """
        info = {
            "provider": "WITNET",
            "network": "AVALANCHE_FUJI",
            "router": WITNET_FUJI_ROUTER,
            "pair": "AVAX/USD",
            "decimals": 6,
            "status": "UNVERIFIED",
            "usable_for_decisions": False,
        }
        try:
            if self.rpc("eth_getCode", [WITNET_FUJI_ROUTER, block]) in ("0x", None):
                raise FujiReadError("FUJI_ORACLE_NOT_DEPLOYED")
            result = self.eth_call(
                WITNET_FUJI_ROUTER, VALUE_FOR + AVAX_USD_PAIR.hex(), block
            )
            price, updated_at, update_status = decode(
                ["int256", "uint256", "uint256"], result
            )
            info.update(updated_at=int(updated_at), oracle_update_status=int(update_status))
            if price > 0:\n                info["price_usd_e8"] = str(price * 100)\n            if price <= 0 or update_status != 200 or updated_at > self.now:
                info["status"] = "UNVERIFIED"
            elif self.now - updated_at > MAX_ORACLE_AGE_SECONDS:
                info["status"] = "STALE"
            else:
                info["status"] = "FRESH"
                # Convert from 1e6 to 1e8 without floats.
                info["price_usd_e8"] = str(price * 100)
                # Not usable for SDE: Fuji test USDC does not have a second
                # validated USD feed and may not track actual USD value.
            return info
        except (FujiReadError, OverflowError, ValueError, TypeError):
            info["status"] = "UNAVAILABLE"
            return info

    def market(self):
        """Optional real off-chain market reference; never an authorization source."""
        output = {
            "provider": "COINGECKO_DEMO",
            "pair": "AVAX/USD",
            "source_type": "OFFCHAIN_MARKET_API",
            "status": "NOT_CONFIGURED",
            "usable_for_decisions": False,
        }
        key = os.environ.get("PACEVANT_COINGECKO_DEMO_KEY")
        if not key:
            return output
        try:
            response = self.client.get(
                COINGECKO_URL,
                params={
                    "ids": "avalanche-2",
                    "vs_currencies": "usd",
                    "include_last_updated_at": "true",
                },
                headers={"x-cg-demo-api-key": key, "Accept": "application/json"},
            )
            response.raise_for_status()
            entry = response.json()["avalanche-2"]
            price = Decimal(str(entry["usd"]))
            updated = int(entry["last_updated_at"])
            if not price.is_finite() or price <= 0 or updated > self.now:
                raise ValueError("invalid price/timestamp")
            output.update(
                price_usd_e8=str(int(price * 100_000_000)),
                updated_at=updated,
                status="FRESH" if self.now - updated <= 180 else "STALE",
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation, OverflowError):
            output["status"] = "UNAVAILABLE"
        return output

    def snapshot(self, address):
        holder = require_address(address)
        if self.rpc("eth_chainId", []) != hex(FUJI_CHAIN_ID):
            raise FujiReadError("FUJI_CHAIN_MISMATCH")
        head = self.rpc("eth_getBlockByNumber", ["latest", False])
        if not isinstance(head, dict) or not all(k in head for k in ("number", "hash", "timestamp")):
            raise FujiReadError("FUJI_BAD_BLOCK")
        block = head["number"]  # pin every balance/price read to the same height
        native = self.rpc("eth_getBalance", [holder, block])
        if not isinstance(native, str) or not native.startswith("0x"):
            raise FujiReadError("FUJI_BAD_BALANCE")
        assets = [
            {"symbol": "AVAX", "contract": None, "decimals": 18,
             "balance_base_units": str(int(native, 16)), "kind": "NATIVE_TEST_AVAX"},
            {"symbol": "USDC", "contract": FUJI_USDC, "decimals": 6,
             "balance_base_units": self.token_balance(FUJI_USDC, holder, block, 6),
             "kind": "CIRCLE_FUJI_TEST_USDC"},
            {"symbol": "WAVAX", "contract": FUJI_WAVAX, "decimals": 18,
             "balance_base_units": self.token_balance(FUJI_WAVAX, holder, block, 18),
             "kind": "FUJI_TEST_WAVAX"},
        ]
        return {
            "network": "AVALANCHE_FUJI_TESTNET",
            "chain_id": FUJI_CHAIN_ID,
            "address": holder,
            "explorer_url": f"{EXPLORER}/address/{holder}",
            "block_number": int(block, 16),
            "block_hash": head["hash"],
            "block_timestamp": int(head["timestamp"], 16),
            "assets": assets,
            "oracle": self.oracle(block),
            "market": self.market(),
            "source": "FUJI_C_CHAIN_RPC",
            "execution_enabled": False,
            "used_for_sde_or_attestation": False,
            "warnings": [
                "Read-only Fuji data; no swap, signing, key custody, or mainnet operations",
                "Fuji test USDC and mock USDC are different contracts",
                "No USD portfolio total without independently verified pricing for all tokens",
                "CoinGecko off-chain market data is not a Fuji-native oracle and is display-only",
            ],
        }
