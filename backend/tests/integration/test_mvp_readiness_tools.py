"""The readiness verifier cannot mutate a public node or import a wallet credential."""

import os
from types import SimpleNamespace

import pytest
from tools.operations.verify_mvp_fuji_fork import load_model_settings, require_isolated_fork


@pytest.mark.parametrize("url,client,chain", [
    ("https://api.avax-test.network/ext/bc/C/rpc", "Anvil/v1", 43113),
    ("http://127.0.0.1:8545", "Avalanche/v1", 43113),
    ("http://127.0.0.1:8545", "Anvil/v1", 43114),
])
def test_verifier_rejects_public_non_anvil_and_wrong_chain_before_setup(url, client, chain):
    w3 = SimpleNamespace(provider=SimpleNamespace(endpoint_uri=url), client_version=client,
                         eth=SimpleNamespace(chain_id=chain))
    with pytest.raises(ValueError, match="ISOLATED_FORK_REQUIRED"):
        require_isolated_fork(w3)


def test_verifier_accepts_only_the_expected_disposable_fork():
    require_isolated_fork(SimpleNamespace(provider=SimpleNamespace(endpoint_uri="http://127.0.0.1:12345"),
                                          client_version="anvil/v1", eth=SimpleNamespace(chain_id=43113)))


def test_model_config_reader_excludes_wallet_and_service_credentials(tmp_path, monkeypatch):
    names = ("B_FUJI_OWNER_PRIVATE_KEY", "PACEVANT_ATTESTOR_KEY", "B_FUJI_RELAYER_PRIVATE_KEY", "B_API_KEY")
    for name in (*names, "DEEPSEEK_API_KEY", "PACEVANT_SHIELD_MODE"):
        monkeypatch.delenv(name, raising=False)
    config = tmp_path / "private-model-settings.env"
    config.write_text("\n".join(f"{name}=must-never-be-imported" for name in names)
                      + "\nDEEPSEEK_API_KEY=test-only-model-value\nPACEVANT_SHIELD_MODE=wallet_pipeline\n")
    load_model_settings(config)
    assert all(name not in os.environ for name in names)
    assert os.environ["DEEPSEEK_API_KEY"] == "test-only-model-value"
    assert os.environ["PACEVANT_SHIELD_MODE"] == "wallet_pipeline"
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.delenv("PACEVANT_SHIELD_MODE")
