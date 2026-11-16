import json
import os
import re
import signal
import socket
import subprocess
import sys
import time

import httpx
import pytest
from dotenv import dotenv_values

from app.configuration import migrate_env
from app.settings import ROOT, DeploymentSettings, Settings


def test_split_env_migrates_preserving_keys_and_portable_paths(tmp_path):
    original = "# User settings\nDEPLOYER_PRIVATE_KEY=owner-test\nAGENT_PRIVATE_KEY=relayer-test\nA_SERVICE_URL=http://localhost:8000\nFUJI_RPC_URL=https://test-rpc.example/private-url\n"
    main = tmp_path / ".env"
    main.write_text(original)
    split = tmp_path / ".env.b.local"
    split.write_text(
        "\n".join(
            [
                "B_MODE=local",
                "B_API_KEY=keep-api-key",
                "B_RELAYER_PRIVATE_KEY=keep-local-key",
                "B_RPC_URL=http://127.0.0.1:9999",
                f"B_DEPLOYMENT_FILE={(tmp_path / 'deployments/local.json').as_posix()}",
                f"B_DATA_DIR={(tmp_path / '.execution-data').as_posix()}",
            ]
        )
    )
    result = migrate_env(tmp_path)
    env = dotenv_values(main)
    assert main.read_text().startswith(original)
    assert not split.exists()
    assert result["merged_files"] == [".env.b.local"]
    assert env["B_API_KEY"] == "keep-api-key"
    assert env["B_LOCAL_RELAYER_PRIVATE_KEY"] == "keep-local-key"
    assert env["B_LOCAL_DEPLOYMENT_FILE"] == "deployments/local.json"
    assert env["B_FUJI_RELAYER_PRIVATE_KEY"] == "relayer-test"
    assert env["B_FUJI_OWNER_PRIVATE_KEY"] == "owner-test"
    assert env["B_FUJI_RPC_URL"] == "https://test-rpc.example/private-url"
    before = main.read_bytes()
    assert migrate_env(tmp_path)["updated_keys"] == []
    assert main.read_bytes() == before


def test_env_conflict_retains_both_original_files(tmp_path):
    main = tmp_path / ".env"
    split = tmp_path / ".env.b.local"
    main.write_text("B_API_KEY=one\n")
    split.write_text("B_API_KEY=two\n")
    before = main.read_bytes(), split.read_bytes()
    with pytest.raises(RuntimeError, match="Conflicting configuration for B_API_KEY"):
        migrate_env(tmp_path)
    assert (main.read_bytes(), split.read_bytes()) == before


def test_profile_selection_isolates_wallets_and_storage(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "B_MODE=local",
                "B_API_KEY=shared-key",
                "B_LOCAL_RPC_URL=http://127.0.0.1:9999",
                "B_LOCAL_RELAYER_PRIVATE_KEY=local-key",
                "B_FUJI_RPC_URL=https://fuji.example/rpc",
                "B_FUJI_RELAYER_PRIVATE_KEY=fuji-key",
                "B_FUJI_OWNER_PRIVATE_KEY=fuji-owner",
                "B_FUJI_ATTESTOR_ADDRESS=0x" + "11" * 20,
            ]
        )
    )
    local = Settings(_env_file=env)
    fuji = Settings(_env_file=env, mode="fuji")
    deployment = DeploymentSettings(_env_file=env, mode="fuji")
    assert local.rpc_url == "http://127.0.0.1:9999"
    assert fuji.rpc_url == "https://fuji.example/rpc"
    assert local.relayer_private_key.get_secret_value() == "local-key"
    assert fuji.relayer_private_key.get_secret_value() == "fuji-key"
    assert local.api_key == fuji.api_key
    assert local.data_dir != fuji.data_dir
    assert local.deployment_file != fuji.deployment_file
    assert fuji.deployment_file == ROOT / "deployments/execution-fuji.json"
    assert deployment.owner_private_key.get_secret_value() == "fuji-owner"
    assert "owner_private_key" not in Settings.model_fields
    assert "fuji_owner_private_key" not in Settings.model_fields


def test_config_output_hides_keys_and_private_rpc_url(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "B_MODE=fuji",
                "B_API_KEY=secret-api",
                "B_FUJI_RELAYER_PRIVATE_KEY=secret-relayer",
                "B_FUJI_OWNER_PRIVATE_KEY=secret-owner",
                "B_FUJI_RPC_URL=https://user:secret-password@rpc.example/private-token",
            ]
        )
    )
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "config", "--env-file", str(env)],
        capture_output=True,
        text=True,
        check=True,
    )
    for secret in [
        "secret-api",
        "secret-relayer",
        "secret-owner",
        "secret-password",
        "private-token",
    ]:
        assert secret not in result.stdout
    assert json.loads(result.stdout)["rpc_host"] == "rpc.example"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.integration
def test_one_command_local_stack_bootstraps_only_selected_profile(tmp_path):
    env = tmp_path / ".env"
    rpc_port, api_port = free_port(), free_port()
    while api_port == rpc_port:
        api_port = free_port()
    env.write_text(
        "\n".join(
            [
                "B_MODE=fuji",
                "B_API_KEY=stable-shared-api-key",
                f"B_LOCAL_RPC_URL=http://127.0.0.1:{rpc_port}",
                f"B_LOCAL_DEPLOYMENT_FILE={(tmp_path / 'deployment.json').as_posix()}",
                f"B_LOCAL_DATA_DIR={(tmp_path / 'data').as_posix()}",
                "B_FUJI_RELAYER_PRIVATE_KEY=do-not-change-fuji-key",
                "A_SERVICE_URL=http://localhost:8000",
            ]
        )
    )
    log_path = tmp_path / "local-stack.log"
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.cli",
            "start-local",
            "--env-file",
            str(env),
            "--port",
            str(api_port),
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{api_port}",
            timeout=1,
            headers={"X-API-Key": "stable-shared-api-key"},
        ) as client:
            for _ in range(150):
                if process.poll() is not None:
                    pytest.fail("Local stack process exited before becoming ready")
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Local stack startup timed out")
            assert client.get("/v1/chain/context").json()["chain_id"] == 31337
            first = client.get("/v1/chain/context").json()
            for _ in range(35):
                time.sleep(0.1)
                fresh = client.get("/v1/chain/context").json()
                if fresh["block_number"] > first["block_number"]:
                    break
            assert fresh["block_number"] > first["block_number"]
            assert int(time.time()) - fresh["timestamp"] < 5
        values = dotenv_values(env)
        assert values["B_MODE"] == "fuji"
        assert values["B_API_KEY"] == "stable-shared-api-key"
        assert values["B_FUJI_RELAYER_PRIVATE_KEY"] == "do-not-change-fuji-key"
        assert values["B_LOCAL_RELAYER_PRIVATE_KEY"]
        assert not (tmp_path / ".env.b.local").exists()
    finally:
        # Windows TerminateProcess does not run the CLI's finally block. Stop the
        # exact Anvil PID reported by THIS isolated stack, never other dev nodes.
        log.close()
        output = log_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"Started local Anvil \(PID (\d+)\)", output)
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        if match:
            try:
                os.kill(int(match[1]), signal.SIGTERM)
            except ProcessLookupError:
                pass
