"""Operator tooling for the existing A/B system. Never a signer/executor bypass."""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values, set_key
from eth_account import Account
from filelock import FileLock
from web3 import Web3

from treasury_contracts.onchain_v2 import read_v2_context
from treasury_contracts.toolchain import foundry_binary
from treasury_contracts.v2 import DeploymentProofConfig, ProofPolicy, keccak

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
POLICY_ENV = {
    "TREASURY_MAX_RELATIVE_LOSS_BPS": "",
    "TREASURY_MAX_FIXED_LOSS_USD": "",
    "TREASURY_ORACLE_BAND_BPS": "",
    "TREASURY_POSTCONDITION_TOLERANCE_BPS": "",
    "TREASURY_SESSION_RISK_LIMIT_USD": "",
    "TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD": "",
}
ENV_DEFAULTS = {
    "PACEVANT_MODE": "MOCK",
    "PACEVANT_B_URL": "http://127.0.0.1:8001",
    "PACEVANT_B_TOKEN": "${B_API_KEY}",
    "PACEVANT_CHAIN_RPC_URL": "${B_FUJI_RPC_URL}",
    "PACEVANT_RELAYER_ADDRESS": "${AGENT_ADDRESS}",
    "PACEVANT_MANDATE_FILE": ".control-data-v2/fuji/mandate.json",
    "PACEVANT_ORACLE_FILE": ".control-data-v2/fuji/oracle.json",
    "PACEVANT_ATTESTOR_KEY": "",
    "PACEVANT_OPERATOR_TOKEN": "",
    "PACEVANT_INTERNAL_TOKEN": "",
    "PACEVANT_FUJI_VERIFICATION_RPC": PUBLIC_RPC,
    "B_FUJI_ATTESTOR_ADDRESS": "",
    "B_FUJI_OWNER_PRIVATE_KEY": "${DEPLOYER_PRIVATE_KEY}",
    "B_FUJI_RELAYER_PRIVATE_KEY": "${AGENT_PRIVATE_KEY}",
    "B_FUJI_RPC_URL": "${FUJI_RPC_URL}",
    "FUJI_RPC_URL": PUBLIC_RPC,
    "DEPLOYER_PRIVATE_KEY": "",
    "AGENT_PRIVATE_KEY": "",
    "AGENT_ADDRESS": "",
    "FUJI_TEST_WALLETS_ONLY": "false",
    "B_API_KEY": "",
    "TREASURY_LOCAL_RPC_URL": "http://127.0.0.1:8545",
    "TREASURY_LOCAL_DEPLOYMENT_FILE": "deployments/treasury-local-v2.json",
    "TREASURY_FUJI_DEPLOYMENT_FILE": "deployments/treasury-fuji-v2.json",
    "TREASURY_LOCAL_DATA_DIR": ".execution-data-v2",
    "TREASURY_FUJI_DATA_DIR": ".execution-data-fuji-v2",
    "TREASURY_CONTROL_DATA_DIR": ".control-data-v2",
    "TREASURY_A_PORT": "8000",
    "TREASURY_B_PORT": "8001",
    "TREASURY_OWNER_POLICY_APPROVED": "false",
    "TREASURY_MAX_WAVAX_PER_SWAP": "0",
    "TREASURY_MAX_ORACLE_AGE_SECONDS": "60",
    "TREASURY_SESSION_DURATION_SECONDS": "3600",
    "TREASURY_ORACLE_USDC_USD": "1",
    "TREASURY_ORACLE_WAVAX_USD": "20",
    "TREASURY_FUJI_MAX_BLOCK_DRIFT": "30",
    "TREASURY_LOCAL_MAX_BLOCK_DRIFT": "3",
    "TREASURY_FUJI_CONFIRMATIONS": "2",
    "TREASURY_LOCAL_CONFIRMATIONS": "1",
    **POLICY_ENV,
}


class OpsError(RuntimeError):
    """Messages contain names/reasons only, never secret values or RPC credentials."""


def path_for(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def read_env(path):
    values = {k: v or "" for k, v in dotenv_values(path).items()}
    values.update(
        {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("B_", "PACEVANT_", "TREASURY_", "FUJI_"))
        }
    )
    return values


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=".tmp-", delete=False, encoding="utf-8"
    ) as f:
        json.dump(value, f, indent=2)
        f.write("\n")
        temporary = Path(f.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update_env(path, updates):
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock"):
        original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".env-update-")
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(original)
            for key, value in updates.items():
                set_key(temporary, key, value, quote_mode="always")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def key_account(values, name):
    if not values.get(name):
        raise OpsError("Missing " + name)
    try:
        return Account.from_key(values[name])
    except Exception:
        raise OpsError("Invalid private key in " + name) from None


