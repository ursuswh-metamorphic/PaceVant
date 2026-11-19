"""Measure genuine original V1 and current V2.1 complete A/B protocols on Anvil.

Run after Python setup/bootstrap/compile. Never loads the user's .env or sends a Fuji tx.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import platform
import socket
import sqlite3
import subprocess
import tarfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
from eth_account import Account
from web3 import Web3

import treasury_backend.operations as ops

ROOT = ops.ROOT
BASELINE = "1b09bd8dd04fd74868f30634abeec93276522d36"


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def rpc(w3, method, params):
    result = w3.provider.make_request(method, params)
    if "error" in result:
        raise RuntimeError("Local benchmark RPC operation failed: " + method)
    return result["result"]


def original_source(destination, ref):
    commit = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
    destination.mkdir(parents=True, exist_ok=True)
    archive = subprocess.check_output(
        ["git", "-c", "core.autocrlf=false", "archive", "--format=tar", commit], cwd=ROOT
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination, filter="data")
    config = destination / "foundry.toml"
    text = config.read_text().replace(
        'libs = ["node_modules"]', 'libs = ["' + (ROOT / "lib").as_posix() + '"]'
    )
    text = text.replace(
        "@openzeppelin/contracts/=node_modules/@openzeppelin/contracts/",
        "@openzeppelin/contracts/="
        + (ROOT / "lib/openzeppelin-contracts/contracts").as_posix()
        + "/",
    )
    config.write_text(text)
    ops.compile_contracts(destination)
    expected = subprocess.check_output(
        ["git", "show", commit + ":contracts/src/PolicyVault.sol"], cwd=ROOT
    )
    assert (destination / "contracts/src/PolicyVault.sol").read_bytes() == expected
    return commit


def contracts(p):
    w3 = p.web3()
    d = json.loads(p.deployment.read_text())

    def c(name, address):
        return w3.eth.contract(
            address=Web3.to_checksum_address(address), abi=ops.artifact(p, name)["abi"]
        )

    return (
        w3,
        d,
        c("PolicyVault", d["vault_address"]),
        c("MockSwapAdapter", d["router"]),
        c("MockUSDC", d["token_in"]),
        c("MockWAVAX", d["token_out"]),
    )


def owner_send(w3, key, fn, *, wait=True, price=None):
    account = Account.from_key(key)
    tx = fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address, "pending"),
            "chainId": 31337,
            "gasPrice": price or w3.eth.gas_price,
            "gas": 300000,
        }
    )
    hash_ = w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction)
    if not wait:
        return hash_
    receipt = w3.eth.wait_for_transaction_receipt(hash_)
    assert receipt.status == 1
    return receipt


def setup(p, *, legacy):
    if legacy:
        env = ops.b_environment(p, deployment=True)
        env["PYTHONPATH"] = os.pathsep.join(
            (str(p.root / "apps/execution-plane"), str(p.root / "packages/contracts-api"))
        )
        run = subprocess.run(
            [
                ops.execution_python(),
                "-m",
                "app.cli",
                "deploy-local",
                "--env-file",
                str(p.control_data / "runtime.env"),
            ],
            cwd=p.root / "apps/execution-plane",
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if run.returncode:
            raise RuntimeError("Isolated original-commit deployment failed")
    else:
        # Match the four-mode guard ablation's declared 2.5% policy. This is
        # TEST_ONLY on an owned Anvil, never an inferred owner Fuji setting.
        config = json.loads((ROOT / "fixtures/v2_1/TEST_ONLY_policy.json").read_text())
        config["proof_policy"]["max_relative_loss_bps"] = 250
        file = p.control_data / "risk-policy.json"
        ops.atomic_json(file, config)
        env = ops.b_environment(p, deployment=True)
        env["PYTHONPATH"] = os.pathsep.join(
            (str(p.root / "backend/src"), str(p.root / "packages/contracts-api"))
        )
        run = subprocess.run(
            [
                ops.execution_python(),
                "-m",
                "treasury_backend.operations.execution",
                "deploy-local",
                "--env-file",
                str(p.control_data / "runtime.env"),
                "--v2-config",
                str(file),
            ],
            cwd=p.root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if run.returncode:
            raise RuntimeError("Isolated current V2.1 deployment failed")
        ops.prepare(p)
    w3, d, vault, router, u, w = contracts(p)
    keys = json.loads((p.execution_data / "local-keys.json").read_text())
    owner_send(w3, keys["owner"], u.functions.mint(vault.address, 10000 * 10**6))
    if legacy:
        template = json.loads((p.root / "fixtures/mock/mandate.json").read_text())
        template.update(
            {k: d[k].lower() for k in ("vault_address", "owner", "router", "token_in", "token_out")}
        )
        template.update(
            chain_id=31337,
            policy_hash=Web3.to_hex(vault.functions.activePolicyHash().call()),
            expires_at=vault.functions.policyExpiresAt().call(),
        )
        ops.atomic_json(p.control_data / "mandate.json", template)
        ops.refresh_oracle(p)
    return keys


@contextmanager
def servers(p, metric_file, gate):
    processes = []
    files = []
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(5):
            try:
                with gate:
                    ops.refresh_oracle(p)
            except Exception:
                pass

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        legacy = not (p.root / "backend/src/treasury_backend").is_dir()
        roles = (
            (
                ("execution", p.b_port, ops.execution_python(), ops.b_environment(p), "/health"),
                ("control", p.a_port, os.sys.executable, ops.a_environment(p), "/healthz"),
            )
            if legacy
            else (("backend", p.a_port, os.sys.executable, ops.backend_environment(p), "/healthz"),)
        )
        for role, port_, python, env, health in roles:
            file = (p.control_data / (role + "-protocol.log")).open("w", encoding="utf-8")
            files.append(file)
            process = subprocess.Popen(
                [
                    python,
                    str(ROOT / "tools/evaluation/protocol_server.py"),
                    role,
                    "--source",
                    str(p.root),
                    "--metrics",
                    str(metric_file),
                    "--port",
                    str(port_),
                ],
                cwd=p.root,
                env=env,
                stdout=file,
                stderr=file,
            )
            processes.append(process)
            ops.wait_ready(process, f"http://127.0.0.1:{port_}" + health)
        yield
    finally:
        stop.set()
        thread.join(timeout=6)
        for process in reversed(processes):
            ops.stop_process(process)
        for file in files:
            file.close()


def records(path):
    return (
        [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if path.exists()
        else []
    )


def run_config(root, source, mode):
    folder = root / mode
    folder.mkdir(parents=True, exist_ok=True)
    env_file = folder / "bench.env"
    ops.init_env(env_file)
    ops.update_env(
        env_file,
        {
            "TREASURY_LOCAL_RPC_URL": f"http://127.0.0.1:{port()}",
            "TREASURY_A_PORT": str(port()),
            "TREASURY_B_PORT": str(port()),
            "TREASURY_LOCAL_DEPLOYMENT_FILE": str(folder / "deployment.json"),
            "TREASURY_LOCAL_DATA_DIR": str(folder / "execution"),
            "TREASURY_CONTROL_DATA_DIR": str(folder / "control"),
        },
    )
    p = ops.Profile.load(source, env_file, "local")
    p.control_data.mkdir(parents=True, exist_ok=True)
    metric_file = folder / "metrics.jsonl"
    metric_file.write_text("")
    rows = []
    with ops.local_chain(p):
        keys = setup(p, legacy=mode == "FULL_V1_ORIGINAL")
        w3, d, vault, router, u, w = contracts(p)
        # Owned evaluation node only: keep intra-scenario block times fixed to the
        # real start time. Avoid synthetic +1s offsets becoming future evidence.
        rpc(w3, "anvil_setBlockTimestampInterval", [0])
        base_control, base_execution = p.control_data, p.execution_data
        mandate = json.loads((base_control / "mandate.json").read_text())
        for family, multiplier, count in (
            ("benign", 10000, 1),
            ("benign_mild_drift", 9980, 1),
            ("below_minout", 9800, 1),
            ("above_minout_below_phi", 9940, 1),
            ("cumulative_reservation", 9990, 3),
        ):
            # Snapshot rollback must isolate application state too: otherwise the
            # two independent protected-revert scenarios correctly quarantine A.
            p.control_data = base_control / family
            p.execution_data = base_execution / family
            ops.atomic_json(p.control_data / "mandate.json", mandate)
            ops.atomic_json(p.execution_data / "local-keys.json", keys)
            while w3.eth.get_block("latest").timestamp >= int(time.time()):
                time.sleep(0.05)
            rpc(w3, "evm_setNextBlockTimestamp", [int(time.time())])
            ops.refresh_oracle(p)
            snapshot = rpc(w3, "evm_snapshot", [])
            gate = threading.Lock()
            with (
                servers(p, metric_file, gate),
                httpx.Client(
                    base_url=f"http://127.0.0.1:{p.a_port}",
                    headers={"Authorization": "Bearer " + p.values["PACEVANT_OPERATOR_TOKEN"]},
                    timeout=90,
                    trust_env=False,
                ) as a,
            ):
                for index in range(count):
                    # Keep logical time fresh after scenario rollback without altering any risk gate.
                    while w3.eth.get_block("latest").timestamp >= int(time.time()):
                        time.sleep(0.05)
                    rpc(
                        w3,
                        "evm_setNextBlockTimestamp",
                        [int(time.time())],
                    )
                    owner_send(w3, keys["owner"], router.functions.setOutputPerUsdc(5 * 10**16))
                    ops.refresh_oracle(p)
                    before = [
                        u.functions.balanceOf(vault.address).call(),
                        w.functions.balanceOf(vault.address).call(),
                    ]
                    spent = vault.functions.dailySpentUsdc(
                        w3.eth.get_block("latest").timestamp // 86400
                    ).call()
                    start = time.perf_counter()
                    offset = len(records(metric_file))
                    gate.acquire()
                    rpc(w3, "evm_setAutomine", [False])
                    try:
                        reply = a.post(
                            "/v1/workflows/start",
                            json={"goal": "Buy WAVAX with 200 USDC", "mandate_id": "mandate_demo"},
                        )
                        reply.raise_for_status()
                        id_ = reply.json()["workflow_id"]
                        url = "/v1/workflows/" + id_
                        workflow = a.get(url).raise_for_status().json()
                        if workflow["status"] in {"SUBMITTED", "SUBMITTING"}:
                            # The owner price hook is mined BEFORE the already signed relayer tx.
                            # Thus every pre-sign and relayer preflight saw the original fair state.
                            owner_hash = owner_send(
                                w3,
                                keys["owner"],
                                router.functions.setOutputPerUsdc(5 * 10**16 * multiplier // 10000),
                                wait=False,
                                price=max(w3.eth.gas_price * 100, 1000000000),
                            )
                            rpc(w3, "evm_mine", [])
                            for _ in range(30):
                                workflow = a.get(url).raise_for_status().json()
                                if workflow["status"] not in {"SUBMITTED", "SUBMITTING"}:
                                    break
                                time.sleep(0.1)
                        else:
                            owner_hash = None
                    finally:
                        rpc(w3, "evm_setAutomine", [True])
                        gate.release()
                    elapsed = (time.perf_counter() - start) * 1000
                    receipt = next(
                        (e["receipt"] for e in reversed(workflow["timeline"]) if "receipt" in e),
                        None,
                    )
                    proof = next(
                        (e["proof"] for e in reversed(workflow["timeline"]) if "proof" in e), None
                    )
                    after = [
                        u.functions.balanceOf(vault.address).call(),
                        w.functions.balanceOf(vault.address).call(),
                    ]
                    deltas = [after[i] - before[i] for i in range(2)]
                    if receipt:
                        raw = w3.eth.get_transaction_receipt(receipt["tx_hash"])
                        hook = w3.eth.get_transaction_receipt(owner_hash)
                        assert (
                            hook.blockNumber == raw.blockNumber
                            and hook.transactionIndex < raw.transactionIndex
                        )
                        if raw.status == 0:
                            assert before == after
                            assert (
                                vault.functions.dailySpentUsdc(
                                    raw.blockNumber
                                    and w3.eth.get_block(raw.blockNumber).timestamp // 86400
                                ).call()
                                == spent
                            )
                    stages = {}
                    for metric in records(metric_file)[offset:]:
                        stages[metric["stage"]] = (
                            stages.get(metric["stage"], 0) + metric["elapsed_ms"]
                        )
                    row = {
                        "config": mode,
                        "attackFamily": family,
                        "seed": 1,
                        "tradeIndex": index,
                        "workflow_status": workflow["status"],
                        "actualResult": "confirmed"
                        if workflow["status"] == "CONFIRMED"
                        else "protectedRevert"
                        if workflow["status"] == "REVERTED"
                        else "preSignRefuse",
                        "endToEnd_ms": elapsed,
                        "stage_ms": stages,
                        "solidityGasUsed": int(receipt["gas_used"]) if receipt else 0,
                        "tx_hash": receipt["tx_hash"] if receipt else None,
                        "actualTokenDeltas": [str(x) for x in deltas],
                        "attackerGainWavax": str(max(0, 10 * 10**18 - deltas[1]))
                        if receipt and receipt["status"] == "CONFIRMED"
                        else "0",
                        "modeledRealizedLossUsdE8": str(
                            -deltas[0] * 100 - deltas[1] * 20 * 10**8 // 10**18
                        ),
                        "certifiedRiskDebit": proof.get("risk_debit_usd_e8") if proof else None,
                        "proof_context_hash": next(
                            (
                                e["decision"].get("proof_context_hash")
                                for e in workflow["timeline"]
                                if e.get("decision", {}).get("verdict") == "APPROVE"
                            ),
                            None,
                        ),
                        "proof_source_hash": proof.get("source_hash") if proof else None,
                        "actual_signer_protocol": "IMMUTABLE_DECISION_ATTESTOR",
                        "actual_relayer_protocol": "DURABLE_RAW_TX_JOURNAL",
                    }
                    rows.append(row)
                    ops.atomic_json(folder / "partial-records.json", rows)
                    ops.atomic_json(folder / (family + f"-{index}-workflow.json"), workflow)
                    if row["actualResult"] == "preSignRefuse":
                        break
            assert rpc(w3, "evm_revert", [snapshot])
    return rows


def summary(rows):
    result = {}
    for mode in sorted({r["config"] for r in rows}):
        group = [r for r in rows if r["config"] == mode]
        times = sorted(r["endToEnd_ms"] for r in group)
        result[mode] = {
            "rows": len(group),
            "p50_ms": times[math.ceil(0.5 * len(times)) - 1],
            "p95_ms": times[math.ceil(0.95 * len(times)) - 1],
            "p99_ms": times[math.ceil(0.99 * len(times)) - 1],
            "worst_ms": times[-1],
            "normal_gas": group[0]["solidityGasUsed"],
        }
    return result


def enrich(rows, root):
    """Derive report metadata from the actual immutable workflow/journal records."""
    baseline = {
        (r["attackFamily"], r["tradeIndex"]): r["solidityGasUsed"]
        for r in rows
        if r["config"] == "FULL_V1_ORIGINAL"
    }
    previous_session = {}
    for row in rows:
        folder = root / row["config"]
        family = row["attackFamily"]
        workflow = json.loads((folder / f"{family}-{row['tradeIndex']}-workflow.json").read_text())
        timeline = workflow["timeline"]
        sim = next((e["simulation"] for e in timeline if "simulation" in e), None)
        build = next((e["build"] for e in timeline if "build" in e), None)
        row["setupBlock"] = sim["fork_block"] if sim else None
        row["policyVersion"] = None
        if build:
            with sqlite3.connect(folder / "execution" / family / "state.sqlite3") as db:
                saved = db.execute(
                    "SELECT value FROM records WHERE kind='build-context' AND id=?",
                    (build["build_id"],),
                ).fetchone()
            if saved:
                row["policyVersion"] = json.loads(saved[0])["context"]["policy_version"]
        row["classification"] = (
            "unsafeSuccessful"
            if row["actualResult"] == "confirmed"
            and family in {"below_minout", "above_minout_below_phi"}
            else "benignConfirmed"
            if row["actualResult"] == "confirmed"
            else row["actualResult"]
        )
        row["signature_issued"] = any(e["stage"] == "ATTESTED" for e in timeline)
        row["retryCount"] = max((e.get("attempt", 0) for e in timeline), default=0)
        proof = next((e["proof"] for e in timeline if "proof" in e), None)
        row["solverUnknown"] = (
            any(proof.get(k) == "UNKNOWN" for k in ("check_mode", "compile_mode", "risk_bound"))
            if proof
            else None
        )
        receipt = next((e["receipt"] for e in reversed(timeline) if "receipt" in e), None)
        session = receipt.get("proof_session") if receipt else None
        scope = row["config"], family
        if session:
            previous_session[scope] = session
        else:
            session = previous_session.get(scope)
        row["budgetRemainingUsdE8"] = (
            str(int(session["limit_usd_e8"]) - int(session["used_usd_e8"])) if session else None
        )
        row["globalBudgetRemainingUsdE8"] = (
            str(int(session["global_limit_usd_e8"]) - int(session["global_used_usd_e8"]))
            if session
            else None
        )
        row["stage_ms"]["extract_ms"] = sum(
            row["stage_ms"].get(k, 0) for k in ("extract_parse_ms", "extract_assess_ms")
        )
        row["deltaGasVsOriginalV1"] = row["solidityGasUsed"] - baseline[family, row["tradeIndex"]]
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ref", default=BASELINE)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/evaluation/v2_1_full_protocol_results.json"
    )
    options = parser.parse_args()
    root = ROOT / ".control-data-v2/evaluation" / time.strftime("run-%Y%m%d-%H%M%S")
    root.mkdir(parents=True, exist_ok=True)
    source = root / "original-source"
    commit = original_source(source, options.baseline_ref)
    rows = run_config(root, source, "FULL_V1_ORIGINAL") + run_config(
        root, ROOT, "V2_1_FULL_PROTOCOL"
    )
    expected = {
        "FULL_V1_ORIGINAL": [
            "confirmed",
            "confirmed",
            "protectedRevert",
            "confirmed",
            "confirmed",
            "confirmed",
            "confirmed",
        ],
        "V2_1_FULL_PROTOCOL": [
            "confirmed",
            "confirmed",
            "protectedRevert",
            "protectedRevert",
            "confirmed",
            "confirmed",
            "preSignRefuse",
        ],
    }
    for mode, values in expected.items():
        actual = [r["actualResult"] for r in rows if r["config"] == mode]
        if actual != values:
            raise RuntimeError(
                "Full protocol benchmark outcome mismatch: " + mode + " " + str(actual)
            )
    enrich(rows, root)
    result = {
        "baseline_commit": commit,
        "baseline_source_unmodified": True,
        "current_runtime": "ONE_FASTAPI_UVICORN_WITH_IN_PROCESS_EXECUTION",
        "network": "OWNED_ANVIL_31337_ONLY",
        "environment": {
            "os": platform.platform(),
            "cpu": platform.processor(),
            "python": platform.python_version(),
            "execution_python": subprocess.check_output(
                [ops.execution_python(), "-c", "import platform; print(platform.python_version())"],
                text=True,
            ).strip(),
            "foundry": subprocess.check_output(
                [ops.foundry_binary("forge"), "--version"], text=True
            ).splitlines()[0],
            "z3": "4.15.4.0",
            "rpc": "owned loopback Anvil; no Fuji or user dotenv",
            "compiler": "0.8.38 viaIR optimizer200",
        },
        "summary": summary(rows),
        "records": rows,
        "timing_notes": "Stage durations are nested wall clock (do not sum). Extract parse/assess is separate; authoritative reads remain in sim_ms. Riskbound_solver_ms measures solver verification, analytical bound included in proof_ms.",
    }
    ops.atomic_json(options.output, result)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
