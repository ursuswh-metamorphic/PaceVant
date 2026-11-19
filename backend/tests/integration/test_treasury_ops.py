import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values
from eth_account import Account

ROOT = Path(__file__).resolve().parents[3]
import treasury_backend.operations as ops  # noqa: E402


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_init_env_preserves_wallets_and_is_idempotent(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# keep\nDEPLOYER_PRIVATE_KEY=private-value-left-unchanged\nB_API_KEY=existing-backend-credential-over-24-characters\n"
    )
    ops.init_env(path)
    first = path.read_text()
    ops.init_env(path)
    assert path.read_text() == first and "# keep" in first
    assert dotenv_values(path)["DEPLOYER_PRIVATE_KEY"] == "private-value-left-unchanged"
    assert dotenv_values(path)["PACEVANT_ATTESTOR_KEY"] == ""
    assert dotenv_values(path)["TREASURY_OWNER_POLICY_APPROVED"] == "false"
    assert len(dotenv_values(path)["PACEVANT_OPERATOR_TOKEN"]) >= 24


def test_generate_attestor_only_when_requested_and_empty(tmp_path):
    path = tmp_path / ".env"
    ops.init_env(path, generate_attestor=True)
    values = ops.read_env(path)
    old = values["PACEVANT_ATTESTOR_KEY"]
    assert Account.from_key(old).address == values["B_FUJI_ATTESTOR_ADDRESS"]
    ops.init_env(path, generate_attestor=True)
    assert ops.read_env(path)["PACEVANT_ATTESTOR_KEY"] == old
    result = ops.doctor(ops.Profile.load(ROOT, path, "fuji"))
    assert old not in json.dumps(result)


def test_exact_owner_settings_require_explicit_approval():
    values = {
        "TREASURY_MAX_RELATIVE_LOSS_BPS": "300",
        "TREASURY_MAX_FIXED_LOSS_USD": "0",
        "TREASURY_ORACLE_BAND_BPS": "100",
        "TREASURY_POSTCONDITION_TOLERANCE_BPS": "40",
        "TREASURY_SESSION_RISK_LIMIT_USD": "10",
        "TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD": "20",
        "TREASURY_OWNER_POLICY_APPROVED": "false",
    }
    with pytest.raises(ops.OpsError):
        ops.owner_config(values)
    values["TREASURY_OWNER_POLICY_APPROVED"] = "true"
    c = ops.owner_config(values)
    assert c.proof_policy.authorization == "OWNER_APPROVED"
    assert c.session_limit_usd_e8 == "1000000000" and c.proof_policy.max_wavax_per_swap == "0"
    with pytest.raises(ops.OpsError):
        ops.units("0.000000001", 8, "USD")
    with pytest.raises(ops.OpsError):
        ops.units(1.2, 8, "USD")
    assert ops.units("0.00000001", 8, "USD") == "1"


def test_service_environments_do_not_propagate_owner_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPLOYER_PRIVATE_KEY", "hidden-owner-key")
    monkeypatch.setenv("B_FUJI_OWNER_PRIVATE_KEY", "hidden-owner-key")
    monkeypatch.setenv("PACEVANT_ATTESTOR_KEY", "hidden-attestor-key")
    value = ops.safe_environment({"B_API_KEY": "test-backend"})
    assert "DEPLOYER_PRIVATE_KEY" not in value and "B_FUJI_OWNER_PRIVATE_KEY" not in value
    assert "PACEVANT_ATTESTOR_KEY" not in value