def init_env(env_file, *, generate_attestor=False):
    raw = dotenv_values(env_file, interpolate=False) if env_file.exists() else {}
    updates = {k: v for k, v in ENV_DEFAULTS.items() if k not in raw}
    for name in ("B_API_KEY", "PACEVANT_OPERATOR_TOKEN", "PACEVANT_INTERNAL_TOKEN"):
        if not raw.get(name):
            updates[name] = secrets.token_hex(32)
    if generate_attestor and not raw.get("PACEVANT_ATTESTOR_KEY"):
        updates["PACEVANT_ATTESTOR_KEY"] = Account.create().key.hex()
    update_env(env_file, updates)
    values = read_env(env_file)
    public_updates = {}
    for private, public in (
        ("PACEVANT_ATTESTOR_KEY", "B_FUJI_ATTESTOR_ADDRESS"),
        ("B_FUJI_RELAYER_PRIVATE_KEY", "AGENT_ADDRESS"),
    ):
        if values.get(private) and not values.get(public):
            public_updates[public] = key_account(values, private).address
    if public_updates:
        update_env(env_file, public_updates)
    return {
        "env_file": str(env_file),
        "added_or_initialized": sorted(set(updates) | set(public_updates)),
        "secret_values_printed": False,
    }


def units(value, decimals, name):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise OpsError("Invalid nonnegative decimal in " + name)
    whole, _, fraction = value.partition(".")
    if len(fraction) > decimals:
        raise OpsError("Too many decimal places in " + name)
    result = int(whole) * 10**decimals + int(fraction.ljust(decimals, "0") or "0")
    if result >= 2**256:
        raise OpsError("uint256 overflow in " + name)
    return str(result)


def integer(values, name, default=None, minimum=0, maximum=2**53 - 1):
    try:
        value = int(values.get(name, default))
    except (ValueError, TypeError):
        raise OpsError("Missing or invalid integer: " + name) from None
    if not minimum <= value <= maximum:
        raise OpsError("Out of range: " + name)
    return value


def owner_config(values):
    missing = [k for k in POLICY_ENV if not values.get(k)]
    if missing:
        raise OpsError("Missing owner risk settings: " + ", ".join(missing))
    if values.get("TREASURY_OWNER_POLICY_APPROVED", "").lower() != "true":
        raise OpsError("Owner must review parameters and set TREASURY_OWNER_POLICY_APPROVED=true")
    try:
        limit = units(
            values["TREASURY_SESSION_RISK_LIMIT_USD"], 8, "TREASURY_SESSION_RISK_LIMIT_USD"
        )
        policy = ProofPolicy(
            max_wavax_per_swap=units(
                values.get("TREASURY_MAX_WAVAX_PER_SWAP", "0"), 18, "TREASURY_MAX_WAVAX_PER_SWAP"
            ),
            max_relative_loss_bps=integer(values, "TREASURY_MAX_RELATIVE_LOSS_BPS", maximum=9999),
            fixed_loss_usd_e8=units(
                values["TREASURY_MAX_FIXED_LOSS_USD"], 8, "TREASURY_MAX_FIXED_LOSS_USD"
            ),
            oracle_band_bps=integer(values, "TREASURY_ORACLE_BAND_BPS", maximum=9999),
            tolerance_bps=integer(values, "TREASURY_POSTCONDITION_TOLERANCE_BPS", maximum=9999),
            max_oracle_age=integer(
                values, "TREASURY_MAX_ORACLE_AGE_SECONDS", "60", minimum=1, maximum=3600
            ),
            max_session_risk_usd_e8=limit,
            global_daily_risk_usd_e8=units(
                values["TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD"],
                8,
                "TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD",
            ),
            oracle_source_hash=keccak(b"TRUSTED_TEST_ORACLE"),
            authorization="OWNER_APPROVED",
        )
        return DeploymentProofConfig(
            proof_policy=policy,
            session_limit_usd_e8=limit,
            session_duration_seconds=integer(
                values, "TREASURY_SESSION_DURATION_SECONDS", "3600", minimum=31, maximum=604800
            ),
        )
    except OpsError:
        raise
    except Exception:
        raise OpsError(
            "Owner risk configuration failed validation; check positive caps and integer/bps ranges"
        ) from None


