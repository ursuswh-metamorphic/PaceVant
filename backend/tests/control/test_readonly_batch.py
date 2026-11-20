"""Read-only transport must support the canonical block-pinned RPC batch reader."""

import json

import httpx
import pytest

from treasury_contracts.readonly import ReadError, readonly_web3


@pytest.mark.parametrize("malformed", [False, True])
def test_web3_readonly_batches_match_response_ids(malformed):
    batches = []

    def transport(request):
        payload = json.loads(request.content)
        if not isinstance(payload, list):
            result = "0x7a69" if payload["method"] == "eth_chainId" else "anvil/v1"
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result}
            )
        batches.append(payload)
        replies = [
            {"jsonrpc": "2.0", "id": p["id"], "result": "0x" + (7 + i).to_bytes(32, "big").hex()}
            for i, p in enumerate(payload)
        ]
        if malformed:
            replies[1]["id"] = replies[0]["id"]
        return httpx.Response(200, json=list(reversed(replies)))

    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        w3 = readonly_web3("http://127.0.0.1:8545", 31337, client=http)
        with w3.batch_requests() as batch:
            for address in ["0x" + "01" * 20, "0x" + "02" * 20]:
                batch.add(w3.eth.call({"to": address, "data": "0x12345678"}, block_identifier=42))
            if malformed:
                with pytest.raises(ReadError, match="READONLY_BAD_RESPONSE"):
                    batch.execute()
            else:
                assert [int.from_bytes(value, "big") for value in batch.execute()] == [7, 8]
    assert len(batches) == 1
    assert all(p["method"] == "eth_call" and p["params"][1] == "0x2a" for p in batches[0])


def test_readonly_batch_rejects_privileged_method_before_network():
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("No network allowed"))
    ) as http:
        w3 = readonly_web3("http://127.0.0.1:8545", 31337, client=http)
        with pytest.raises(ReadError, match="READONLY_METHOD_FORBIDDEN"):
            w3.provider.make_batch_request(
                [("eth_chainId", []), ("eth_sendRawTransaction", ["0x"])]
            )


@pytest.mark.parametrize("recover", [True, False])
def test_transient_read_retry_is_bounded_and_never_retries_writes(monkeypatch, recover):
    requests, pauses = [], []
    monkeypatch.setattr("treasury_contracts.readonly.time.sleep", pauses.append)

    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if not recover or len(requests) < 3:
            return httpx.Response(429)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": "0xa869"})

    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        w3 = readonly_web3("https://fuji.invalid", 43113, client=http)
        if recover:
            assert w3.eth.chain_id == 43113
        else:
            with pytest.raises(ReadError, match="READONLY_RPC_UNAVAILABLE"):
                _ = w3.eth.chain_id
        count = len(requests)
        with pytest.raises(ReadError, match="READONLY_METHOD_FORBIDDEN"):
            w3.provider.make_request("eth_sendRawTransaction", ["0x"])
        assert len(requests) == count
        assert pauses == [0.5, 1.0]
        assert all(r["method"] == "eth_chainId" for r in requests)
