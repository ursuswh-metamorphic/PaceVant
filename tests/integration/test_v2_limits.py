import asyncio
from concurrent.futures import ThreadPoolExecutor

from test_proof_v2 import case

from treasury_contracts.http_limits import RequestSizeLimit
from treasury_contracts.proof import PGSProofEngine


def test_concurrent_proof_rechecks_are_stable():
    args = case()
    expected = PGSProofEngine().prove(*args)
    with ThreadPoolExecutor(max_workers=4) as pool:
        proofs = list(pool.map(lambda _: PGSProofEngine().prove(*args), range(8)))
    assert all(p == expected for p in proofs)


def test_request_limit_rejects_chunked_body_before_app():
    async def scenario():
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        messages = iter(
            [
                {"type": "http.request", "body": b"a" * 100, "more_body": True},
                {"type": "http.request", "body": b"b" * 100, "more_body": False},
            ]
        )

        async def receive():
            return next(messages)

        output = []

        async def send(message):
            output.append(message)

        await RequestSizeLimit(app, max_bytes=150)(
            {"type": "http", "method": "POST"}, receive, send
        )
        assert not called and output[0]["status"] == 413

    asyncio.run(scenario())
