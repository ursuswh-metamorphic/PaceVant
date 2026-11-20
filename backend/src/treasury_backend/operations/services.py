import os
import subprocess
import sys
import time
from contextlib import contextmanager
from decimal import InvalidOperation
from threading import Event, Thread
from urllib.parse import urlsplit

import httpx

from treasury_backend.config.planning import PlanningSettings
from treasury_backend.modules.alignment.provider import ShieldConfig

from .contracts import prepare, refresh_oracle
from .env import POLICY_ENV, atomic_json, key_account
from .environments import backend_environment
from .errors import OpsError
from .processes import check_port, stop_process, wait_ready
from .profiles import owner_config


@contextmanager
def services(p, *, public_host="127.0.0.1"):
    prepare(p)
    check_port(p.a_port)
    children = []
    logs = []
    stop = Event()

    def heartbeat():
        if p.network == "fuji" and p.values.get("TREASURY_ORACLE_MODE") == "chainlink":
            # Workflows/dashboard read pinned rounds directly. A competing file
            # heartbeat would consume public RPC capacity during cold fork calls.
            return
        while not stop.wait(5):
            try:
                refresh_oracle(p)
            except Exception:
                # Never stamp fresh evidence after an RPC failure. The signer will reject stale prices.
                pass

    thread = Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        env = backend_environment(p)
        env["PYTHONPATH"] = os.pathsep.join(
            (str(p.root / "backend/src"), str(p.root / "packages/contracts-api"))
        )
        log = (p.control_data / "backend.log").open("a", encoding="utf-8")
        logs.append(log)
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "treasury_backend.api.serve",
                "--host",
                public_host,
                "--port",
                str(p.a_port),
            ],
            cwd=p.root,
            env=env,
            stdout=log,
            stderr=log,
        )
        children.append(proc)
        wait_ready(proc, f"http://127.0.0.1:{p.a_port}/healthz")
        yield children
    finally:
        stop.set()
        thread.join(timeout=6)
        for proc in reversed(children):
            stop_process(proc)
        for log in logs:
            log.close()


def demo(p, goal="Buy WAVAX with 200 USDC"):
    if p.values.get("PACEVANT_REQUIRE_ITAG") == "1":
        from .itag_demo import demo as itag_demo
        return itag_demo(p, goal)
    # Only the real A workflow can obtain an application signature.
    with httpx.Client(
        base_url=f"http://127.0.0.1:{p.a_port}",
        headers={"Authorization": "Bearer " + p.values.get("PACEVANT_OPERATOR_TOKEN", "")},
        timeout=300,
        trust_env=False,
    ) as client:
        response = client.post(
            "/v1/workflows/start", json={"mandate_id": "mandate_demo", "goal": goal}
        )
        if response.status_code != 200:
            raise OpsError("Workflow request rejected; check credentials and the backend log")
        id_ = response.json()["workflow_id"]
        for _ in range(60):
            value = client.get("/v1/workflows/" + id_).raise_for_status().json()
            if value["status"] not in {"SUBMITTED", "SUBMITTING"}:
                break
            time.sleep(1)
    atomic_json(p.control_data / f"demo-{id_}.json", value)
    receipt = next((e["receipt"] for e in reversed(value["timeline"]) if e.get("receipt")), None)
    return {
        "workflow_id": id_,
        "status": value["status"],
        "tx_hash": receipt["tx_hash"] if receipt else None,
        "reason_codes": value["timeline"][-1].get(
            "reason_codes", value["timeline"][-1].get("decision", {}).get("reason_codes", [])
        ),
        "report": str(p.control_data / f"demo-{id_}.json"),
    }


