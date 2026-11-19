import json
import os
import secrets
import subprocess
import time

from eth_account import Account
from web3 import Web3

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.execution.dex.lfj import ADAPTER_VERSION
from treasury_backend.modules.oracle import JsonFilePriceProvider
from treasury_backend.modules.oracle.demo import snapshot as demo_snapshot
from treasury_backend.paths import ROOT
from treasury_contracts.onchain_v2 import read_v2_context
from treasury_contracts.v2 import DeploymentProofConfig, keccak

from .env import atomic_json, key_account, units
from .environments import b_environment
from .errors import OpsError
from .processes import execution_python
from .profiles import owner_config


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
    is_lfj = data.get("adapter_version") == ADAPTER_VERSION
    for name, field in (
        ("PolicyVault", "vault_address"),
        ("LFJSwapAdapter" if is_lfj else "MockSwapAdapter", "router"),
        ("USDC" if is_lfj else "MockUSDC", "token_in"),
        ("WAVAX" if is_lfj else "MockWAVAX", "token_out"),
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
    if data.get("adapter_version") == ADAPTER_VERSION and p.values.get("TREASURY_ORACLE_MODE") != "chainlink":
        return {"source": "REFERENCE_ONLY", "reason": "ORACLE_TOKEN_IDENTITY_MISMATCH"}
    mode = p.values.get("TREASURY_ORACLE_MODE", "demo")
    if mode == "chainlink":
        from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
        from treasury_contracts.oracle import CIRCLE_USDC, WAVAX

        if (data["token_in"].lower(), data["token_out"].lower()) != (CIRCLE_USDC, WAVAX):
            raise OpsError("Chainlink reference policy requires Circle USDC and Fuji WAVAX")
        value = ChainlinkPriceProvider(p.rpc, data["vault_address"]).read()
        atomic_json(p.control_data / "oracle.json", value.model_dump(mode="json"))
        return {"source": value.price_source, "timestamp": value.price_timestamp}
    if mode == "external":
        value = JsonFilePriceProvider(p.control_data / "oracle.json").read()
        if (value.chain_id, value.vault_address) != (p.chain_id, data["vault_address"].lower()):
            raise OpsError("External oracle scope does not match the deployment")
        return {"source": "EXTERNAL_WRITER", "timestamp": value.price_timestamp}
    if mode != "demo":
        raise OpsError("TREASURY_ORACLE_MODE must be demo, external or chainlink")
    prices = (
        units(p.values.get("TREASURY_ORACLE_USDC_USD", "1"), 8, "TREASURY_ORACLE_USDC_USD"),
        units(p.values.get("TREASURY_ORACLE_WAVAX_USD", "20"), 8, "TREASURY_ORACLE_WAVAX_USD"),
    )
    try:
        value, block = demo_snapshot(
            p.web3(),
            chain_id=p.chain_id,
            vault=data["vault_address"],
            prices=prices,
            local=p.network == "local",
        )
    except ControlError as exc:
        raise OpsError(exc.code) from None
    atomic_json(p.control_data / "oracle.json", value.model_dump(mode="json"))
    return {
        "source": "CONTROLLED_DEMO_ORACLE",
        "timestamp": value.price_timestamp,
        "chain_block": block,
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
    if p.network == "fuji" and vault.functions.maxApprovalTtl().call() != owner_config(p.values).approval_ttl_seconds:
        raise OpsError("Owner approval TTL differs from deployed configuration; use renew-policy")
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


def deploy_v2(p, *, adapter="mock"):
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
        "treasury_backend.operations.execution",
        "deploy-" + p.network,
        "--env-file",
        str(p.control_data / "no-owner-runtime.env"),
        "--v2-config",
        str(file),
        "--adapter",
        adapter,
        "--lfj-token",
        "circle" if p.values.get("TREASURY_ORACLE_MODE") == "chainlink" else "faucet",
    ]
    env["PYTHONPATH"] = os.pathsep.join(
        (str(p.root / "backend/src"), str(p.root / "packages/contracts-api"))
    )
    result = subprocess.run(
        command,
        cwd=p.root,
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
        if vault.functions.maxApprovalTtl().call() != config.approval_ttl_seconds:
            send(vault.functions.setApprovalTtl(config.approval_ttl_seconds))
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
