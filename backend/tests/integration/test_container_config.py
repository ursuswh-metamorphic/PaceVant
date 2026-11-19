import json
import os
from pathlib import Path

import pytest
from eth_account import Account

ROOT = Path(__file__).resolve().parents[3]
import treasury_backend.operations as ops  # noqa: E402
from treasury_backend.operations import container as serving  # noqa: E402


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith(("B_", "PACEVANT_", "TREASURY_", "FUJI_")) or name in {
            "DEPLOYER_PRIVATE_KEY",
            "AGENT_PRIVATE_KEY",
            "AGENT_ADDRESS",
        }:
            monkeypatch.delenv(name)
    owner, attestor, relayer = Account.create(), Account.create(), Account.create()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"chain_id": 43113, "pdr_version": "2", "owner": owner.address}))
    for name, value in {
        "B_FUJI_RELAYER_PRIVATE_KEY": relayer.key.hex(),
        "PACEVANT_ATTESTOR_KEY": attestor.key.hex(),
        "FUJI_TEST_WALLETS_ONLY": "true",
        "B_API_KEY": "backend-service-credential-123456",
        "PACEVANT_OPERATOR_TOKEN": "operator-service-credential-123456",
        "PACEVANT_INTERNAL_TOKEN": "internal-service-credential-123456",
        "TREASURY_FUJI_DEPLOYMENT_FILE": str(manifest),
        "TREASURY_SERVER_DATA_DIR": str(tmp_path / "persistent"),
        "PORT": "10000",
    }.items():
        monkeypatch.setenv(name, value)
    return owner, manifest


def test_server_uses_public_owner_manifest_without_owner_private_key(runtime):
    p = serving.container_profile()
    assert p.a_port == 10000 and p.network == "fuji"
    assert p.control_data.is_absolute() and p.execution_data.is_absolute()
    a, b = ops.a_environment(p), ops.b_environment(p)
    assert "B_OWNER_PRIVATE_KEY" not in a and "B_OWNER_PRIVATE_KEY" not in b
    with pytest.raises(ops.OpsError, match="Owner key"):
        p.credentials(require_owner_key=True)


def test_server_refuses_owner_key_upload(runtime, monkeypatch):
    monkeypatch.setenv("DEPLOYER_PRIVATE_KEY", runtime[0].key.hex())
    with pytest.raises(ops.OpsError, match="Do not upload owner"):
        serving.container_profile()


def test_server_requires_manifest_and_separate_credentials(runtime, monkeypatch):
    monkeypatch.setenv("PACEVANT_INTERNAL_TOKEN", os.environ["B_API_KEY"])
    with pytest.raises(ops.OpsError, match="distinct service credentials"):
        serving.container_profile()
    monkeypatch.setenv("PACEVANT_INTERNAL_TOKEN", "another-internal-token-1234567890")
    runtime[1].unlink()
    with pytest.raises(ops.OpsError, match="deployment manifest"):
        serving.container_profile()
