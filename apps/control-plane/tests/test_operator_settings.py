import pytest

from app.errors import ControlError
from app.orchestration.fuji import FujiVerifier
from app.settings import Settings


def test_default_and_bounded_block_drift(monkeypatch):
    monkeypatch.setenv("PACEVANT_MODE", "MOCK")
    monkeypatch.delenv("PACEVANT_MAX_BLOCK_DRIFT", raising=False)
    assert Settings.from_env().max_block_drift == 3
    monkeypatch.setenv("PACEVANT_MAX_BLOCK_DRIFT", "30")
    assert Settings.from_env().max_block_drift == 30
    monkeypatch.setenv("PACEVANT_MAX_BLOCK_DRIFT", "121")
    with pytest.raises(RuntimeError, match="1..120"):
        Settings.from_env()


@pytest.mark.parametrize("rpc", ["http://remote.example/rpc", "https://user:secret@rpc.example"])
def test_verification_rpc_rejects_insecure_or_embedded_credentials(monkeypatch, rpc):
    monkeypatch.setenv("PACEVANT_MODE", "MOCK")
    monkeypatch.setenv("PACEVANT_FUJI_VERIFICATION_RPC", rpc)
    with pytest.raises(RuntimeError, match="PACEVANT_FUJI_VERIFICATION_RPC"):
        Settings.from_env()


def test_independent_fuji_verifier_keeps_wall_clock_freshness():
    import httpx
    from test_v2_gates import inputs

    _, _, context, _, _, _, _, _, now = inputs()
    code = b"code"
    context = context.model_copy(
        update={
            "max_block_drift": 30,
            "fork_block": 10,
            "fork_block_timestamp": now,
            "fork_block_hash": "0x" + "11" * 32,
        }
    )

    def respond(request):
        assert str(request.url) == "https://independent.example/rpc"
        values = [
            hex(context.chain_id),
            {"number": hex(40)},
            {"number": hex(10), "hash": context.fork_block_hash, "timestamp": hex(now)},
            "0x" + code.hex(),
            "0x" + code.hex(),
        ]
        return httpx.Response(200, json=[{"id": i, "result": v} for i, v in enumerate(values)])

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        verifier = FujiVerifier(http, "https://independent.example/rpc")
        verifier.verify(context, now)
        with pytest.raises(ControlError):
            verifier.verify(context, now + 61)
        with pytest.raises(ControlError):
            verifier.verify(context.model_copy(update={"max_block_drift": 29}), now)
