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


def test_serving_and_doctor_use_public_owner_identity_and_ignore_retired_demo(runtime, monkeypatch):
    p = serving.container_profile()
    # An operator's stale local value must never be parsed to serve the treasury.
    p.values["B_FUJI_OWNER_PRIVATE_KEY"] = "unused-invalid-owner-key"
    p.values["PACEVANT_DEMO_ENABLED"] = "1"
    p.values["PACEVANT_DEMO_ACCESS_TOKEN"] = "retired-short-token"
    from treasury_backend.operations import profiles

    original = profiles.key_account

    def role_account(values, name):
        assert name != "B_FUJI_OWNER_PRIVATE_KEY"
        return original(values, name)

    monkeypatch.setattr(profiles, "key_account", role_account)
    p.credentials()
    result = ops.doctor(p)
    rows = {r["name"]: r for r in result["checks"]}
    assert rows["owner_public_identity"]["status"] == "OK"
    assert rows["single_tenant_interface"]["status"] == "OK"
    assert "demo_user_configuration" not in rows


def test_server_requires_manifest_and_separate_credentials(runtime, monkeypatch):
    monkeypatch.setenv("PACEVANT_INTERNAL_TOKEN", os.environ["B_API_KEY"])
    with pytest.raises(ops.OpsError, match="distinct service credentials"):
        serving.container_profile()
    monkeypatch.setenv("PACEVANT_INTERNAL_TOKEN", "another-internal-token-1234567890")
    runtime[1].unlink()
    with pytest.raises(ops.OpsError, match="deployment manifest"):
        serving.container_profile()


@pytest.mark.parametrize("health_status,expected", [(503, 2), (200, 0)])
def test_container_watchdog_restarts_only_failed_liveness(tmp_path, monkeypatch, health_status, expected):
    from contextlib import contextmanager
    from types import SimpleNamespace

    persistent = tmp_path / "persistent"
    persistent.mkdir()
    journal = persistent / "journal-kept.txt"
    journal.write_text("keep")
    profile = SimpleNamespace(control_data=persistent, a_port=18000)
    monkeypatch.setattr(serving, "container_profile", lambda:profile)
    monkeypatch.setattr(serving.signal, "signal", lambda *_:None)
    clock = [0]
    monkeypatch.setattr(serving.time, "monotonic", lambda:clock[0])

    def sleep(_):
        clock[0] += 31
        if clock[0] > 100:
            raise KeyboardInterrupt

    monkeypatch.setattr(serving.time, "sleep", sleep)

    def probe(url, **kwargs):
        assert url.endswith("/healthz")  # Oracle/session /readyz must never trigger a restart.
        return SimpleNamespace(status_code=health_status)

    monkeypatch.setattr(serving.httpx, "get", probe)

    @contextmanager
    def services(*args, **kwargs):
        assert kwargs["log_to_stdout"]
        yield [SimpleNamespace(poll=lambda:None)]

    monkeypatch.setattr(serving, "services", services)
    assert serving.main() == expected
    assert journal.read_text() == "keep"
