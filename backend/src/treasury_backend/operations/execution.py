"""Bootstrap/deploy/demo are operator CLI commands, never public signing endpoints."""

import argparse
import json
import secrets
import socket
import subprocess
import time
from pathlib import Path

from eth_account import Account
from web3 import Web3

from treasury_backend.config.execution import ROOT, DeploymentSettings, Settings
from treasury_backend.modules.execution.chain import Chain, artifact
from treasury_backend.modules.execution.crypto import (
    approval_for,
    canonical,
    content_hash,
    digest,
    domain_for,
    keccak,
    message,
)
from treasury_backend.modules.execution.dex.lfj import (
    ADAPTER_VERSION,
    CIRCLE_USDC,
    ROUTER,
    USDC,
    WAVAX,
    LFJClient,
)
from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.execution.models import (
    BuiltTransaction,
    ExecutionRequest,
    SignedPDR,
    TransactionProposal,
)
from treasury_backend.modules.execution.relaying.relayer import Relayer
from treasury_backend.modules.execution.simulation.runner import Simulator, rpc
from treasury_backend.modules.execution.storage import Store
from treasury_backend.modules.execution.transaction.builder import Builder
from treasury_backend.operations.configuration import portable_path, update_env
from treasury_contracts.toolchain import foundry_binary


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def send(w3, account, fn):
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


