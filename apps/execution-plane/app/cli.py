"""Bootstrap/deploy/demo are operator CLI commands, never public signing endpoints."""

import argparse
import json
import secrets
import time
import subprocess
import socket
from pathlib import Path
from eth_account import Account
from web3 import Web3
from .chain import Chain, artifact
from .crypto import (
    canonical,
    content_hash,
    keccak,
    message,
    approval_for,
    domain_for,
    digest,
)
from .models import TransactionProposal, BuiltTransaction, SignedPDR, ExecutionRequest
from .settings import ROOT, Settings, DeploymentSettings
from .store import Store
from .transaction.builder import Builder
from .simulation.runner import Simulator, rpc
from .execution.relayer import Relayer
from .configuration import portable_path, update_env
from .errors import PlaneError


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def send(w3, account, fn):
    if w3.eth.chain_id not in {31337, 43113}:
        raise PlaneError(
            "CHAIN_MISMATCH", "Only local Anvil or Avalanche Fuji writes are permitted"
        )
    tx = fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address, "pending"),
            "chainId": w3.eth.chain_id,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = account.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction), timeout=90
    )
    if receipt.status != 1:
        raise RuntimeError("Deployment/configuration reverted")
    return receipt


def deploy(settings, fuji=False, write_env=True, env_file=None):
    if fuji:
        from .dex.deploy import deploy_lfj

        return deploy_lfj(settings)  # Existing callers are dry-run by default.
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": settings.rpc_timeout}))
    if not w3.client_version.lower().startswith("anvil"):
        raise RuntimeError("Local bootstrap is only allowed against Anvil")
    from urllib.parse import urlparse

    if urlparse(settings.rpc_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Local bootstrap requires loopback RPC")
    owner, signer, relayer = Account.create(), Account.create(), Account.create()
    attestor = signer.address
    for account in (owner, relayer):
        rpc(w3, "anvil_setBalance", [account.address, hex(100 * 10**18)])

    def create(name, args):
        a = artifact(name)
        receipt = send(
            w3,
            owner,
            w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"]["object"]).constructor(*args),
        )
        return w3.eth.contract(address=receipt.contractAddress, abi=a["abi"])

    usdc, wavax = (
        create("MockUSDC", [owner.address]),
        create("MockWAVAX", [owner.address]),
    )
    router = create("MockSwapAdapter", [owner.address, usdc.address, wavax.address])
    vault = create("PolicyVault", [owner.address, attestor, usdc.address, wavax.address])
    send(w3, owner, vault.functions.setRouter(router.address, True))
    send(
        w3,
        owner,
        vault.functions.configurePolicy(
            content_hash(
                {
                    "mandate_id": "mandate_demo",
                    "version": 1,
                    "max_exposure_bps": 2500,
                    "max_replans": 2,
                }
            ),
            500 * 10**6,
            1000 * 10**6,
            100,
            int(time.time()) + 86400 * 7,
        ),
    )
    send(w3, owner, usdc.functions.mint(vault.address, 7700 * 10**6))
    send(w3, owner, wavax.functions.mint(vault.address, 115 * 10**18))
    send(w3, owner, wavax.functions.mint(router.address, 100000 * 10**18))
    deployment = {
        "schema_version": "1.1",
        "mode": "fuji" if fuji else "local",
        "chain_id": w3.eth.chain_id,
        "vault_address": vault.address,
        "router": router.address,
        "token_in": usdc.address,
        "token_out": wavax.address,
        "owner": owner.address,
        "attestor": attestor,
        "relayer": relayer.address,
        "policy_hash": Web3.to_hex(vault.functions.activePolicyHash().call()),
        "deployment_block": w3.eth.block_number,
        "bytecode_hashes": {
            name: keccak(w3.eth.get_code(obj.address))
            for name, obj in [
                ("PolicyVault", vault),
                ("MockSwapAdapter", router),
                ("MockUSDC", usdc),
                ("MockWAVAX", wavax),
            ]
        },
    }
    save(settings.deployment_file, deployment)
    if not fuji:
        save(
            settings.data_dir / "local-keys.json",
            {
                "owner": owner.key.hex(),
                "attestor": signer.key.hex(),
                "relayer": relayer.key.hex(),
                "warning": "EPHEMERAL LOCAL ANVIL KEYS ONLY; NOT VALID FOR FUJI",
            },
        )
        if write_env:
            update_env(
                env_file or ROOT / ".env",
                {
                    "B_LOCAL_RPC_URL": settings.rpc_url,
                    "B_LOCAL_DEPLOYMENT_FILE": portable_path(settings.deployment_file),
                    "B_LOCAL_DATA_DIR": portable_path(settings.data_dir),
                    "B_API_KEY": settings.api_key.get_secret_value() or secrets.token_hex(32),
                    "B_LOCAL_RELAYER_PRIVATE_KEY": relayer.key.hex(),
                },
            )
    return deployment


def demo(settings):
    if settings.mode != "local":
        raise RuntimeError(
            "Demo CLI signs ONLY on local Anvil. Fuji PDR must come from A's SDE attestor."
        )
    chain, store = Chain(settings), Store(settings.data_dir)
    keys = json.loads((settings.data_dir / "local-keys.json").read_text())
    settings = Settings(**{**settings.model_dump(), "relayer_private_key": keys["relayer"]})
    chain.settings = settings
    rpc(chain.w3, "evm_mine", [])
    c = chain.context()
    p = TransactionProposal(
        intent_id="intent_local_" + secrets.token_hex(4),
        mandate_id="mandate_demo",
        mandate_version=1,
        action="SWAP_EXACT_INPUT",
        chain_id=c["chain_id"],
        vault_address=c["vault_address"],
        router=c["router"],
        token_in=c["token_in"],
        token_out=c["token_out"],
        amount_in_base_units="200000000",
        slippage_bps=40,
        recipient=c["vault_address"],
        deadline=min(int(time.time()), c["timestamp"]) + 29,
        user_goal_reason="Local B execution acceptance demo; A decision logic not exercised",
    )
    with store.lock:
        built = BuiltTransaction.model_validate(Builder(chain, store).build(p))
        evidence = Simulator(chain, store).simulate(built.build_id, built.policy_hash)
        approval = approval_for(built, evidence["evidence_root"])
        domain = domain_for(built)
        signature = Account.sign_message(message(domain, approval), keys["attestor"]).signature
        pdr = SignedPDR(
            decision_id="LOCAL_TEST_ONLY_NO_SDE",
            build_id=built.build_id,
            domain=domain,
            approval=approval,
            signature=Web3.to_hex(signature),
            typed_data_hash=digest(domain, approval),
        )
        submitted = Relayer(chain, store).execute(
            ExecutionRequest(build_id=built.build_id, signed_pdr=pdr)
        )
        result = Relayer(chain, store).monitor(submitted["tx_hash"])
        bundle = {
            "source": "REAL_LOCAL_SIM",
            "a_sde_exercised": False,
            "proposal": p.model_dump(),
            "built_transaction": built.model_dump(),
            "simulation_evidence": evidence,
            "signed_pdr": pdr.model_dump(),
            "execution_result": result,
        }
        save(ROOT / "evidence/execution-plane-local.json", bundle)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "tx_hash": result["tx_hash"],
                    "verification_status": evidence["verification_status"],
                    "stress_tests": evidence["stress_tests"],
                },
                indent=2,
            )
        )
        if result["status"] != "CONFIRMED":
            raise RuntimeError("Demo did not confirm")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "deploy-local",
            "deploy-fuji",
            "demo",
            "schemas",
            "golden",
            "fixtures",
            "serve",
            "config",
            "migrate-env",
            "start-local",
            "lfj-preflight",
            "lfj-execute",
        ],
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--network", choices=["local", "fuji"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--broadcast",
        action="store_true",
        help="Requires separate operator authorization setting for Fuji writes",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--fund-amount",
        type=int,
        default=0,
        help="LFJ test USDC base units to transfer from owner after authorized deploy",
    )
    parser.add_argument(
        "--request-file", type=Path, help="ExecutionRequest JSON with Signed PDR from A"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "schemas":
        from . import models

        for name in [
            "TransactionProposal",
            "BuiltTransaction",
            "SimulationEvidence",
            "SignedPDR",
            "ExecutionResult",
            "SimulationRequest",
            "ExecutionRequest",
            "ExecutionSubmission",
            "ChainContext",
            "OnchainSnapshot",
            "ErrorDetail",
            "ErrorEnvelope",
            "ApprovalChainState",
        ]:
            save(
                ROOT / f"packages/contracts-api/{name}.schema.json",
                getattr(models, name).model_json_schema(),
            )
        from .api.main import create_app

        save(ROOT / "packages/contracts-api/openapi.json", create_app().openapi())
        save(
            ROOT / "packages/contracts-api/treasury_contracts/abi/PolicyVault.json",
            artifact("PolicyVault")["abi"],
        )
    elif args.command == "golden":
        from .golden import generate

        generate()
    elif args.command == "fixtures":
        from .sample_fixtures import generate

        generate()
    elif args.command == "migrate-env":
        from .configuration import migrate_env

        print(json.dumps(migrate_env(), indent=2))
    else:
        settings_type = (
            DeploymentSettings if args.command in {"deploy-fuji", "config"} else Settings
        )
        env_file = (args.env_file or ROOT / ".env").resolve()
        required_mode = (
            "fuji"
            if args.command in {"deploy-fuji", "lfj-preflight", "lfj-execute"}
            else "local"
            if args.command in {"deploy-local", "demo", "start-local"}
            else None
        )
        if required_mode and args.network and args.network != required_mode:
            parser.error(f"{args.command} requires --network {required_mode}")
        overrides = {"mode": required_mode or args.network} if required_mode or args.network else {}
        settings = settings_type(_env_file=env_file, **overrides)
        if args.command in {"lfj-preflight", "deploy-fuji"}:
            from .dex.deploy import deploy_lfj

            result = deploy_lfj(
                settings_type(_env_file=env_file, **overrides)
                if args.command == "deploy-fuji"
                else DeploymentSettings(_env_file=env_file, **overrides),
                broadcast=args.command == "deploy-fuji" and args.broadcast and not args.dry_run,
                fund_amount=args.fund_amount,
            )
            if args.output:
                save(args.output, result)
            print(json.dumps(result, indent=2))
        elif args.command == "lfj-execute":
            if not args.request_file:
                parser.error("lfj-execute requires --request-file from A's SDE")
            request = ExecutionRequest.model_validate_json(args.request_file.read_bytes())
            chain = Chain(settings)
            store = Store(settings.data_dir)
            with store.lock:
                result = Relayer(chain, store).execute(
                    request, dry_run=not args.broadcast or args.dry_run
                )
                print(json.dumps(result, indent=2))
        elif args.command == "demo":
            demo(settings)
        elif args.command == "serve":
            serve(settings, args.host, args.port)
        elif args.command == "start-local":
            start_local(settings, env_file, args.host, args.port)
        elif args.command == "config":
            from urllib.parse import urlparse

            print(
                json.dumps(
                    {
                        "env_file": str(env_file),
                        "network": settings.mode,
                        "rpc_host": urlparse(settings.rpc_url).hostname,
                        "deployment_file": portable_path(settings.deployment_file),
                        "data_dir": portable_path(settings.data_dir),
                        "api_key_configured": bool(settings.api_key.get_secret_value()),
                        "relayer_key_configured": bool(
                            settings.relayer_private_key.get_secret_value()
                        ),
                        "attestor_address": settings.attestor_address or None,
                        "owner_key_configured": bool(settings.owner_private_key.get_secret_value()),
                    },
                    indent=2,
                )
            )
        else:
            print(
                json.dumps(
                    deploy(settings, args.command == "deploy-fuji", env_file=env_file),
                    indent=2,
                )
            )


def serve(settings, host="127.0.0.1", port=8001):
    import uvicorn
    from .api.main import create_app

    uvicorn.run(create_app(settings), host=host, port=port)


def start_local(settings, env_file, host, port):
    """One command: compile, reuse/start Anvil, bootstrap if needed, serve API."""
    from urllib.parse import urlparse

    endpoint = urlparse(settings.rpc_url)
    if endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Local stack requires loopback RPC")
    with socket.socket() as probe:
        try:
            probe.bind((host, port))
        except OSError:
            raise RuntimeError(
                f"API port {port} is already in use; stop the existing API or use --port"
            ) from None
    subprocess.run(
        ["node", str(ROOT / "scripts/foundry.mjs"), "forge", "build"],
        cwd=ROOT,
        check=True,
    )
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 2}))
    process = None
    try:
        if not w3.is_connected():
            process = subprocess.Popen(
                [
                    settings.anvil_binary,
                    "--host",
                    endpoint.hostname,
                    "--port",
                    str(endpoint.port or 8545),
                    "--chain-id",
                    "31337",
                    "--hardfork",
                    "cancun",
                    "--silent",
                ]
            )
            print(f"Started local Anvil (PID {process.pid})", flush=True)
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Anvil could not start")
                if w3.is_connected():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Anvil startup timeout")
        if not w3.client_version.lower().startswith("anvil"):
            raise RuntimeError("Local stack requires Anvil")
        if w3.eth.chain_id != 31337:
            raise RuntimeError("Local stack requires Anvil chain 31337")
        if not settings.api_key.get_secret_value():
            update_env(env_file, {"B_API_KEY": secrets.token_hex(32)})
            settings = Settings(_env_file=env_file, mode="local")
        needs_deploy = (
            not settings.deployment_file.is_file()
            or not settings.relayer_private_key.get_secret_value()
        )
        if not needs_deploy:
            try:
                Chain(settings)
            except (ValueError, OSError, RuntimeError, PlaneError):
                needs_deploy = True
        if needs_deploy:
            print(
                "Bootstrapping local mock deployment and updating .env profile...",
                flush=True,
            )
            deploy(settings, env_file=env_file)
            settings = Settings(_env_file=env_file, mode="local")
        # Keep local timestamps fresh while A's UI/planner is idle. Source RPC is
        # explicitly a loopback Anvil, never Fuji; simulations remain isolated.
        rpc(w3, "evm_mine", [])
        rpc(w3, "evm_setIntervalMining", [2])
        print(f"Execution Plane local: http://{host}:{port}/docs", flush=True)
        serve(settings, host, port)
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
