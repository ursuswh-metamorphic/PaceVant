import json
import socket
import subprocess
import time
import pytest
from eth_account import Account
from fastapi.testclient import TestClient
from web3 import Web3
from treasury_backend.api.execution import create_app
from treasury_backend.modules.execution.chain import Chain
from treasury_backend.operations.execution import deploy
from treasury_backend.modules.execution.crypto import approval_for, digest, domain_for, message
from treasury_backend.modules.execution.models import BuiltTransaction, SignedPDR
from treasury_backend.config.execution import Settings
from treasury_backend.modules.execution.simulation.runner import rpc


def mine_current_block(chain):
    # Anvil restores the mining timestamp when evm_revert rolls back a test snapshot.
    timestamp = int(time.time())
    if timestamp > chain.w3.eth.get_block("latest").timestamp:
        rpc(chain.w3, "evm_setNextBlockTimestamp", [timestamp])
        rpc(chain.w3, "evm_mine", [])


@pytest.fixture(scope="session")
def local_network(tmp_path_factory):
    root = tmp_path_factory.mktemp("anvil")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    settings = Settings(
        _env_file=None,
        rpc_url=f"http://127.0.0.1:{port}",
        deployment_file=root / "deployment.json",
        data_dir=root / "bootstrap",
        api_key="test-backend-key",
    )
    proc = subprocess.Popen(
        [
            settings.anvil_binary,
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
            "--silent",
            "--chain-id",
            "31337",
            "--hardfork",
            "cancun",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail("Anvil exited")
            if w3.is_connected():
                break
            time.sleep(0.1)
        else:
            pytest.fail("Anvil startup timeout")
        deploy(settings, write_env=False)

        class LocalKeys(dict):
            def __repr__(self):
                return "<ephemeral local test keys>"

        keys = LocalKeys(
            json.loads((settings.data_dir / "local-keys.json").read_text())
        )
        yield settings, keys
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.fixture
def plane(local_network, tmp_path):
    base, keys = local_network
    settings = Settings(
        **{
            **base.model_dump(),
            "data_dir": tmp_path / "data",
            "relayer_private_key": keys["relayer"],
        }
    )
    chain = Chain(settings)
    snap = rpc(chain.w3, "evm_snapshot", [])
    mine_current_block(chain)
    app = create_app(settings, chain)
    with TestClient(app, raise_server_exceptions=False) as client:
        client.headers["X-API-Key"] = settings.api_key.get_secret_value()
        yield client, chain, keys, app
    assert rpc(chain.w3, "evm_revert", [snap])


def proposal(chain, **changes):
    c = chain.context()
    return {
        "intent_id": "intent_test",
        "mandate_id": "mandate_demo",
        "mandate_version": 1,
        "action": "SWAP_EXACT_INPUT",
        "chain_id": c["chain_id"],
        "vault_address": c["vault_address"],
        "router": c["router"],
        "token_in": c["token_in"],
        "token_out": c["token_out"],
        "amount_in_base_units": "200000000",
        "slippage_bps": 40,
        "recipient": c["vault_address"],
        "deadline": min(int(time.time()), c["timestamp"]) + 29,
        "user_goal_reason": "Local integration test",
        **changes,
    }


def post(client, route, body, key="test"):
    return client.post(route, json=body, headers={"Idempotency-Key": key})


def build_and_simulate(client, chain):
    response = post(client, "/v1/build", proposal(chain))
    assert response.status_code == 200, response.text
    built = response.json()
    response = post(
        client,
        "/v1/simulations",
        {"build_id": built["build_id"], "expected_policy_hash": built["policy_hash"]},
    )
    assert response.status_code == 200, response.text
    return built, response.json()


def sign_pdr(built, evidence, keys):
    b = BuiltTransaction.model_validate(built)
    a, d = approval_for(b, evidence["evidence_root"]), domain_for(b)
    signature = Account.sign_message(message(d, a), keys["attestor"]).signature
    return SignedPDR(
        decision_id="local_test_decision",
        build_id=b.build_id,
        domain=d,
        approval=a,
        signature=Web3.to_hex(signature),
        typed_data_hash=digest(d, a),
    ).model_dump()


@pytest.fixture
def v3(local_network, tmp_path):
    """Disposable V3 deployment; generated keys stay in process memory."""
    from types import SimpleNamespace
    from treasury_backend.modules.execution.v3 import V3Execution
    from treasury_backend.operations.v3_local import deploy_local
    from treasury_contracts.rpc import evm_web3

    base, _ = local_network
    w3 = evm_web3(Web3.HTTPProvider(base.rpc_url))
    snap = rpc(w3, "evm_snapshot", [])
    mine_current_block(SimpleNamespace(w3=w3))
    data = deploy_local(w3, base.model_copy(update={"data_dir": tmp_path / "execution"}), tmp_path)
    data["execution"] = V3Execution(data["settings"], data["manifest"])
    yield data
    assert rpc(w3, "evm_revert", [snap])


@pytest.fixture
def mvp(local_network,tmp_path):
    from types import SimpleNamespace
    from treasury_backend.modules.execution.mvp import MvpExecution
    from treasury_backend.operations.mvp_local import deploy_mvp_local
    from treasury_contracts.rpc import evm_web3
    base,_=local_network
    w3=evm_web3(Web3.HTTPProvider(base.rpc_url));snap=rpc(w3,"evm_snapshot",[])
    mine_current_block(SimpleNamespace(w3=w3))
    data=deploy_mvp_local(w3,base.model_copy(update={"data_dir":tmp_path/"execution"}),tmp_path)
    data["execution"]=MvpExecution(data["settings"],data["manifest"])
    yield data
    assert rpc(w3,"evm_revert",[snap])
