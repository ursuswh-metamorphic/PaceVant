"""Bounded, Fuji-only chain observations for the read-only dashboard."""

import json
import re
import time
from decimal import Decimal

import httpx
from eth_abi import decode, encode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak

FUJI_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
FUJI_CHAIN_ID = 43113
EXPLORER = "https://explorer-test.avax.network/c-chain"
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
QUANTITY = re.compile(r"^0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)$")
DATA = re.compile(r"^0x(?:[0-9a-fA-F]{2})*$")
HASH = re.compile(r"^0x[0-9a-f]{64}$")
MAX_RESPONSE_BYTES = 524_288
MAX_READ_SECONDS = 20


class FujiReadError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require_address(address):
    if not isinstance(address, str) or not ADDRESS.fullmatch(address):
        raise FujiReadError("INVALID_WALLET_ADDRESS")
    return address.lower()


def quantity(value, code="FUJI_BAD_QUANTITY"):
    if not isinstance(value, str) or not QUANTITY.fullmatch(value) or len(value) > 66:
        raise FujiReadError(code)
    return int(value, 16)


def hex_data(value):
    if not isinstance(value, str) or not DATA.fullmatch(value):
        raise FujiReadError("FUJI_BAD_CALL_RESULT")
    return bytes.fromhex(value[2:])


def timestamp_fields(now, updated):
    # Invalid uint256 timestamps must not overflow canonical JSON or browser Date.
    if not 0 <= updated <= 253402300799:
        return {"updated_at_raw": str(updated), "age_seconds": None}
    return {"updated_at": updated, "age_seconds": now - updated if updated else None}


class FujiRPC:
    def __init__(self, client, now=None, monotonic=time.monotonic):
        self.client = client
        self.now = int(time.time()) if now is None else int(now)
        self.monotonic = monotonic
        self.started = monotonic()
        self.deadline = self.started + MAX_READ_SECONDS
        self.call_id = 0
        self.block = None

    def json_request(self, method, url, **options):
        remaining = self.deadline - self.monotonic()
        if remaining <= 0:
            raise FujiReadError("FUJI_READ_TIMEOUT")
        try:
            # Read an upstream body incrementally and bound its total size.
            with self.client.stream(
                method,
                url,
                timeout=httpx.Timeout(min(4, remaining), connect=min(2, remaining)),
                follow_redirects=False,
                **options,
            ) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    if self.monotonic() >= self.deadline:
                        raise FujiReadError("FUJI_READ_TIMEOUT")
                    if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise FujiReadError("FUJI_RESPONSE_TOO_LARGE")
                    data.extend(chunk)
                return json.loads(data, parse_float=Decimal)
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise FujiReadError("FUJI_RPC_UNAVAILABLE") from None

    def rpc(self, method, params):
        if method not in {
            "eth_chainId",
            "eth_getBlockByNumber",
            "eth_getBalance",
            "eth_getCode",
            "eth_call",
            "eth_getTransactionReceipt",
        }:
            raise FujiReadError("UNSAFE_RPC_METHOD")
        self.call_id += 1
        payload = self.json_request(
            "POST",
            FUJI_RPC,
            json={
                "jsonrpc": "2.0",
                "id": self.call_id,
                "method": method,
                "params": params,
            },
        )
        if (
            not isinstance(payload, dict)
            or payload.get("jsonrpc") != "2.0"
            or payload.get("id") != self.call_id
        ):
            raise FujiReadError("FUJI_BAD_RPC_RESULT")
        if "error" in payload:
            raise FujiReadError("FUJI_CALL_REVERTED")
        if "result" not in payload:
            raise FujiReadError("FUJI_BAD_RPC_RESULT")
        return payload["result"]

    def pin_block(self):
        if quantity(self.rpc("eth_chainId", [])) != FUJI_CHAIN_ID:
            raise FujiReadError("FUJI_CHAIN_MISMATCH")
        block = self.rpc("eth_getBlockByNumber", ["latest", False])
        if not isinstance(block, dict):
            raise FujiReadError("FUJI_BAD_BLOCK")
        number = quantity(block.get("number"), "FUJI_BAD_BLOCK")
        timestamp = quantity(block.get("timestamp"), "FUJI_BAD_BLOCK")
        if not isinstance(block.get("hash"), str) or not HASH.fullmatch(block["hash"]):
            raise FujiReadError("FUJI_BAD_BLOCK")
        if not 0 <= self.now - timestamp <= 120:
            raise FujiReadError("FUJI_BLOCK_STALE")
        self.block = {"number": number, "timestamp": timestamp, "hash": block["hash"]}
        return self.block

    @property
    def block_tag(self):
        if self.block is None:
            raise FujiReadError("FUJI_BLOCK_NOT_PINNED")
        return hex(self.block["number"])

    def verify_block(self):
        current = self.rpc("eth_getBlockByNumber", [self.block_tag, False])
        if not isinstance(current, dict) or current.get("hash") != self.block["hash"]:
            raise FujiReadError("FUJI_BLOCK_CHANGED")

    def code(self, address):
        code = hex_data(self.rpc("eth_getCode", [require_address(address), self.block_tag]))
        if not code:
            raise FujiReadError("FUJI_CONTRACT_NOT_DEPLOYED")
        return "0x" + keccak(code).hex()

    def eth_call(self, address, signature, types=(), values=(), returns=("uint256",)):
        data = keccak(text=signature)[:4] + encode(types, values)
        return self.decode_call(address, "0x" + data.hex(), returns)

    def decode_call(self, address, data, returns):
        raw = hex_data(
            self.rpc("eth_call", [{"to": require_address(address), "data": data}, self.block_tag])
        )
        try:
            result = decode(returns, raw)
            if encode(returns, result) != raw:
                raise ValueError("noncanonical ABI")
            return result
        except (DecodingError, ValueError, TypeError, OverflowError):
            raise FujiReadError("FUJI_BAD_CALL_RESULT") from None