@dataclass(repr=False)
class Profile:
    root: Path
    network: str
    values: dict
    rpc: str
    deployment: Path
    execution_data: Path
    control_data: Path
    a_port: int
    b_port: int
    drift: int
    confirmations: int

    @classmethod
    def load(cls, root, env_file, network):
        v = read_env(env_file)
        n = network.upper()
        rpc = v.get(f"TREASURY_{n}_RPC_URL") or (
            v.get("B_FUJI_RPC_URL") or PUBLIC_RPC if network == "fuji" else "http://127.0.0.1:8545"
        )
        parsed = urlsplit(rpc)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or (
                parsed.scheme != "https"
                and not (
                    parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise OpsError("RPC must use HTTPS or loopback HTTP, without userinfo")
        if network == "local" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise OpsError("Local mode requires a loopback Anvil RPC")
        return cls(
            root,
            network,
            v,
            rpc,
            path_for(
                root,
                v.get(f"TREASURY_{n}_DEPLOYMENT_FILE", f"deployments/treasury-{network}-v2.json"),
            ),
            path_for(
                root,
                v.get(
                    f"TREASURY_{n}_DATA_DIR",
                    ".execution-data-fuji-v2" if network == "fuji" else ".execution-data-v2",
                ),
            ),
            path_for(root, v.get("TREASURY_CONTROL_DATA_DIR", ".control-data-v2")) / network,
            integer(v, "TREASURY_A_PORT", "8000", minimum=1, maximum=65535),
            integer(v, "TREASURY_B_PORT", "8001", minimum=1, maximum=65535),
            integer(
                v,
                f"TREASURY_{n}_MAX_BLOCK_DRIFT",
                "30" if network == "fuji" else "3",
                minimum=1,
                maximum=120,
            ),
            integer(
                v,
                f"TREASURY_{n}_CONFIRMATIONS",
                "2" if network == "fuji" else "1",
                minimum=1,
                maximum=100,
            ),
        )

    @property
    def chain_id(self):
        return 43113 if self.network == "fuji" else 31337

    def web3(self):
        return Web3(Web3.HTTPProvider(self.rpc, request_kwargs={"timeout": 5}))

    def credentials(self, *, require_owner_key=False):
        if self.network == "local":
            key_file = self.execution_data / "local-keys.json"
            if not key_file.exists():
                raise OpsError("Local deployment keys missing; run treasury local first")
            local = json.loads(key_file.read_text())
            return local["attestor"], local["relayer"]
        if self.values.get("FUJI_TEST_WALLETS_ONLY", "").lower() != "true":
            raise OpsError("Set FUJI_TEST_WALLETS_ONLY=true for dedicated test wallets")
        if self.values.get("B_FUJI_OWNER_PRIVATE_KEY"):
            owner_address = key_account(self.values, "B_FUJI_OWNER_PRIVATE_KEY").address
        elif not require_owner_key and self.deployment.is_file():
            owner_address = Web3.to_checksum_address(
                json.loads(self.deployment.read_text())["owner"]
            )
        else:
            raise OpsError(
                "Owner key is needed for deployment; serving needs an existing V2 manifest"
            )
        signer = key_account(self.values, "PACEVANT_ATTESTOR_KEY")
        relayer = key_account(self.values, "B_FUJI_RELAYER_PRIVATE_KEY")
        if len({owner_address.lower(), signer.address.lower(), relayer.address.lower()}) != 3:
            raise OpsError("Owner, attestor and relayer must be three distinct test wallets")
        configured = self.values.get("B_FUJI_ATTESTOR_ADDRESS")
        if configured and configured.lower() != signer.address.lower():
            raise OpsError("B_FUJI_ATTESTOR_ADDRESS does not match PACEVANT_ATTESTOR_KEY")
        return self.values["PACEVANT_ATTESTOR_KEY"], self.values["B_FUJI_RELAYER_PRIVATE_KEY"]


def safe_environment(extra):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("B_", "PACEVANT_", "TREASURY_", "FUJI_"))
        and k not in {"DEPLOYER_PRIVATE_KEY", "AGENT_PRIVATE_KEY", "AGENT_ADDRESS"}
    }
    return env | {k: str(v) for k, v in extra.items()}


