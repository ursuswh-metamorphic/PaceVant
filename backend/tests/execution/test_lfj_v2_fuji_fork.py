"""Optional public Fuji reads and V2 deployment/swaps on an ephemeral Anvil fork."""

import json
import os
import time

import pytest
from eth_abi import encode
from eth_account import Account
from web3 import Web3

from treasury_backend.config.execution import DeploymentSettings
from treasury_backend.modules.execution.chain import Chain
from treasury_backend.modules.execution.dex.lfj import LFJClient, USDC, call
from treasury_backend.modules.execution.models import BuiltTransaction, TransactionProposal
from treasury_backend.modules.execution.simulation.runner import Simulator, fork_node, rpc
from treasury_backend.modules.execution.storage import Store
from treasury_backend.modules.execution.transaction.builder import Builder
from treasury_backend.operations.env import PUBLIC_RPC
from treasury_backend.operations.execution import deploy
from treasury_backend.paths import ROOT
from treasury_contracts.proof import PGSProofEngine
from treasury_contracts.v2 import (
    EffectEvidenceV2,
    OracleEvidence,
    PreflightV2Request,
    Price,
    ProofPolicy,
    Registry,
    SessionContext,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("PACEVANT_LFJ_FORK") != "1", reason="Opt-in public Fuji reads"),
]


def test_v2_simulator_executes_verified_lfj_route_on_fuji_fork(tmp_path):
    source = DeploymentSettings(_env_file=None, mode="fuji", rpc_url=PUBLIC_RPC, rpc_timeout=20)
    public = Web3(Web3.HTTPProvider(source.rpc_url, request_kwargs={"timeout": 20}))
    preflight = LFJClient(public).preflight((100_000,))
    assert preflight["status"] == "QUOTE_VERIFIED_EXECUTION_NOT_YET_SIMULATED"

    with fork_node(source, preflight["block_number"], 43113) as w3:
        assert w3.client_version.lower().startswith("anvil")
        assert w3.provider.endpoint_uri.startswith("http://127.0.0.1:")
        owner, attestor, relayer = Account.create(), Account.create(), Account.create()
        for account in (owner, relayer):
            rpc(w3, "anvil_setBalance", [account.address, hex(10**20)])
        settings = DeploymentSettings(
            _env_file=None,
            mode="fuji",
            rpc_url=w3.provider.endpoint_uri,
            deployment_file=tmp_path / "deployment.json",
            data_dir=tmp_path / "execution",
            owner_private_key=owner.key.hex(),
            attestor_address=attestor.address,
            relayer_private_key=relayer.key.hex(),
            rpc_timeout=20,
        )
        config = json.loads((ROOT / "fixtures/v2_1/TEST_ONLY_policy.json").read_text())
        # Deployment validation is exercised on loopback with disposable owner authorization.
        config["proof_policy"]["authorization"] = "OWNER_APPROVED"
        manifest = deploy(settings, fuji=True, write_env=False, v2_config=config, adapter="lfj")
        assert manifest["pdr_version"] == "2"
        assert manifest["lfj_route"]["pair"] == preflight["selected_route"]["pair"]

        faucet_owner = Web3.to_checksum_address(call(w3, USDC, "owner()", returns=("address",))[0])
        rpc(w3, "anvil_setBalance", [faucet_owner, hex(10**18)])
        rpc(w3, "anvil_impersonateAccount", [faucet_owner])
        mint = Web3.keccak(text="mint(address,uint256)")[:4] + encode(
            ["address", "uint256"], [manifest["vault_address"], 1000 * 10**6]
        )
        minted = rpc(
            w3,
            "eth_sendTransaction",
            [{"from": faucet_owner, "to": USDC, "data": Web3.to_hex(mint), "gas": hex(150000)}],
        )
        assert w3.eth.wait_for_transaction_receipt(minted).status == 1
        rpc(w3, "anvil_stopImpersonatingAccount", [faucet_owner])

        chain = Chain(settings)
        store = Store(settings.data_dir)
        now = max(int(time.time()), w3.eth.get_block("latest").timestamp + 1)
        rpc(w3, "evm_setNextBlockTimestamp", [now])
        rpc(w3, "evm_mine", [])
        context = chain.context()
        proposal = TransactionProposal(
            intent_id="intent_lfj_v2_fork_test",
            mandate_id="mandate_fork_only",
            mandate_version=1,
            action="SWAP_EXACT_INPUT",
            chain_id=43113,
            vault_address=manifest["vault_address"],
            router=manifest["router"],
            token_in=manifest["token_in"],
            token_out=manifest["token_out"],
            amount_in_base_units="100000",
            slippage_bps=40,
            recipient=manifest["vault_address"],
            deadline=context["timestamp"] + 29,
            user_goal_reason="Fork-only V2 integration test",
        )
        built = BuiltTransaction.model_validate(Builder(chain, store).build(proposal))
        saved = store.get("build-context", built.build_id)
        evidence = Simulator(chain, store).simulate(built.build_id, built.policy_hash)
        assert evidence["source"] == "FORK_SIM"
        assert evidence["baseline"]["execution_status"] == "SUCCESS"
        assert not evidence["baseline"]["unexpected_transfer"]
        assert not evidence["baseline"]["unauthorized_approval"]
        assert evidence["effects_v2"] is not None
        assert (
            evidence["baseline"]["token_out_delta_base_units"]
            == saved["lfj_quote"]["amount_out_base_units"]
        )
        assert evidence["stress_tests"][0]["status"] == "SUCCESS_SAFE"
        assert evidence["stress_tests"][1]["status"] == "PROTECTED_REVERT"
        assert evidence["verification_status"] == "COMPLETE"

        # An explicit mathematical fixture exercises final Phi on the fork only.
        # The runtime cannot use these assumed USD prices for LFJ authorization.
        effects = EffectEvidenceV2.model_validate(evidence["effects_v2"])
        registry = Registry.model_validate(context["registry"])
        session = SessionContext.model_validate(context["proof_session"])
        policy = ProofPolicy.model_validate(context["proof_policy"])
        assumed_prices = OracleEvidence(
            chain_id=43113,
            vault=built.vault_address,
            source_hash=policy.oracle_source_hash,
            timestamp=context["timestamp"],
            block_number=context["block_number"],
            block_hash=context["block_hash"],
            prices=tuple(
                Price(
                    asset=asset.address,
                    nominal_usd_e8=str(price),
                    low_usd_e8=str(price * 99 // 100),
                    high_usd_e8=str(price * 101 // 100),
                )
                for asset in registry.assets
                for price in [10**8 if asset.decimals == 6 else 20 * 10**8]
            ),
        )
        proof = PGSProofEngine().prove(
            built, effects, policy, registry, assumed_prices, session, context["timestamp"]
        )
        assert proof.status == "VERIFIED", proof.reason
        final = Simulator(chain, store).preflight_v2(
            PreflightV2Request(build_id=built.build_id, proof=proof, session_id=session.session_id)
        )
        report = json.loads(store.read_artifact(final["content_hash"][2:]))
        assert [entry["status"] for entry in report["scenarios"]] == [
            "SUCCESS_SAFE",
            "SUCCESS_SAFE",
            "PROTECTED_REVERT",
        ]
        assert not chain.vault.functions.usedNonce(int(built.nonce)).call()
