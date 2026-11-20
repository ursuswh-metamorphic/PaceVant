"""Fuji can return extended block extraData; identity checks must still work."""

import httpx
import pytest
from web3.providers.base import JSONBaseProvider

from treasury_contracts.readonly import ReadError, readonly_web3
from treasury_contracts.rpc import evm_web3

HASH = "0x" + "ab" * 32
EXTRA = "0x" + "ef" * 80


def block():
    return {
        "number": "0x123",
        "hash": HASH,
        "timestamp": "0x456",
        "extraData": EXTRA,
        "transactions": [],
        "gasLimit": "0x989680",
        "gasUsed": "0x0",
    }


class HeaderProvider(JSONBaseProvider):
    def make_request(self, method, params):
        assert method in {"eth_getBlockByNumber", "eth_getBlockByHash"}
        return {"jsonrpc": "2.0", "id": 1, "result": block()}


@pytest.mark.parametrize("identifier", [291, HASH])
def test_extended_header_keeps_canonical_identity(identifier):
    value = evm_web3(HeaderProvider()).eth.get_block(identifier)
    assert value.number == 291
    assert value.timestamp == 1110
    assert value.hash.hex() == HASH[2:]
    assert bytes(value.proofOfAuthorityData).hex() == EXTRA[2:]


def test_readonly_transport_accepts_fuji_header_without_allowing_writes():
    calls = []

    def reply(request):
        import json

        payload = json.loads(request.content)
        calls.append(payload["method"])
        result = "0xa869" if payload["method"] == "eth_chainId" else block()
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        w3 = readonly_web3("https://rpc.example.test", 43113, client=client)
        assert w3.eth.get_block(291).hash.hex() == HASH[2:]
        assert calls == ["eth_chainId", "eth_getBlockByNumber"]
        with pytest.raises(ReadError, match="READONLY_METHOD_FORBIDDEN"):
            w3.provider.make_request("eth_sendRawTransaction", ["0x00"])
        assert calls == ["eth_chainId", "eth_getBlockByNumber"]
