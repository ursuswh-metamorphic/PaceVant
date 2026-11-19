"""Opt-in real Circle/LFJ/Chainlink pipeline, disposable wallets, NO public writes."""


import os

import pytest
from eth_account import Account
from fastapi.testclient import TestClient
from web3 import Web3

from treasury_backend.api.app import create_app
from treasury_backend.config.control import Settings as ControlSettings
from treasury_backend.config.execution import Settings as ExecutionSettings
from treasury_backend.modules.execution.simulation.runner import fork_node, rpc
from treasury_backend.modules.persistence import Store
from treasury_backend.operations.env import PUBLIC_RPC
from treasury_backend.operations.fuji_demo import bootstrap, select_goal
from treasury_backend.operations.profiles import Profile
from treasury_backend.paths import ROOT
from treasury_contracts.oracle import CHAINLINK_SOURCE

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("PACEVANT_LFJ_FORK") != "1", reason="Opt-in public Fuji reads; all writes on Anvil",
)]


def test_circle_chainlink_pipeline_confirms_on_isolated_fuji_fork(tmp_path):
    source = ExecutionSettings(_env_file=None, mode="fuji", rpc_url=PUBLIC_RPC)
    public = Web3(Web3.HTTPProvider(PUBLIC_RPC))
    with fork_node(source, public.eth.block_number, 43113) as w3:
        rpc(w3, "anvil_setBlockTimestampInterval", [0])
        owner, attestor, relayer = Account.create(), Account.create(), Account.create()
        rpc(w3, "anvil_setBalance", [owner.address, hex(10**18)])
        values = {
            "B_FUJI_OWNER_PRIVATE_KEY": owner.key.hex(), "PACEVANT_ATTESTOR_KEY": attestor.key.hex(),
            "B_FUJI_RELAYER_PRIVATE_KEY": relayer.key.hex(), "FUJI_TEST_WALLETS_ONLY": "true",
            "TREASURY_ORACLE_MODE": "chainlink", "TREASURY_ORACLE_SOURCE_ID": CHAINLINK_SOURCE,
            "TREASURY_OWNER_POLICY_APPROVED": "true", "TREASURY_MAX_RELATIVE_LOSS_BPS": "300",
            "TREASURY_MAX_FIXED_LOSS_USD": "0", "TREASURY_ORACLE_BAND_BPS": "100",
            "TREASURY_POSTCONDITION_TOLERANCE_BPS": "40", "TREASURY_SESSION_RISK_LIMIT_USD": "10",
            "TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD": "20", "TREASURY_MAX_ORACLE_AGE_SECONDS": "180",
            "TREASURY_APPROVAL_TTL_SECONDS": "180", "B_API_KEY": "test-execution-" + "c" * 30,
        }
        p = Profile(ROOT, "fuji", values, w3.provider.endpoint_uri, tmp_path / "deployment.json",
                    tmp_path / "execution", tmp_path / "control", 18000, 18001, 120, 1)
        bootstrap(p)
        control = ControlSettings(mode="FUJI", db=p.control_data / "control.sqlite3",
            mandate_file=p.control_data / "mandate.json", oracle_file=p.control_data / "oracle.json",
            chain_rpc_url=p.rpc, relayer_address=relayer.address.lower(), attestor_key=attestor.key.hex(),
            operator_token="test-operator-" + "a" * 30, internal_token="test-internal-" + "b" * 30,
            max_block_drift=120, fuji_verification_rpc=p.rpc)
        execution = ExecutionSettings(_env_file=None, mode="fuji", rpc_url=p.rpc,
            deployment_file=p.deployment, data_dir=p.execution_data, api_key=values["B_API_KEY"],
            relayer_private_key=relayer.key.hex(), max_ttl=180, freshness_seconds=180,
            max_block_drift=120, required_confirmations=1)
        with TestClient(create_app(control, execution)) as client:
            result = client.post("/v1/workflows/start", headers={"Authorization": "Bearer " + control.operator_token},
                json={"mandate_id": "mandate_demo", "goal": select_goal(p)}).raise_for_status().json()
        assert result["status"] == "CONFIRMED", result
        bundle = Store(control.db).attempts(result["workflow_id"])[-1]
        assert bundle["risk"]["result"] == "PASS"
        assert [bundle["proof"][k] for k in ("check_mode", "compile_mode", "risk_bound")] == ["UNSAT"] * 3
        assert bundle["portfolio"]["price_source"] == CHAINLINK_SOURCE
        assert len(bundle["portfolio"]["oracle_feeds"]) == 2
        assert bundle["simulation"]["effects_v2"]["adapter_version"] == "lfj-v1-fuji-v1"
        assert [s["status"] for s in bundle["simulation"]["stress_tests"]] == ["SUCCESS_SAFE", "PROTECTED_REVERT"]