def doctor(p, *, live=False):
    rows = []

    def row(name, status, reason=""):
        rows.append({"name": name, "status": status, "reason": reason})

    try:
        planner = PlanningSettings.from_values(p.values)
        row("planner_configuration", "OK", planner.provider)
        if planner.provider == "groq":
            row("GROQ_API_KEY", "OK")
        if planner.provider in {"gemini", "xingchi", "deepseek", "rotate"}:
            configured = {"deepseek": bool(planner.deepseek_api_key), "gemini": bool(planner.gemini_api_key), "groq": bool(planner.api_key),
                          "xingchi": bool(planner.xingchi_api_key and planner.xingchi_base_url)}
            selected = planner.rotation_order if planner.provider == "rotate" else (planner.provider,)
            row("ai_provider_order", "OK", ",".join(n for n in selected if configured[n]))
    except RuntimeError:
        row("planner_configuration", "INVALID", "Check planner provider/key/model/local budgets")

    try:
        required = p.values.get("PACEVANT_REQUIRE_ITAG", "0")
        if required not in {"0", "1"}:
            raise ValueError("Invalid ITAG flag")
        shield = ShieldConfig.from_values(p.network.upper(), p.values)
        active = shield.mode in {"paper", "wallet_hardened", "wallet_pipeline"}
        row("shield_configuration", "OK" if shield.mode != "legacy_fixture" else "INVALID", shield.mode)
        row("itag_shield_requirement", "OK" if required == "0" or active else "BLOCKED",
            "Required ITAG needs an active semantic shield")
        if active:
            row("shield_provider_credentials", "OK" if any(c.api_key for c in (shield, *shield.fallbacks)) else "MISSING",
                "Presence check; live model availability is evaluated during requests")
    except (ValueError, TypeError, InvalidOperation):
        row("shield_configuration", "INVALID", "Check ITAG flag, shield endpoint/model/budgets")

    for name in ("B_API_KEY", "PACEVANT_OPERATOR_TOKEN", "PACEVANT_INTERNAL_TOKEN"):
        value = p.values.get(name, "")
        row(name, "OK" if len(value) >= 24 else "MISSING_OR_SHORT")
    token_values = [
        p.values.get(n, "")
        for n in ("B_API_KEY", "PACEVANT_OPERATOR_TOKEN", "PACEVANT_INTERNAL_TOKEN")
    ]
    row(
        "credential_separation",
        "OK" if len(set(token_values)) == 3 and all(token_values) else "INVALID",
    )
    wallets = {}
    if p.network == "fuji":
        for name, role in (
            ("B_FUJI_OWNER_PRIVATE_KEY", "owner"),
            ("B_FUJI_RELAYER_PRIVATE_KEY", "relayer"),
            ("PACEVANT_ATTESTOR_KEY", "attestor"),
        ):
            try:
                wallets[role] = key_account(p.values, name).address
                row(name, "OK")
            except OpsError:
                row(name, "MISSING_OR_INVALID")
        for name in POLICY_ENV:
            row(name, "OK" if p.values.get(name) else "MISSING")
        try:
            owner_config(p.values)
            row("owner_policy_approval", "OK")
        except OpsError as e:
            row("owner_policy_approval", "BLOCKED", str(e))
        try:
            p.credentials()
            row("wallet_roles_and_testnet_ack", "OK")
        except OpsError as e:
            row("wallet_roles_and_testnet_ack", "BLOCKED", str(e))
    row("deployment_manifest", "OK" if p.deployment.exists() else "NOT_DEPLOYED")
    network = {"requested_chain_id": p.chain_id, "rpc_host": urlsplit(p.rpc).hostname}
    if live:
        try:
            w3 = p.web3()
            network["actual_chain_id"] = w3.eth.chain_id
            if w3.eth.chain_id != p.chain_id:
                raise OpsError("CHAIN_MISMATCH")
            head = w3.eth.get_block("latest")
            network["block"] = head.number
            row("rpc_chain", "OK")
            for role, address in wallets.items():
                balance = w3.eth.get_balance(address)
                network[role] = {"address": address, "test_avax_wei": str(balance)}
                if role != "attestor":
                    row(
                        role + "_gas_funding",
                        "OK" if balance > 0 else "EMPTY",
                        "Deployment/transactions need test AVAX; doctor does not assume a universal gas amount",
                    )
            historical = max(0, head.number - 10)
            w3.eth.get_balance(wallets.get("owner", "0x" + "00" * 20), block_identifier=historical)
            row("historical_state_reads", "OK")
        except Exception:
            row(
                "rpc_chain_or_archive",
                "UNAVAILABLE_OR_MISMATCH",
                "No signing or transactions attempted",
            )
    ready = all(r["status"] in {"OK", "NOT_DEPLOYED"} for r in rows)
    return {
        "network": p.network,
        "configuration_ready": ready,
        "checks": rows,
        "rpc": network,
        "secret_values_printed": False,
    }
