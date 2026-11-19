"""Opt-in live-state test. All writes go to loopback Anvil; no Fuji broadcast.

Treasury contracts are created ONLY on the fork. LFJ faucet owner is impersonated
ONLY there to mint treasury test funds; LFJ pools/reserves are never edited.
The test's signature exercises the contracts, and is NOT an A/SDE approval.
"""

import json
import os
import time
from pathlib import Path

import pytest
from eth_abi import encode
from eth_account import Account
from web3 import Web3

from app.chain import Chain, artifact, plain
from app.cli import send
from app.crypto import approval_for, approval_tuple, content_hash, domain_for, keccak, message
from app.dex.lfj import ADAPTER_VERSION, LFJClient, ROUTER, USDC, WAVAX, call
from app.evidence.extractor import token_facts
from app.models import BuiltTransaction, TransactionProposal
from app.settings import Settings
from app.simulation.runner import Simulator, fork_node, rpc
from app.store import Store
from app.transaction.builder import Builder

pytestmark = [
    pytest.mark.integration,
    pytest.mark.fuji_fork,
    pytest.mark.skipif(
        os.getenv("PACEVANT_LFJ_FORK") != "1",
        reason="Explicit opt-in for public Fuji reads required",
    ),
]


@pytest.mark.parametrize(
    "treasury_tokens,expected_stress,expected_verification",
    [
        (100, ["SUCCESS_SAFE", "INCONCLUSIVE"], "INCONCLUSIVE"),
        (1000, ["SUCCESS_SAFE", "PROTECTED_REVERT"], "COMPLETE"),
    ],
)
def test_real_lfj_on_isolated_fuji_fork(
    tmp_path, treasury_tokens, expected_stress, expected_verification
):
    source = Settings(
        _env_file=None, mode="fuji", rpc_url="https://api.avax-test.network/ext/bc/C/rpc"
    )
    public = Web3(Web3.HTTPProvider(source.rpc_url, request_kwargs={"timeout": 20}))
    preflight = LFJClient(public).preflight((100_000,))
    assert preflight["status"] == "QUOTE_VERIFIED_EXECUTION_NOT_YET_SIMULATED"
    route = preflight["selected_route"]
    with fork_node(source, preflight["block_number"], 43113) as w3:
        assert w3.client_version.lower().startswith("anvil")
        assert w3.provider.endpoint_uri.startswith("http://127.0.0.1:")
        owner, attestor, relayer = Account.create(), Account.create(), Account.create()
        for account in (owner, relayer):
            rpc(w3, "anvil_setBalance", [account.address, hex(100 * 10**18)])

        def create(name, args):
            item = artifact(name)
            receipt = send(
                w3,
                owner,
                w3.eth.contract(abi=item["abi"], bytecode=item["bytecode"]["object"]).constructor(
                    *args
                ),
            )
            return w3.eth.contract(address=receipt.contractAddress, abi=item["abi"])

        vault = create("PolicyVault", [owner.address, attestor.address, USDC, WAVAX])
        adapter = create("LFJSwapAdapter", [vault.address, ROUTER, route["pair"], USDC, WAVAX])
        send(w3, owner, vault.functions.setRouter(adapter.address, True))
        send(
            w3,
            owner,
            vault.functions.configurePolicy(
                content_hash({"fork_only_test": True}),
                500 * 10**6,
                1000 * 10**6,
                100,
                int(time.time()) + 86400,
            ),
        )
        (faucet_owner,) = call(w3, USDC, "owner()", returns=("address",))
        faucet_owner = Web3.to_checksum_address(faucet_owner)
        rpc(w3, "anvil_setBalance", [faucet_owner, hex(10**18)])
        rpc(w3, "anvil_impersonateAccount", [faucet_owner])
        mint_data = Web3.keccak(text="mint(address,uint256)")[:4] + encode(
            ["address", "uint256"], [vault.address, treasury_tokens * 10**6]
        )
        mint_hash = rpc(
            w3,
            "eth_sendTransaction",
            [
                {
                    "from": faucet_owner,
                    "to": USDC,
                    "data": Web3.to_hex(mint_data),
                    "gas": hex(150000),
                }
            ],
        )
        assert w3.eth.wait_for_transaction_receipt(mint_hash).status == 1
        rpc(w3, "anvil_stopImpersonatingAccount", [faucet_owner])
        manifest = {
            "schema_version": "1.1",
            "adapter_version": ADAPTER_VERSION,
            "mode": "fuji",
            "chain_id": 43113,
            "vault_address": vault.address,
            "router": adapter.address,
            "token_in": USDC,
            "token_out": WAVAX,
            "owner": owner.address,
            "attestor": attestor.address,
            "relayer": relayer.address,
            "policy_hash": Web3.to_hex(vault.functions.activePolicyHash().call()),
            "lfj_route": route,
            "bytecode_hashes": {
                name: keccak(w3.eth.get_code(address))
                for name, address in [
                    ("PolicyVault", vault.address),
                    ("LFJSwapAdapter", adapter.address),
                    ("USDC", USDC),
                    ("WAVAX", WAVAX),
                ]
            },
        }
        manifest_file = tmp_path / "deployment.json"
        manifest_file.write_text(json.dumps(manifest))
        settings = Settings(
            _env_file=None,
            mode="fuji",
            rpc_url=w3.provider.endpoint_uri,
            deployment_file=manifest_file,
            data_dir=tmp_path / "execution",
            fuji_broadcast_authorized=False,
        )
        chain = Chain(settings)
        store = Store(settings.data_dir)
        # A fork does not mine while setup performs reads. Start this isolated
        # workflow at current time, as the existing Anvil fixtures do; keep the
        # production 30-second TTL and freshness guards unchanged.
        from conftest import mine_current_block

        mine_current_block(chain)
        c = chain.context()
        proposal = TransactionProposal(
            intent_id="intent_lfj_fork_test",
            mandate_id="mandate_fork_only",
            mandate_version=1,
            action="SWAP_EXACT_INPUT",
            chain_id=43113,
            vault_address=vault.address,
            router=adapter.address,
            token_in=USDC,
            token_out=WAVAX,
            amount_in_base_units="100000",
            slippage_bps=40,
            recipient=vault.address,
            deadline=c["timestamp"] + 29,
            user_goal_reason="Fork-only contract integration test; not an SDE authorization",
        )
        built = BuiltTransaction.model_validate(Builder(chain, store).build(proposal))
        quoted = int(
            store.get("build-context", built.build_id)["dex_quote"]["amount_out_base_units"]
        )
        # Execute on the FIRST fork before simulation. A second fork later replays this pinned pre-state.
        approval = approval_for(built, content_hash({"fork_contract_test_not_sde": True}))
        signature = Account.sign_message(
            message(domain_for(built), approval), attestor.key
        ).signature
        before = chain.balances()
        receipt = send(
            w3,
            relayer,
            vault.functions.executeApprovedSwap(
                approval_tuple(approval), built.router_calldata, signature
            ),
        )
        after = chain.balances()
        from treasury_contracts.models import SignedPDR
        from treasury_contracts.crypto import digest
        from treasury_contracts.outcomes import verify_outcome
        from treasury_contracts.readonly import readonly_web3

        fork_pdr = SignedPDR(decision_id="LFJ_FORK_PROTOCOL_TEST_NOT_SDE", build_id=built.build_id,
                             domain=domain_for(built), approval=approval, signature=Web3.to_hex(signature),
                             typed_data_hash=digest(domain_for(built), approval))
        reader = readonly_web3(w3.provider.endpoint_uri, 43113)
        try:
            reconciliation = verify_outcome(reader, built, fork_pdr, Web3.to_hex(receipt.transactionHash),
                                            expected_relayer=relayer.address, expected_attestor=attestor.address,
                                            evidence_root=approval.evidenceRoot)
        finally:
            reader.provider.close()
        assert reconciliation.verification_status == "VERIFIED", reconciliation
        facts = token_facts(
            receipt,
            vault.address,
            adapter.address,
            USDC,
            WAVAX,
            100000,
            int(built.min_amount_out_base_units),
            route,
        )
        assert (
            receipt.status == 1
            and not facts["unexpected_transfer"]
            and not facts["unauthorized_approval"]
        )
        assert int(before["usdc_base_units"]) - int(after["usdc_base_units"]) == 100000
        assert int(after["wavax_base_units"]) - int(before["wavax_base_units"]) == quoted
        assert vault.functions.usedNonce(int(built.nonce)).call()
        assert (
            call(
                w3,
                USDC,
                "allowance(address,address)",
                ("address", "address"),
                (adapter.address, ROUTER),
            )[0]
            == 0
        )
        # This is the production simulator using actual LFJ code, not a quote-only test.
        evidence = Simulator(chain, store).simulate(built.build_id, built.policy_hash)
        assert evidence["baseline"]["execution_status"] == "SUCCESS"
        assert (
            evidence["baseline"]["token_out_delta_base_units"]
            == facts["token_out_delta_base_units"]
        )
        assert not evidence["baseline"]["unexpected_transfer"]
        assert [x["status"] for x in evidence["stress_tests"]] == expected_stress
        assert evidence["verification_status"] == expected_verification
        # A replay remains blocked on the outer fork, with original signature and calldata.
        with pytest.raises(Exception):
            vault.functions.executeApprovedSwap(
                approval_tuple(approval), built.router_calldata, signature
            ).call({"from": relayer.address})
        report = {
            "scope": "ISOLATED_FUJI_FORK_NOT_PUBLIC_DEPLOYMENT_OR_SDE_APPROVAL",
            "public_fuji_broadcast": False,
            "preflight": preflight,
            "bootstrap": {
                "scope": "FORK_ONLY",
                "treasury_usdc_base_units": str(treasury_tokens * 10**6),
                "funding": "Impersonated LFJ faucet owner to mint only on fork; pool/token storage not patched",
                "ephemeral_roles": [owner.address, attestor.address, relayer.address],
            },
            "fork_deployment": manifest,
            "fork_receipt": plain(receipt),
            "readonly_reconciliation": reconciliation.model_dump(),
            "facts": facts,
            "before": before,
            "after": after,
            "quote_matches_fork_receipt": True,
            "simulation": evidence,
            "nonce_consumed": True,
            "artifact_bundle": {
                file.stem: json.loads(file.read_text())
                for file in (store.root / "artifacts").glob("*.json")
            },
            "live_blockers": [
                "USER_AUTHORIZATION_REQUIRED",
                "LFJ_TOKEN_FUNDING_REQUIRED",
                "ORACLE_TOKEN_IDENTITY_MISMATCH",
            ],
        }
        output = Path(os.environ.get("PACEVANT_LFJ_REPORT", str(tmp_path / "lfj-fork-report.json")))
        if treasury_tokens == 100:
            output = output.with_name(output.stem + "-insufficient-stress-budget.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print("LFJ fork report:", output)