def test_live_service_profiles_receive_only_their_role_keys(tmp_path):
    env = tmp_path / "roles.env"
    ops.init_env(env, generate_attestor=True)
    owner, relayer = Account.create(), Account.create()
    ops.update_env(
        env,
        {
            "B_FUJI_OWNER_PRIVATE_KEY": owner.key.hex(),
            "B_FUJI_RELAYER_PRIVATE_KEY": relayer.key.hex(),
            "FUJI_TEST_WALLETS_ONLY": "true",
        },
    )
    p = ops.Profile.load(ROOT, env, "fuji")
    a, b = ops.a_environment(p), ops.b_environment(p)
    assert a["PACEVANT_ATTESTOR_KEY"] == p.values["PACEVANT_ATTESTOR_KEY"]
    assert b["B_RELAYER_PRIVATE_KEY"] == relayer.key.hex()
    assert "PACEVANT_ATTESTOR_KEY" not in b and "B_RELAYER_PRIVATE_KEY" not in a
    assert "B_OWNER_PRIVATE_KEY" not in a and "B_OWNER_PRIVATE_KEY" not in b
    assert owner.key.hex() not in a.values() and owner.key.hex() not in b.values()
    assert ops.b_environment(p, deployment=True)["B_OWNER_PRIVATE_KEY"] == owner.key.hex()


def test_complete_local_operator_command(tmp_path, monkeypatch):
    # One API process: compile/deploy/proof/receipt without Node or a second API port.
    monkeypatch.setenv("TREASURY_FORGE_BINARY", ops.foundry_binary("forge", ROOT))
    monkeypatch.setenv("TREASURY_ANVIL_BINARY", ops.anvil_binary())
    empty_path = tmp_path / "no-node-bin"
    empty_path.mkdir()
    child_env = dict(os.environ, PATH=str(empty_path))
    assert shutil.which("node", path=child_env["PATH"]) is None
    env = tmp_path / "smoke.env"
    ops.init_env(env)
    ops.update_env(
        env,
        {
            "TREASURY_LOCAL_RPC_URL": f"http://127.0.0.1:{port()}",
            "TREASURY_A_PORT": str(port()),
            "TREASURY_B_PORT": str(port()),
            "TREASURY_LOCAL_DEPLOYMENT_FILE": str(tmp_path / "deployment.json"),
            "TREASURY_LOCAL_DATA_DIR": str(tmp_path / "execution"),
            "TREASURY_CONTROL_DATA_DIR": str(tmp_path / "control"),
        },
    )
    p = ops.Profile.load(ROOT, env, "local")
    with socket.socket() as retired_api_port, ops.local_chain(p):
        # The merged backend must work even when the retired execution port is occupied.
        retired_api_port.bind(("127.0.0.1", p.b_port))
        retired_api_port.listen()
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/treasury.py"),
                "local",
                "--once",
                "--env-file",
                str(env),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=child_env,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        manifest = json.loads((tmp_path / "deployment.json").read_text())
        assert manifest["pdr_version"] == "2" and manifest["chain_id"] == 31337
        reports = list((tmp_path / "control/local").glob("demo-*.json"))
        assert len(reports) == 1
        workflow = json.loads(reports[0].read_text())
        assert workflow["status"] == "CONFIRMED"
        assert any(e["stage"] == "PROVED" for e in workflow["timeline"])
        assert workflow["timeline"][-1]["receipt"]["proof_session"]["used_usd_e8"] != "0"
        backend_log = (tmp_path / "control/local/backend.log").read_text()
        assert backend_log.count("Started server process") == 1
        assert not (tmp_path / "control/local/execution.log").exists()

        _, w3, vault = ops.deployed(p)
        old_id = manifest["session_id"]
        old_session = vault.functions.sessions(old_id).call()
        day = w3.eth.get_block("latest").timestamp // 86400
        global_used = vault.functions.globalDailyRiskUsedUsdE8(day).call()
        spent = vault.functions.dailySpentUsdc(day).call()
        renewed = ops.renew(p)
        assert renewed["restart_services_required"]
        assert renewed["session_id"] != old_id
        assert vault.functions.sessions(old_id).call() == old_session
        assert vault.functions.sessions(renewed["session_id"]).call()[4] == 0
        assert vault.functions.globalDailyRiskUsedUsdE8(day).call() == global_used > 0
        assert vault.functions.dailySpentUsdc(day).call() == spent == 200 * 10**6