def deploy(settings, fuji=False, write_env=True, env_file=None, v2_config=None, adapter="mock", lfj_token="faucet"):
    from treasury_contracts.v2 import DeploymentProofConfig

    if v2_config is not None:
        v2_config = DeploymentProofConfig.model_validate(v2_config)
        if fuji and v2_config.proof_policy.authorization != "OWNER_APPROVED":
            raise RuntimeError("Fuji V2 requires explicit owner-approved risk configuration")
    is_lfj = adapter == "lfj"
    usdc_address = CIRCLE_USDC if lfj_token == "circle" else USDC
    if is_lfj and not (fuji and v2_config):
        raise RuntimeError("LFJ deployment requires Fuji and V2 policy configuration")
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": settings.rpc_timeout}))
    if fuji:
        if settings.mode != "fuji" or w3.eth.chain_id != 43113:
            raise RuntimeError("Fuji mode and chain 43113 required")
        if (
            not settings.owner_private_key.get_secret_value()
            or not settings.attestor_address
            or not settings.relayer_private_key.get_secret_value()
        ):
            raise RuntimeError(
                "Configure B_FUJI_OWNER_PRIVATE_KEY, B_FUJI_ATTESTOR_ADDRESS (public address from A), and B_FUJI_RELAYER_PRIVATE_KEY in .env before Fuji deploy"
            )
        owner = Account.from_key(settings.owner_private_key.get_secret_value())
        attestor = Web3.to_checksum_address(settings.attestor_address)
        relayer = Account.from_key(settings.relayer_private_key.get_secret_value())
        if len({owner.address.lower(), attestor.lower(), relayer.address.lower()}) != 3:
            raise RuntimeError("Owner, A's attestor and relayer must differ")
        # B never creates or loads A's Fuji attestor private key.
    else:
        if not w3.client_version.lower().startswith("anvil"):
            raise RuntimeError("Local bootstrap is only allowed against Anvil")
        from urllib.parse import urlparse

        if urlparse(settings.rpc_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("Local bootstrap requires loopback RPC")
        owner, signer, relayer = Account.create(), Account.create(), Account.create()
        attestor = signer.address
        for account in (owner, relayer):
            rpc(w3, "anvil_setBalance", [account.address, hex(100 * 10**18)])

    deployment_receipts = []

    def owner_send(fn):
        if not fuji:
            return send(w3, owner, fn)
        from types import SimpleNamespace

        from treasury_backend.operations.fuji_demo import send_setup

        deployment_scope = keccak(str(settings.deployment_file.resolve()).encode())[2:14]
        label = "deploy-" + deployment_scope + "-" + str(len(deployment_receipts) + 1)
        profile = SimpleNamespace(web3=lambda: w3, control_data=settings.data_dir)
        journal = settings.data_dir / "fuji-setup" / (label + ".json")
        tx = {} if journal.exists() else fn.build_transaction({
            "from": owner.address, "nonce": w3.eth.get_transaction_count(owner.address, "pending"),
            "chainId": 43113, "gasPrice": w3.eth.gas_price,
        })
        public = send_setup(profile, owner, label, tx)
        deployment_receipts.append(public)
        return w3.eth.get_transaction_receipt(public["tx_hash"])

    def create(name, args):
        a = artifact(name)
        receipt = owner_send(
            w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"]["object"]).constructor(*args),
        )
        return w3.eth.contract(address=receipt.contractAddress, abi=a["abi"])

    if is_lfj:
        client = LFJClient(w3, usdc_address)
        block = w3.eth.get_block("latest")
        route = client.v1_route(block.number)
        client.token(usdc_address, 6, block.number)
        client.token(WAVAX, 18, block.number)
        quote = client.verified_quote(100_000, block.number, route)
        if quote["block_hash"] != Web3.to_hex(block.hash):
            raise RuntimeError("LFJ deployment preflight block changed")
        erc20 = artifact("IERC20Metadata")["abi"]
        usdc = w3.eth.contract(address=usdc_address, abi=erc20)
        wavax = w3.eth.contract(address=WAVAX, abi=erc20)
        vault = create("PolicyVault", [owner.address, attestor, usdc_address, WAVAX])
        router = create("LFJSwapAdapter", [vault.address, ROUTER, route["pair"], usdc_address, WAVAX])
    else:
        usdc = create("MockUSDC", [owner.address])
        wavax = create("MockWAVAX", [owner.address])
        router = create("MockSwapAdapter", [owner.address, usdc.address, wavax.address])
        vault = create("PolicyVault", [owner.address, attestor, usdc.address, wavax.address])
    owner_send( vault.functions.setRouter(router.address, True))
    if v2_config and v2_config.approval_ttl_seconds != 30:
        owner_send( vault.functions.setApprovalTtl(v2_config.approval_ttl_seconds))
    if v2_config:
        owner_send(
            vault.functions.configureProofPolicy(router.address, v2_config.proof_policy.abi_tuple),
        )
    owner_send(
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
    if not is_lfj:
        owner_send( usdc.functions.mint(vault.address, 7700 * 10**6))
        owner_send( wavax.functions.mint(vault.address, 115 * 10**18))
        owner_send( wavax.functions.mint(router.address, 100000 * 10**18))
    proof_deployment = {}
    if v2_config:
        from eth_abi import encode

        from treasury_contracts.v2 import keccak as abi_keccak

        now = w3.eth.get_block("latest").timestamp
        session_id = abi_keccak(
            encode(
                ["uint256", "address", "bytes32", "address"],
                [
                    w3.eth.chain_id,
                    vault.address,
                    vault.functions.activePolicyHash().call(),
                    owner.address,
                ],
            )
        )
        receipt = owner_send(
            vault.functions.createSession(
                session_id,
                now,
                min(
                    now + v2_config.session_duration_seconds,
                    vault.functions.policyExpiresAt().call(),
                ),
                int(v2_config.session_limit_usd_e8),
            ),
        )
        if not is_lfj:
            owner_send( usdc.functions.mint(router.address, 100000 * 10**6))
        proof_deployment = {
            "pdr_version": "2",
            "session_id": session_id,
            "session_creation_tx": Web3.to_hex(receipt.transactionHash),
            "session_creation_block": receipt.blockNumber,
        }
    deployment = {
        **proof_deployment,
        **({"adapter_version": ADAPTER_VERSION, "lfj_route": route} if is_lfj else {}),
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
        "owner_transactions": deployment_receipts,
        "bytecode_hashes": {
            name: keccak(w3.eth.get_code(obj.address))
            for name, obj in [
                ("PolicyVault", vault),
                ("LFJSwapAdapter" if is_lfj else "MockSwapAdapter", router),
                ("USDC" if is_lfj else "MockUSDC", usdc),
                ("WAVAX" if is_lfj else "MockWAVAX", wavax),
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
        ],
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--v2-config",
        type=Path,
        help="Explicit owner risk/session JSON; TEST_ONLY allowed only locally",
    )
    parser.add_argument("--network", choices=["local", "fuji"])
    parser.add_argument("--adapter", choices=["mock", "lfj"], default="mock")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--lfj-token", choices=["circle", "faucet"], default="faucet")
    args = parser.parse_args()
    if args.command == "schemas":
        from treasury_backend.modules.execution import models as models

        for name in [
            "TransactionProposal",
            "BuiltTransaction",
            "SimulationEvidence",
            "SignedPDR",
            "ExecutionResult",
            "ExecutionReconciliation",
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
        from treasury_backend.api.execution import create_app

        save(ROOT / "packages/contracts-api/openapi.json", create_app().openapi())
        save(
            ROOT / "packages/contracts-api/treasury_contracts/abi/PolicyVault.json",
            artifact("PolicyVault")["abi"],
        )
    elif args.command == "golden":
        from treasury_backend.operations.vectors import generate

        generate()
    elif args.command == "fixtures":
        from treasury_backend.operations.samples import generate

        generate()
    elif args.command == "migrate-env":
        from treasury_backend.operations.configuration import migrate_env

        print(json.dumps(migrate_env(), indent=2))
    else:
        settings_type = (
            DeploymentSettings if args.command in {"deploy-fuji", "config"} else Settings
        )
        env_file = (args.env_file or ROOT / ".env").resolve()
        required_mode = (
            "fuji"
            if args.command == "deploy-fuji"
            else "local"
            if args.command in {"deploy-local", "demo", "start-local"}
            else None
        )
        if required_mode and args.network and args.network != required_mode:
            parser.error(f"{args.command} requires --network {required_mode}")
        overrides = {"mode": required_mode or args.network} if required_mode or args.network else {}
        settings = settings_type(_env_file=env_file, **overrides)
        if args.command == "demo":
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
                    deploy(
                        settings,
                        args.command == "deploy-fuji",
                        adapter=args.adapter,
                        lfj_token=args.lfj_token,
                        env_file=env_file,
                        v2_config=json.loads(args.v2_config.read_text(encoding="utf-8"))
                        if args.v2_config
                        else None,
                    ),
                    indent=2,
                )
            )


def serve(settings, host="127.0.0.1", port=8001):
    import uvicorn

    from treasury_backend.api.execution import create_app

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
        [foundry_binary("forge", ROOT), "build"],
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
