import pytest

from treasury_backend.config.control import Settings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.workflows.fuji import FujiVerifier


def test_default_and_bounded_block_drift(monkeypatch):
    monkeypatch.setenv("PACEVANT_MODE", "MOCK")
    monkeypatch.delenv("PACEVANT_MAX_BLOCK_DRIFT", raising=False)
    assert Settings.from_env().max_block_drift == 3
    monkeypatch.setenv("PACEVANT_MAX_BLOCK_DRIFT", "30")
    assert Settings.from_env().max_block_drift == 30
    monkeypatch.setenv("PACEVANT_MAX_BLOCK_DRIFT", "200")
    assert Settings.from_env().max_block_drift == 200
    monkeypatch.setenv("PACEVANT_MAX_BLOCK_DRIFT", "241")
    with pytest.raises(RuntimeError, match="1..240"):
        Settings.from_env()


@pytest.mark.parametrize("rpc", ["http://remote.example/rpc", "https://user:secret@rpc.example", "https://rpc.example/?token=test"])
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
        with pytest.raises(ControlError, match="STALE_REQUIRES_REEVALUATION"):
            verifier.verify(context, now + 61)
        with pytest.raises(ControlError, match="STALE_REQUIRES_REEVALUATION"):
            verifier.verify(context.model_copy(update={"max_block_drift": 29}), now)


@pytest.mark.parametrize("phase,include_display_prices", [("PRE", False), ("REVALIDATION", False), ("OBSERVED", True)])
def test_signing_observation_avoids_display_only_oracle_calls(phase, include_display_prices):
    from types import SimpleNamespace

    from treasury_backend.modules.workflows.service import ControlPlane

    calls = []
    client = SimpleNamespace(observe=lambda *args, **kwargs: calls.append(kwargs) or "snapshot")
    service = SimpleNamespace(settings=SimpleNamespace(mode="FUJI"),
                              store=SimpleNamespace(history_version=lambda *args: 1))
    mandate = SimpleNamespace(chain_id=43113, vault_address="0x" + "12" * 20)
    assert ControlPlane.observe(service, client, mandate, SimpleNamespace(block_number=5), None,
                                phase=phase, persist=False) == "snapshot"
    assert calls[0]["include_oracles"] is include_display_prices
