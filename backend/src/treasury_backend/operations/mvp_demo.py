"""Disposable local MVP server/smoke. No .env loads, public writes, or owner key in serving configuration."""

import argparse
import json
import secrets
import socket
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient
from pydantic import SecretStr
from web3 import Web3

from treasury_backend.api.app import create_app
from treasury_backend.config.control import Settings as ControlSettings
from treasury_backend.config.execution import Settings
from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.modules.execution.mvp import MvpExecution
from treasury_backend.operations.mvp_local import deploy_mvp_local
from treasury_backend.paths import ROOT
from treasury_contracts.toolchain import native_tool_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18030)
    parser.add_argument("--output", type=Path, default=ROOT / "data/mvp-local")
    parser.add_argument("--protocol-fixture", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        chain_port = sock.getsockname()[1]
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        rpc_url=f"http://127.0.0.1:{chain_port}",
        deployment_file=root / "local-runtime.json",
        data_dir=root / "execution",
        api_key=SecretStr(secrets.token_hex(32)),
    )
    proc = subprocess.Popen(
        [
            settings.anvil_binary,
            "--host",
            "127.0.0.1",
            "--port",
            str(chain_port),
            "--chain-id",
            "31337",
            "--hardfork",
            "cancun",
            "--silent",
                "--block-time",
                "1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=native_tool_environment(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        for _ in range(100):
            if w3.is_connected():
                break
            if proc.poll() is not None:
                raise RuntimeError("LOCAL_ANVIL_FAILED")
            time.sleep(0.1)
        data = deploy_mvp_local(w3, settings, root)
        m = data["manifest"]
        settings = data["settings"]
        bridge = {
            "chain_id": 31337,
            "vault_address": m.treasury,
            "router": m.adapter,
            "token_in": m.usdc,
            "token_out": m.wavax,
            "owner": m.owner,
            "attestor": m.attestor,
            "relayer": m.relayer,
            "adapter_version": "mock-swap-v1",
            "pdr_version": "2",
            "session_id": data["session_id"],
            "bytecode_hashes": {
                k: m.code_hashes[v]
                for k, v in (
                    ("PolicyVault", "treasury"),
                    ("MockSwapAdapter", "adapter"),
                    ("MockUSDC", "usdc"),
                    ("MockWAVAX", "wavax"),
                )
            },
        }
        settings.deployment_file.write_text(json.dumps(bridge), encoding="utf-8")
        operator = secrets.token_hex(32)
        (root / "operator-access.txt").write_text(operator, encoding="utf-8")
        fixture = None
        if args.protocol_fixture:
            from treasury_backend.operations.mvp_protocol_fixture import ProtocolFixture

            fixture = ProtocolFixture()
            shield = ShieldConfig(
                mode="wallet_pipeline",
                model="LOCAL_PROTOCOL_FIXTURE",
                context_chars=100000,
                max_calls=300,
            )
        else:
            shield = ShieldConfig.from_env("LOCAL")
            if shield.mode not in {"wallet_pipeline", "wallet_hardened"}:
                raise RuntimeError(
                    "Configure a real Shield provider or explicitly select --protocol-fixture for LOCAL TEST"
                )
        control = replace(
            ControlSettings(),
            mode="LOCAL",
            db=root / "control.sqlite3",
            require_itag=True,
            attestor_key=data["attestor"].key.hex(),
            chain_rpc_url=settings.rpc_url,
            relayer_address=m.relayer,
            operator_token=operator,
            internal_token=secrets.token_hex(32),
            shield=shield,
        )
        execution = MvpExecution(settings, m)
        # The serving composition receives attestor+relayer, never the owner signer.
        del data["owner"]
        app = create_app(control, settings, treasury_execution=execution, semantic_provider=fixture)
        if args.once:
            with TestClient(app) as client:
                c = execution.context(m.default_session_id)
                body = {
                    "operation": "USDC_PAYMENT",
                    "chain_id": 31337,
                    "treasury": m.treasury,
                    "session_id": m.default_session_id,
                    "token_in": m.usdc,
                    "token_out": m.usdc,
                    "recipient": m.owner,
                    "amount": "1000000",
                    "deadline": c["timestamp"] + 150,
                    "objective": "Pay exactly 1 test USDC to the owner-approved system EOA",
                }
                result = (
                    client.post(
                        "/mvp/workflows",
                        json=body,
                        headers={
                            "Authorization": "Bearer " + operator,
                            "Idempotency-Key": "local-smoke-" + secrets.token_hex(8),
                        },
                    )
                    .raise_for_status()
                    .json()
                )
                summary = {
                    "environment": "LOCAL_TEST",
                    "semantic_scope": fixture.evaluation_scope
                    if fixture
                    else "REAL_CONFIGURED_PROVIDER",
                    "status": result["status"],
                    "reason_code": result.get("reason_code"),
                    "workflow_id": result["workflow_id"],
                    "public_writes": False,
                    "outcome": result.get("outcome"),
                }
                (root / "smoke-evidence.json").write_text(
                    json.dumps(result, indent=2), encoding="utf-8"
                )
                print(json.dumps(summary, indent=2))
                return 0 if result["status"] == "CONFIRMED" else 2
        print(
            json.dumps(
                {
                    "url": f"http://127.0.0.1:{args.port}",
                    "environment": "LOCAL_TEST",
                    "operator_credential_file": str(root / "operator-access.txt"),
                    "public_writes": False,
                    "semantic_scope": fixture.evaluation_scope
                    if fixture
                    else "REAL_CONFIGURED_PROVIDER",
                }
            ),
            flush=True,
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