def b_environment(p, *, deployment=False):
    values = {
        "B_MODE": p.network,
        "B_RPC_URL": p.rpc,
        "B_DEPLOYMENT_FILE": p.deployment,
        "B_DATA_DIR": p.execution_data,
        "B_API_KEY": p.values.get("B_API_KEY", ""),
        "B_MAX_BLOCK_DRIFT": p.drift,
        "B_REQUIRED_CONFIRMATIONS": p.confirmations,
        "B_ANVIL_BINARY": anvil_binary(),
    }
    if p.network == "fuji":
        signer, relayer = p.credentials(require_owner_key=deployment)
        values.update(
            B_RELAYER_PRIVATE_KEY=relayer, B_ATTESTOR_ADDRESS=Account.from_key(signer).address
        )
        if deployment:
            values["B_OWNER_PRIVATE_KEY"] = p.values["B_FUJI_OWNER_PRIVATE_KEY"]
    elif (p.execution_data / "local-keys.json").exists():
        _, relayer = p.credentials()
        values["B_RELAYER_PRIVATE_KEY"] = relayer
    return safe_environment(values)


def a_environment(p, *, source_root=None):
    signer, relayer = p.credentials()
    values = {
        "PACEVANT_MODE": p.network.upper(),
        "PACEVANT_DB": p.control_data / "control.sqlite3",
        "PACEVANT_MANDATE_FILE": p.control_data / "mandate.json",
        "PACEVANT_ORACLE_FILE": p.control_data / "oracle.json",
        "PACEVANT_B_URL": f"http://127.0.0.1:{p.b_port}",
        "PACEVANT_B_TOKEN": p.values.get("B_API_KEY", ""),
        "PACEVANT_OPERATOR_TOKEN": p.values.get("PACEVANT_OPERATOR_TOKEN", ""),
        "PACEVANT_INTERNAL_TOKEN": p.values.get("PACEVANT_INTERNAL_TOKEN", ""),
        "PACEVANT_ATTESTOR_KEY": signer,
        "PACEVANT_CHAIN_RPC_URL": p.rpc,
        "PACEVANT_RELAYER_ADDRESS": Account.from_key(relayer).address,
        "PACEVANT_MAX_BLOCK_DRIFT": p.drift,
        "PACEVANT_FUJI_VERIFICATION_RPC": p.values.get("PACEVANT_FUJI_VERIFICATION_RPC")
        or PUBLIC_RPC,
    }
    if source_root:
        values["PYTHONPATH"] = os.pathsep.join(
            (str(source_root / "apps/control-plane"), str(source_root / "packages/contracts-api"))
        )
    return safe_environment(values)


