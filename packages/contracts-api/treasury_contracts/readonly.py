"""Bounded RPC transport with no signing, submission or privileged node methods."""

import json
import time
from urllib.parse import urlsplit

import httpx
from web3 import Web3
from web3.providers.base import BaseProvider


class ReadError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


READ_METHODS = {
    "eth_chainId",
    "web3_clientVersion",
    "eth_getBlockByNumber",
    "eth_getBlockByHash",
    "eth_getBalance",
    "eth_getCode",
    "eth_call",
    "eth_getTransactionByHash",
    "eth_getTransactionReceipt",
    "eth_getLogs",
    "eth_gasPrice",
    "eth_getTransactionCount",
}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class ReadOnlyProvider(BaseProvider):
    def __init__(self, url, chain_id, *, client=None, monotonic=time.monotonic, seconds=25):
        super().__init__()
        parsed = urlsplit(url)
        if (
            chain_id not in {31337, 43113}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
            or (chain_id == 31337 and parsed.hostname not in LOOPBACK)
            or not (
                parsed.scheme == "https"
                or (parsed.scheme == "http" and parsed.hostname in LOOPBACK)
            )
        ):
            raise ReadError("READONLY_ENDPOINT_REJECTED")
        self.url, self.expected_chain = url, chain_id
        self.local = parsed.hostname in LOOPBACK
        self.http = client or httpx.Client(trust_env=False, follow_redirects=False)
        self.owned = client is None
        self.monotonic, self.deadline = monotonic, monotonic() + seconds
        self.checked, self.request_id = False, 0

    def close(self):
        if self.owned:
            self.http.close()

    def _rpc(self, method, params):
        remaining = self.deadline - self.monotonic()
        if remaining <= 0:
            raise ReadError("READONLY_TIMEOUT")
        self.request_id += 1
        try:
            payload = json.loads(
                Web3.to_json(
                    {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
                )
            )
            with self.http.stream(
                "POST", self.url, json=payload, timeout=min(4, remaining), follow_redirects=False
            ) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    if self.monotonic() > self.deadline:
                        raise ReadError("READONLY_TIMEOUT")
                    if len(data) + len(chunk) > 1_048_576:
                        raise ReadError("READONLY_RESPONSE_TOO_LARGE")
                    data.extend(chunk)
                result = json.loads(data)
            if (
                not isinstance(result, dict)
                or result.get("jsonrpc") != "2.0"
                or result.get("id") != self.request_id
                or not ({"result", "error"} & result.keys())
            ):
                raise ReadError("READONLY_BAD_RESPONSE")
            if "error" in result:
                raise ReadError("READONLY_CALL_FAILED")
            return result
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise ReadError("READONLY_RPC_UNAVAILABLE") from None

    def make_request(self, method, params):
        if method not in READ_METHODS:
            raise ReadError("READONLY_METHOD_FORBIDDEN")
        if not self.checked:
            chain = self._rpc("eth_chainId", [])["result"]
            if not isinstance(chain, str) or chain != hex(self.expected_chain):
                raise ReadError("CHAIN_MISMATCH")
            if self.local:
                version = self._rpc("web3_clientVersion", [])["result"]
                if not isinstance(version, str) or not version.lower().startswith("anvil"):
                    raise ReadError("LOCAL_REQUIRES_ANVIL")
            self.checked = True
        return self._rpc(method, params)


def readonly_web3(url, chain_id, **options):
    return Web3(ReadOnlyProvider(url, chain_id, **options))
