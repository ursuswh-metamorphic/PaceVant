"""Real A + B smoke tests with temporary Anvil deployments and separate processes."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx
import pytest
from web3 import Web3

from app.settings import ROOT
from app.simulation.runner import rpc
from conftest import mine_current_block


def open_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def process_ready(command, url, env, output, *, cwd):
    with output.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    if httpx.get(url, timeout=0.5).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail(f"Service startup failed. See {output}")
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("amount", "price_age", "verdicts", "hold_receipt", "v2", "reverse"),
    [
        (200, 0, ["APPROVE"], False, False, False),
        (500, 0, ["REPLAN", "APPROVE"], False, False, False),
        (200, 120, ["ESCALATE"], False, False, False),
        (200, 0, ["APPROVE"], True, False, False),
        (200, 0, ["APPROVE"], False, True, False),
        (500, 0, ["REPLAN", "APPROVE"], False, True, False),
        (1, 0, ["APPROVE"], False, True, True),
        (20, 0, ["REPLAN", "APPROVE"], False, True, True),
        (200, 120, ["ESCALATE"], False, True, False),
    ],
    ids=[
        "normal",
        "exposure-replan",
        "stale-oracle",
        "pending-reservation",
        "v2-normal",
        "v2-exposure-replan",
        "v2-reverse",
        "v2-reverse-cap",
        "v2-stale",
    ],
)
def test_start_workflow_through_a_and_b(
    plane, tmp_path, amount, price_age, verdicts, hold_receipt, v2, reverse
):
    _, chain, keys, _ = plane
    if v2:
        from v2_setup import activate

        activate(chain, keys, tmp_path)
    a_port, b_port = open_port(), open_port()
    a_url, b_url = f"http://127.0.0.1:{a_port}", f"http://127.0.0.1:{b_port}"
    execution_key, operator_key, internal_key = (secrets.token_hex(32) for _ in range(3))

    b_env = {name: value for name, value in os.environ.items() if not name.startswith("B_")}
    b_env.update(
        B_MODE="local",
        B_API_KEY=execution_key,
        B_LOCAL_RPC_URL=chain.settings.rpc_url,
        B_LOCAL_DEPLOYMENT_FILE=str(chain.settings.deployment_file),
        B_LOCAL_DATA_DIR=str(tmp_path / "execution"),
        B_LOCAL_RELAYER_PRIVATE_KEY=keys["relayer"],
    )
    context = chain.context()
    mandate = json.loads((ROOT / "fixtures/mock/mandate.json").read_text(encoding="utf-8"))
    mandate.update(
        {
            name: context[name]
            for name in (
                "chain_id",
                "vault_address",
                "owner",
                "router",
                "token_in",
                "token_out",
                "policy_hash",
            )
        }
    )
    mandate["expires_at"] = context["policy_expires_at"]
    if v2:
        mandate.update(
            proof_policy=context["proof_policy"],
            registry=context["registry"],
            session_id=context["proof_session"]["session_id"],
        )
    mandate_path = tmp_path / "mandate.json"
    mandate_path.write_text(json.dumps(mandate), encoding="utf-8")
    oracle_path = tmp_path / "oracle.json"
    a_env = {name: value for name, value in os.environ.items() if not name.startswith("PACEVANT_")}
    a_test_env = os.environ.get("PACEVANT_A_TEST_ENV", str(ROOT / ".control-data-tests" / "venv"))
    a_env.update(
        UV_PROJECT_ENVIRONMENT=a_test_env,
        PACEVANT_MODE="LOCAL",
        PACEVANT_DB=str(tmp_path / "control.sqlite3"),
        PACEVANT_B_URL=b_url,
        PACEVANT_B_TOKEN=execution_key,
        PACEVANT_CHAIN_RPC_URL=chain.settings.rpc_url,
        PACEVANT_RELAYER_ADDRESS=chain.deployment["relayer"],
        PACEVANT_ATTESTOR_KEY=keys["attestor"],
        PACEVANT_OPERATOR_TOKEN=operator_key,
        PACEVANT_INTERNAL_TOKEN=internal_key,
        PACEVANT_MANDATE_FILE=str(mandate_path),
        PACEVANT_ORACLE_FILE=str(oracle_path),
    )
    before = chain.balances()
    before_spend = int(chain.snapshot()["daily_spent_usdc_base_units"])
    with (
        process_ready(
            [
                sys.executable,
                "-m",
                "app.cli",
                "serve",
                "--port",
                str(b_port),
                "--env-file",
                str(tmp_path / "execution.env"),
            ],
            b_url + "/health",
            b_env,
            tmp_path / "execution.log",
            cwd=ROOT / "apps/execution-plane",
        ),
        process_ready(
            ["uv", "run", "--locked", "python", "scripts/serve.py", "--port", str(a_port)],
            a_url + "/healthz",
            a_env,
            tmp_path / "control.log",
            cwd=ROOT,
        ),
        httpx.Client(
            base_url=a_url, headers={"Authorization": f"Bearer {operator_key}"}, timeout=35
        ) as a,
    ):
        mine_current_block(chain)
        oracle_path.write_text(
            json.dumps(
                {
                    "chain_id": context["chain_id"],
                    "vault_address": context["vault_address"],
                    "price_source": "TRUSTED_TEST_ORACLE",
                    "price_usdc_usd_e8": "100000000",
                    "price_wavax_usd_e8": "2000000000",
                    "price_timestamp": int(time.time()) - price_age,
                }
            ),
            encoding="utf-8",
        )
        request = {
            "goal": f"Sell {amount} WAVAX for USDC" if reverse else f"Buy WAVAX with {amount} USDC",
            "mandate_id": mandate["mandate_id"],
        }
        if hold_receipt:
            rpc(chain.w3, "evm_setAutomine", [False])
        try:
            started = a.post("/v1/workflows/start", json=request)
            assert started.status_code == 200, started.text
            workflow_url = "/v1/workflows/" + started.json()["workflow_id"]
            if hold_receipt:
                pending = a.get(workflow_url).raise_for_status().json()
                assert pending["status"] == "SUBMITTED", pending
                second = a.post("/v1/workflows/start", json=request).raise_for_status().json()
                second_url = "/v1/workflows/" + second["workflow_id"]
                blocked = a.get(second_url).raise_for_status().json()
                assert blocked["status"] == "ESCALATED", blocked
                assert blocked["timeline"][-1]["reason_codes"] == ["VAULT_APPROVAL_IN_FLIGHT"]
                assert not any(event["stage"] == "ATTESTED" for event in blocked["timeline"])
                assert chain.balances() == before
                rpc(chain.w3, "evm_mine", [])
        finally:
            if hold_receipt:
                rpc(chain.w3, "evm_setAutomine", [True])
        workflow = a.get(workflow_url).raise_for_status().json()
        for _ in range(12):
            if workflow["status"] not in {"SUBMITTED", "SUBMITTING"}:
                break
            time.sleep(0.25)
            workflow = a.get(workflow_url).raise_for_status().json()
        events = workflow["timeline"]
        assert [e["decision"]["verdict"] for e in events if "decision" in e] == verdicts, workflow
        simulations = [e["simulation"] for e in events if e["stage"] == "SIMULATED"]
        assert {sim["source"] for sim in simulations} == {"REAL_LOCAL_SIM"}
        assert {sim["verification_status"] for sim in simulations} == {"COMPLETE"}
        adverse = [
            s for s in simulations[0]["stress_tests"] if s["scenario_id"] == "reserve_shift_adverse"
        ]
        assert adverse[0]["status"] == "PROTECTED_REVERT"
        assert adverse[0]["output_base_units"] == "0"

        if price_age:
            assert workflow["status"] == "ESCALATED"
            assert "STALE_PRICE" in events[-1]["decision"]["reason_codes"]
            assert not any(e["stage"] == "ATTESTED" for e in events)
            assert chain.balances() == before
            return

        assert workflow["status"] == "CONFIRMED", workflow
        attested = [e for e in events if e["stage"] == "ATTESTED"]
        assert len(attested) == 1
        if amount == 500:
            risks = [e["risk"] for e in events if e["stage"] == "EVALUATED"]
            assert [risk["projected_wavax_exposure_bps"] for risk in risks] == [2800, 2500]
            assert len({sim["evidence_root"] for sim in simulations}) == 2
            assert len({sim["nonce"] for sim in simulations}) == 2
            assert not chain.vault.functions.usedNonce(int(simulations[0]["nonce"])).call()
        assert chain.vault.functions.usedNonce(int(simulations[-1]["nonce"])).call()
        receipt = events[-1]["receipt"]
        onchain = chain.w3.eth.get_transaction_receipt(receipt["tx_hash"])
        assert onchain.status == 1 and onchain.to == chain.vault.address
        assert receipt["actual_token_in_delta_base_units"] == (
            str(-(10 if amount == 20 else 1) * 10**18) if reverse else "-200000000"
        )
        assert receipt["actual_token_out_delta_base_units"] == (
            str((200 if amount == 20 else 20) * 10**6) if reverse else "10000000000000000000"
        )
        assert int(events[-1]["execution_fee"]["gas_cost_wei"]) > 0
        assert int(chain.snapshot()["daily_spent_usdc_base_units"]) - before_spend == (
            0 if reverse else 200_000_000
        )
        if v2:
            proofs = [e["proof"] for e in events if e["stage"] == "PROVED"]
            assert len(proofs) == 1 and proofs[0]["status"] == "VERIFIED"
            assert all(
                proofs[0][key] == "UNSAT" for key in ("check_mode", "compile_mode", "risk_bound")
            )
            assert receipt["proof_session"]["used_usd_e8"] == proofs[0]["risk_debit_usd_e8"]
            assert receipt["block_hash"] == Web3.to_hex(onchain.blockHash)