def artifact(p, name):
    path = p.root / "out" / f"{name}.sol" / f"{name}.json"
    if not path.exists():
        raise OpsError(
            "Contract artifacts missing; run uv run python scripts/foundry.py forge build"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def deployed(p):
    if not p.deployment.exists():
        raise OpsError("V2 deployment missing; deploy the selected network first")
    data = json.loads(p.deployment.read_text(encoding="utf-8"))
    w3 = p.web3()
    if w3.eth.chain_id != p.chain_id or data.get("chain_id") != p.chain_id:
        raise OpsError("RPC/deployment chain mismatch")
    if data.get("pdr_version") != "2":
        raise OpsError("Selected manifest is not a V2 deployment")
    for name, field in (
        ("PolicyVault", "vault_address"),
        ("MockSwapAdapter", "router"),
        ("MockUSDC", "token_in"),
        ("MockWAVAX", "token_out"),
    ):
        if (
            keccak(w3.eth.get_code(Web3.to_checksum_address(data[field])))
            != data["bytecode_hashes"][name]
        ):
            raise OpsError("Deployed code mismatch: " + name)
    vault = w3.eth.contract(
        address=Web3.to_checksum_address(data["vault_address"]),
        abi=artifact(p, "PolicyVault")["abi"],
    )
    return data, w3, vault


def refresh_oracle(p):
    data = json.loads(p.deployment.read_text(encoding="utf-8"))
    w3 = p.web3()
    if w3.eth.chain_id != p.chain_id:
        raise OpsError("Oracle updater chain mismatch")
    if p.network == "local":
        if not w3.client_version.lower().startswith("anvil"):
            raise OpsError("Local oracle requires Anvil")
        w3.provider.make_request("evm_mine", [])
    block = w3.eth.get_block("latest")
    if not 0 <= int(time.time()) - block.timestamp <= 60:
        raise OpsError("Oracle updater refuses a stale/future chain head")
    prices = (
        units(p.values.get("TREASURY_ORACLE_USDC_USD", "1"), 8, "TREASURY_ORACLE_USDC_USD"),
        units(p.values.get("TREASURY_ORACLE_WAVAX_USD", "20"), 8, "TREASURY_ORACLE_WAVAX_USD"),
    )
    if min(map(int, prices)) <= 0:
        raise OpsError("Controlled oracle prices must be positive")
    value = {
        "chain_id": p.chain_id,
        "vault_address": data["vault_address"].lower(),
        "price_source": "TRUSTED_TEST_ORACLE",
        "price_usdc_usd_e8": prices[0],
        "price_wavax_usd_e8": prices[1],
        "price_timestamp": int(time.time()),
    }
    atomic_json(p.control_data / "oracle.json", value)
    return {
        "source": "CONTROLLED_DEMO_ORACLE",
        "timestamp": value["price_timestamp"],
        "chain_block": block.number,
    }


def prepare(p):
    data, w3, vault = deployed(p)
    if vault.functions.owner().call().lower() != data["owner"].lower():
        raise OpsError("Deployment manifest owner does not match the vault")
    signer, relayer = p.credentials()
    if vault.functions.attestor().call().lower() != Account.from_key(signer).address.lower():
        raise OpsError("Attestor key does not match deployed vault")
    if data["relayer"].lower() != Account.from_key(relayer).address.lower():
        raise OpsError("Relayer key does not match deployment")
    context = read_v2_context(w3, data["vault_address"], data["session_id"], required=True)
    if p.network == "fuji" and context["proof_policy"] != owner_config(
        p.values
    ).proof_policy.model_dump(mode="json"):
        raise OpsError("Owner .env risk policy differs from the deployed policy; renew explicitly")
    session = context["proof_session"]
    active_hash = Web3.to_hex(vault.functions.activePolicyHash().call())
    if (
        not session["active"]
        or not session["starts_at"] <= int(time.time()) < session["expires_at"]
        or session["policy_hash"] != active_hash
    ):
        raise OpsError(
            "Session is inactive/expired or bound to an old policy; run treasury renew-session"
        )
    if (
        not vault.functions.policyActive().call()
        or vault.functions.paused().call()
        or vault.functions.policyExpiresAt().call() <= int(time.time())
    ):
        raise OpsError("Vault policy unavailable or paused")
    mandate = {
        "mandate_id": "mandate_demo",
        "version": 1,
        "chain_id": p.chain_id,
        **{
            k: data[k].lower()
            for k in ("vault_address", "owner", "router", "token_in", "token_out")
        },
        "policy_hash": active_hash,
        "max_usdc_per_swap_base_units": str(vault.functions.maxPerSwap().call()),
        "max_usdc_spend_per_day_base_units": str(vault.functions.maxSpendPerDay().call()),
        "max_daily_execution_cost_usd_e8": "5000000000",
        "max_avax_exposure_bps": 2500,
        "max_slippage_bps": vault.functions.maxSlippageBps().call(),
        "max_replans": 2,
        "expires_at": vault.functions.policyExpiresAt().call(),
        "status": "ACTIVE",
        "required_stress": {
            "reserve_shift_mild": "SUCCESS_REQUIRED",
            "reserve_shift_adverse": "PROTECTED_REVERT_ALLOWED",
        },
        "proof_policy": context["proof_policy"],
        "registry": context["registry"],
        "session_id": data["session_id"],
    }
    atomic_json(p.control_data / "mandate.json", mandate)
    refresh_oracle(p)
    return {
        "network": p.network,
        "chain_id": p.chain_id,
        "vault": data["vault_address"],
        "session_id": data["session_id"],
        "mandate_file": str(p.control_data / "mandate.json"),
        "oracle_file": str(p.control_data / "oracle.json"),
    }


def compile_contracts(root=ROOT):
    subprocess.run(
        [foundry_binary("forge", ROOT), "build", "--root", str(root)],
        cwd=ROOT,
        check=True,
    )


def execution_python():
    path = (
        ROOT
        / "apps/execution-plane/.venv"
        / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    )
    if not path.exists():
        raise OpsError(
            "Execution environment missing; run uv sync --project apps/execution-plane --locked"
        )
    return str(path)


def deploy_v2(p):
    if p.network == "fuji":
        p.credentials(require_owner_key=True)
        config = owner_config(p.values)
        if p.deployment.exists():
            raise OpsError(
                "Deployment manifest already exists; select a NEW manifest to avoid overwriting Fuji history"
            )
    else:
        config = DeploymentProofConfig.model_validate_json(
            (ROOT / "fixtures/v2_1/TEST_ONLY_policy.json").read_text()
        )
    p.control_data.mkdir(parents=True, exist_ok=True)
    file = p.control_data / "risk-policy.json"
    atomic_json(file, config.model_dump(mode="json"))
    env = b_environment(p, deployment=True)
    command = [
        execution_python(),
        "-m",
        "app.cli",
        "deploy-" + p.network,
        "--env-file",
        str(p.control_data / "no-owner-runtime.env"),
        "--v2-config",
        str(file),
    ]
    env["PYTHONPATH"] = os.pathsep.join(
        (str(p.root / "apps/execution-plane"), str(p.root / "packages/contracts-api"))
    )
    result = subprocess.run(
        command,
        cwd=p.root / "apps/execution-plane",
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise OpsError(
            "Deployment failed; no secret output forwarded. Check RPC, gas funding and configuration using doctor"
        )
    return prepare(p)


def check_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            raise OpsError(
                f"Port {port} is in use; choose another TREASURY_A_PORT/TREASURY_B_PORT"
            ) from None


def renew(p, *, policy=False):
    data, w3, vault = deployed(p)
    config = (
        owner_config(p.values)
        if p.network == "fuji"
        else DeploymentProofConfig.model_validate_json(
            (ROOT / "fixtures/v2_1/TEST_ONLY_policy.json").read_text()
        )
    )
    p.credentials()
    if p.network == "fuji":
        owner = key_account(p.values, "B_FUJI_OWNER_PRIVATE_KEY")
    else:
        owner = Account.from_key(
            json.loads((p.execution_data / "local-keys.json").read_text())["owner"]
        )
    if owner.address.lower() != vault.functions.owner().call().lower():
        raise OpsError("Configured owner does not own this deployment")
    receipts = []

    def send(fn):
        tx = fn.build_transaction(
            {
                "from": owner.address,
                "nonce": w3.eth.get_transaction_count(owner.address, "pending"),
                "chainId": p.chain_id,
                "gasPrice": w3.eth.gas_price,
            }
        )
        receipt = w3.eth.wait_for_transaction_receipt(
            w3.eth.send_raw_transaction(owner.sign_transaction(tx).raw_transaction), timeout=90
        )
        if receipt.status != 1:
            raise OpsError("Owner configuration transaction reverted")
        receipts.append(
            {"tx_hash": Web3.to_hex(receipt.transactionHash), "block": receipt.blockNumber}
        )

    if policy:
        send(
            vault.functions.configureProofPolicy(
                Web3.to_checksum_address(data["router"]), config.proof_policy.abi_tuple
            )
        )
        send(
            vault.functions.configurePolicy(
                keccak(b"OWNER_DEMO_RENEWAL" + secrets.token_bytes(32)),
                vault.functions.maxPerSwap().call(),
                vault.functions.maxSpendPerDay().call(),
                vault.functions.maxSlippageBps().call(),
                w3.eth.get_block("latest").timestamp + 604800,
            )
        )
    current = read_v2_context(w3, data["vault_address"], data["session_id"], required=True)
    if current["proof_policy"] != config.proof_policy.model_dump(mode="json"):
        raise OpsError("Policy differs; use explicit renew-policy after owner review")
    now = w3.eth.get_block("latest").timestamp
    if (
        not vault.functions.policyActive().call()
        or vault.functions.policyExpiresAt().call() <= now + 30
    ):
        raise OpsError("Owner policy expired/revoked; explicit renew-policy required")
    id_ = keccak(secrets.token_bytes(32))
    send(
        vault.functions.createSession(
            id_,
            now,
            min(now + config.session_duration_seconds, vault.functions.policyExpiresAt().call()),
            int(config.session_limit_usd_e8),
        )
    )
    data.update(session_id=id_, policy_hash=Web3.to_hex(vault.functions.activePolicyHash().call()))
    data.setdefault("owner_renewals", []).append(
        {"policy_changed": policy, "session_id": id_, "transactions": receipts}
    )
    atomic_json(p.deployment, data)
    return prepare(p) | {
        "owner_transactions": receipts,
        "global_and_daily_counters_reset": False,
        "restart_services_required": True,
    }


def stop_process(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def anvil_binary(root=ROOT):
    return foundry_binary("anvil", root)


@contextmanager
def local_chain(p):
    if p.network != "local":
        yield
        return
    w3 = p.web3()
    proc = None
    try:
        if not w3.is_connected():
            u = urlsplit(p.rpc)
            p.control_data.mkdir(parents=True, exist_ok=True)
            with (p.control_data / "anvil.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(
                    [
                        anvil_binary(),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(u.port or 8545),
                        "--chain-id",
                        "31337",
                        "--hardfork",
                        "cancun",
                        "--silent",
                    ],
                    stdout=log,
                    stderr=log,
                )
            for _ in range(100):
                if w3.is_connected():
                    break
                if proc.poll() is not None:
                    raise OpsError("Anvil startup failed")
                time.sleep(0.1)
            else:
                raise OpsError("Anvil startup timed out")
        if not w3.client_version.lower().startswith("anvil") or w3.eth.chain_id != 31337:
            raise OpsError("Local target is not Anvil chain 31337")
        # The oracle heartbeat mines a fresh LOCAL block every five seconds;
        # no persistent mining configuration of an existing user node is changed.
        yield
    finally:
        if proc:
            stop_process(proc)


def wait_ready(proc, url):
    for _ in range(200):
        if proc.poll() is not None:
            raise OpsError("Service exited; inspect the private profile log directory")
        try:
            if httpx.get(url, timeout=0.4, trust_env=False).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise OpsError("Service readiness timed out")


@contextmanager
def services(p, *, public_host="127.0.0.1"):
    prepare(p)
    check_port(p.a_port)
    check_port(p.b_port)
    children = []
    logs = []
    stop = Event()

    def heartbeat():
        while not stop.wait(5):
            try:
                refresh_oracle(p)
            except Exception:
                # Never stamp fresh evidence after an RPC failure. The signer will reject stale prices.
                pass

    thread = Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        for role, command, cwd, env, url in (
            (
                "execution",
                [
                    execution_python(),
                    "-m",
                    "app.cli",
                    "serve",
                    "--network",
                    p.network,
                    "--port",
                    str(p.b_port),
                    "--env-file",
                    str(p.control_data / "no-owner-runtime.env"),
                ],
                p.root / "apps/execution-plane",
                b_environment(p),
                f"http://127.0.0.1:{p.b_port}/health",
            ),
            (
                "control",
                [
                    sys.executable,
                    str(p.root / "scripts/serve.py"),
                    "--host",
                    public_host,
                    "--port",
                    str(p.a_port),
                ],
                p.root,
                a_environment(p),
                f"http://127.0.0.1:{p.a_port}/healthz",
            ),
        ):
            env["PYTHONPATH"] = os.pathsep.join(
                (
                    str(
                        p.root
                        / f"apps/{'execution-plane' if role == 'execution' else 'control-plane'}"
                    ),
                    str(p.root / "packages/contracts-api"),
                )
            )
            log = (p.control_data / f"{role}.log").open("a", encoding="utf-8")
            logs.append(log)
            proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log)
            children.append(proc)
            wait_ready(proc, url)
        yield children
    finally:
        stop.set()
        thread.join(timeout=6)
        for proc in reversed(children):
            stop_process(proc)
        for log in logs:
            log.close()


def demo(p, goal="Buy WAVAX with 200 USDC"):
    # Only the real A workflow can obtain an application signature.
    with httpx.Client(
        base_url=f"http://127.0.0.1:{p.a_port}",
        headers={"Authorization": "Bearer " + p.values.get("PACEVANT_OPERATOR_TOKEN", "")},
        timeout=90,
        trust_env=False,
    ) as client:
        response = client.post(
            "/v1/workflows/start", json={"mandate_id": "mandate_demo", "goal": goal}
        )
        if response.status_code != 200:
            raise OpsError("Workflow request rejected; check credentials and the control log")
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
