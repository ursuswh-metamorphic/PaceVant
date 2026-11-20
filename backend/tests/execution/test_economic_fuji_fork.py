"""Opt-in economic audit: real Fuji LFJ/Circle/feeds, ONLY disposable Anvil writes.

No project .env is loaded. Fixture vault/keys and stress funding are local-only.
This checks the execution/proof pipeline, not the AI or web authentication flow.
"""

import json
import os
import subprocess
import time
from fractions import Fraction
from urllib.parse import urlsplit

import pytest
from eth_abi import encode
from eth_account import Account
from web3 import Web3

from treasury_backend.config.execution import Settings
from treasury_backend.modules.execution.chain import Chain
from treasury_backend.modules.execution.dex.lfj import CIRCLE_USDC, ROUTER, WAVAX, LFJClient, call
from treasury_backend.modules.execution.models import BuiltTransaction, SimulationEvidence, TransactionProposal
from treasury_backend.modules.execution.simulation.runner import Simulator, fork_node, rpc
from treasury_backend.modules.execution.storage import Store
from treasury_backend.modules.execution.transaction.builder import Builder
from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
from treasury_backend.operations.env import PUBLIC_RPC
from treasury_backend.operations.fuji_demo import bootstrap
from treasury_backend.operations.profiles import Profile
from treasury_backend.paths import ROOT
from treasury_contracts.oracle import CHAINLINK_SOURCE
from treasury_contracts.proof import PGSProofEngine, owner_price_interval
from treasury_contracts.token_facts import token_facts
from treasury_contracts.v2 import (
    DomainV2, OracleEvidence, PreflightV2Request, Price, ProofPolicy, Registry,
    SessionContext, approval_v2, message_v2,
)

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("PACEVANT_ECONOMIC_FORK") != "1",
    reason="Opt-in public read-only Fuji source; transactions restricted to Anvil",
)]


def test_real_lfj_post_signing_drift_and_bounded_sandwich(tmp_path, record_property, monkeypatch):
    measurements, scenarios = {}, []

    def measure(name, operation):
        started = time.perf_counter()
        try:
            return operation()
        finally:
            measurements[name] = round(time.perf_counter() - started, 6)

    source = Settings(_env_file=None, mode="fuji", rpc_url=PUBLIC_RPC)
    public = Web3(Web3.HTTPProvider(PUBLIC_RPC, request_kwargs={"timeout": 30}))
    header = public.eth.get_block("latest")
    with fork_node(source, header.number, 43113) as w3:
        assert urlsplit(w3.provider.endpoint_uri).hostname == "127.0.0.1"
        assert w3.client_version.lower().startswith("anvil")
        assert w3.eth.get_block(header.number).hash == header.hash
        rpc(w3, "anvil_setBlockTimestampInterval", [0])
        owner, attestor, relayer, attacker = [Account.create() for _ in range(4)]
        for actor in (owner, relayer, attacker):
            rpc(w3, "anvil_setBalance", [actor.address, hex(10**20)])
        values = {
            "B_FUJI_OWNER_PRIVATE_KEY": owner.key.hex(), "PACEVANT_ATTESTOR_KEY": attestor.key.hex(),
            "B_FUJI_RELAYER_PRIVATE_KEY": relayer.key.hex(), "FUJI_TEST_WALLETS_ONLY": "true",
            "TREASURY_ORACLE_MODE": "chainlink", "TREASURY_ORACLE_SOURCE_ID": CHAINLINK_SOURCE,
            "TREASURY_OWNER_POLICY_APPROVED": "true", "TREASURY_MAX_RELATIVE_LOSS_BPS": "300",
            "TREASURY_MAX_FIXED_LOSS_USD": "0", "TREASURY_ORACLE_BAND_BPS": "100",
            "TREASURY_POSTCONDITION_TOLERANCE_BPS": "40", "TREASURY_SESSION_RISK_LIMIT_USD": "10",
            "TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD": "20", "TREASURY_MAX_ORACLE_AGE_SECONDS": "300",
            "TREASURY_APPROVAL_TTL_SECONDS": "300", "B_API_KEY": "economic-audit-local-only",
        }
        profile = Profile(ROOT, "fuji", values, w3.provider.endpoint_uri,
                          tmp_path / "deployment.json", tmp_path / "execution", tmp_path / "control",
                          18000, 18001, 200, 1)
        run = subprocess.run

        def fixture_subprocess(*args, **kwargs):
            result = run(*args, **kwargs)
            if result.returncode:
                # Only this fixture's last exception line, with generated keys removed.
                last = result.stderr.strip().splitlines()[-1] if result.stderr else "fixture subprocess failed"
                for account in (owner, attestor, relayer, attacker):
                    last = last.replace(account.key.hex(), "[REDACTED]")
                raise AssertionError(last)
            return result

        with monkeypatch.context() as context_patch:
            context_patch.setattr(subprocess, "run", fixture_subprocess)
            measure("fork_fixture_bootstrap_seconds", lambda: bootstrap(profile))
        settings = Settings(_env_file=None, mode="fuji", rpc_url=profile.rpc,
                            deployment_file=profile.deployment, data_dir=profile.execution_data,
                            max_ttl=300, freshness_seconds=300, max_block_drift=200)
        chain, store = Chain(settings), Store(profile.execution_data)
        route = LFJClient(w3, CIRCLE_USDC).v1_route(w3.eth.block_number)
        reserve_in = int(route["reserves"][0 if route["token0"].lower() == CIRCLE_USDC.lower() else 1])
        # Bounded fixture victim; never change the live wallet, policy, price or pool.
        amount = max(1, min(100 * 10**6, reserve_in // 100))

        def transact(account, target, data):
            signed = account.sign_transaction({"to": target, "data": data,
                "chainId": 43113, "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 1_500_000, "gasPrice": w3.eth.gas_price})
            return w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

        def payload(signature, types, vals):
            return Web3.keccak(text=signature)[:4] + encode(types, vals)

        def mint_on_fork(target, value):
            master = Web3.to_checksum_address(call(w3, CIRCLE_USDC, "masterMinter()", returns=("address",))[0])
            rpc(w3, "anvil_setBalance", [master, hex(10**20)])
            rpc(w3, "anvil_impersonateAccount", [master])
            try:
                data = payload("configureMinter(address,uint256)", ("address", "uint256"),
                               (owner.address, value))
                tx = rpc(w3, "eth_sendTransaction", [{"from": master, "to": CIRCLE_USDC,
                    "data": Web3.to_hex(data), "gas": hex(500_000)}])
                assert w3.eth.wait_for_transaction_receipt(tx).status == 1
                receipt = transact(owner, CIRCLE_USDC, payload("mint(address,uint256)",
                    ("address", "uint256"), (target, value)))
                assert receipt.status == 1
            finally:
                rpc(w3, "anvil_stopImpersonatingAccount", [master])

        mint_on_fork(chain.vault.address, amount)
        mint_on_fork(attacker.address, max(1, reserve_in))
        assert transact(attacker, CIRCLE_USDC, payload("approve(address,uint256)",
            ("address", "uint256"), (ROUTER, 2**256 - 1))).status == 1
        assert transact(attacker, WAVAX, payload("approve(address,uint256)",
            ("address", "uint256"), (ROUTER, 2**256 - 1))).status == 1
        rpc(w3, "evm_setNextBlockTimestamp", [max(int(time.time()), w3.eth.get_block("latest").timestamp)])
        rpc(w3, "evm_mine", [])
        context = chain.context()
        built = measure("build_quote_reads_seconds", lambda: BuiltTransaction.model_validate(
            Builder(chain, store).build(TransactionProposal(
                intent_id="economic-audit", mandate_id="mandate_demo", mandate_version=1,
                action="SWAP_EXACT_INPUT", chain_id=43113, vault_address=chain.vault.address,
                router=chain.router.address, token_in=CIRCLE_USDC, token_out=WAVAX,
                amount_in_base_units=str(amount), slippage_bps=100, recipient=chain.vault.address,
                deadline=context["timestamp"] + 300, user_goal_reason="LOCAL_FORK_AUDIT_ONLY"))))
        simulator = Simulator(chain, store)
        sim = measure("baseline_and_stress_simulation_seconds", lambda: SimulationEvidence.model_validate(
            simulator.simulate(built.build_id, built.policy_hash)))
        assert sim.verification_status == "COMPLETE", sim
        context = store.get("build-context", built.build_id)["context"]
        prices = measure("oracle_pinned_reads_seconds", lambda:
            ChainlinkPriceProvider(profile.rpc, built.vault_address).read(context["block_number"]))
        policy, registry, session = (ProofPolicy.model_validate(context["proof_policy"]),
            Registry.model_validate(context["registry"]), SessionContext.model_validate(context["proof_session"]))
        nominal = {6: int(prices.price_usdc_usd_e8), 18: int(prices.price_wavax_usd_e8)}
        oracle = OracleEvidence(chain_id=43113, vault=built.vault_address,
            source_hash=policy.oracle_source_hash, timestamp=prices.oracle_observed_at,
            block_number=prices.oracle_block_number, block_hash=prices.oracle_block_hash,
            feeds=tuple(prices.oracle_feeds), prices=tuple(Price(asset=a.address,
                nominal_usd_e8=str(nominal[a.decimals]),
                low_usd_e8=str(owner_price_interval(nominal[a.decimals], policy.oracle_band_bps)[0]),
                high_usd_e8=str(owner_price_interval(nominal[a.decimals], policy.oracle_band_bps)[1]))
                for a in registry.assets))
        proof = measure("z3_total_seconds", lambda: PGSProofEngine().prove(
            built, sim.effects_v2, policy, registry, oracle, session, context["timestamp"]))
        assert proof.status == "VERIFIED", proof
        measure("final_guarded_preflight_seconds", lambda: simulator.preflight_v2(
            PreflightV2Request(build_id=built.build_id, proof=proof, session_id=session.session_id)))
        approval = approval_v2(built, sim.evidence_root, proof, session.session_id)
        signature = Account.sign_message(message_v2(DomainV2(chainId=43113,
            verifyingContract=built.vault_address), approval), attestor.key).signature
        encoded = chain.vault.encode_abi("executeApprovedSwapV2", args=[approval.abi_tuple,
            built.router_calldata, proof.phi.abi_tuple, signature])
        # Everything below mutates the market AFTER the proof and signature exist.
        initial = rpc(w3, "evm_snapshot", [])

        def reset():
            nonlocal initial
            assert rpc(w3, "evm_revert", [initial])
            initial = rpc(w3, "evm_snapshot", [])

        def state():
            return (chain.balances(), chain.vault.functions.usedNonce(int(built.nonce)).call(),
                chain.vault.functions.sessions(session.session_id).call(),
                chain.vault.functions.globalDailyRiskUsedUsdE8(context["timestamp"] // 86400).call(),
                chain.vault.functions.dailySpentUsdc(context["timestamp"] // 86400).call(),
                chain.usdc.functions.allowance(chain.router.address, ROUTER).call())

        def victim(label, expected):
            before = state()
            receipt = transact(relayer, chain.vault.address, encoded)
            after = state()
            assert receipt.status == expected, label
            if not expected:
                assert after == before, label
            else:
                output = int(after[0]["wavax_base_units"]) - int(before[0]["wavax_base_units"])
                lower = next(int(x.min_delta) for x in proof.phi.balance_bounds if x.asset == WAVAX.lower())
                assert output >= lower
                assert after[1] and after[5] == 0
            scenarios.append({"scenario": label, "status": "SAFE_SETTLEMENT" if expected else "ATOMIC_REVERT",
                              "gas_used": receipt.gasUsed})
            return receipt

        victim("normal", 1)
        reset()

        def market_swap(account, value, reverse=False):
            path = ([0], [0], [WAVAX, CIRCLE_USDC] if reverse else [CIRCLE_USDC, WAVAX])
            receipt = transact(account, ROUTER, payload(
                "swapExactTokensForTokens(uint256,uint256,(uint256[],uint8[],address[]),address,uint256)",
                ("uint256", "uint256", "(uint256[],uint8[],address[])", "address", "uint256"),
                (value, 1, path, account.address, built.deadline)))
            assert receipt.status == 1
            return receipt

        for label, fraction, expected in (("mild_front_run", 1000, 1), ("severe_front_run", 20, 0)):
            market_swap(attacker, max(1, reserve_in // fraction))
            victim(label, expected)
            reset()

        # Token withdrawal + sync is a counterfactual reserve reduction, NOT an LP burn.
        for label, divisor in (("liquidity_reduction", 100), ("zero_liquidity", None)):
            pair = Web3.to_checksum_address(route["pair"])
            rpc(w3, "anvil_setBalance", [pair, hex(10**20)])
            rpc(w3, "anvil_impersonateAccount", [pair])
            try:
                for token in (chain.usdc, chain.wavax):
                    balance = token.functions.balanceOf(pair).call()
                    removed = balance if divisor is None else balance - balance // divisor
                    tx = rpc(w3, "eth_sendTransaction", [{"from": pair, "to": token.address,
                        "data": token.encode_abi("transfer", args=[attacker.address, removed]), "gas": hex(500000)}])
                    assert w3.eth.wait_for_transaction_receipt(tx).status == 1
                assert transact(attacker, pair, payload("sync()", (), ())).status == 1
            finally:
                rpc(w3, "anvil_stopImpersonatingAccount", [pair])
            victim(label, 0)
            reset()

        # Bounded search, actual EVM front/victim/back runs, explicit realized P&L.
        pnl = []
        for divisor in (20000, 5000, 1000, 500, 100):
            front = max(1, reserve_in // divisor)
            cash_before = chain.usdc.functions.balanceOf(attacker.address).call()
            native_before = w3.eth.get_balance(attacker.address)
            f = market_swap(attacker, front)
            before = state()
            v = transact(relayer, chain.vault.address, encoded)
            if not v.status:
                assert state() == before
            else:
                output = int(chain.balances()["wavax_base_units"]) - int(before[0]["wavax_base_units"])
                assert output >= next(int(x.min_delta) for x in proof.phi.balance_bounds if x.asset == WAVAX.lower())
            acquired = chain.wavax.functions.balanceOf(attacker.address).call()
            back = market_swap(attacker, acquired, reverse=True)
            gross = chain.usdc.functions.balanceOf(attacker.address).call() - cash_before
            gas = native_before - w3.eth.get_balance(attacker.address)
            net_e8 = Fraction(gross * nominal[6], 10**6) - Fraction(gas * nominal[18], 10**18)
            pnl.append({"front_usdc_base_units": front, "victim_settled": bool(v.status),
                        "gross_profit_usdc_base_units": gross, "attacker_gas_wei": gas,
                        "net_reference_profit_usd_e8": str(net_e8),
                        "front_gas_used": f.gasUsed, "back_gas_used": back.gasUsed})
            reset()

        # Measure actual receipt parsing separately from the integrated simulator.
        receipt = victim("extraction_measurement", 1)
        facts = measure("receipt_effect_extraction_seconds", lambda: token_facts(receipt,
            built.vault_address, built.router, built.token_in, built.token_out, amount,
            int(built.min_amount_out_base_units), dex_route=route))
        assert not facts["unexpected_transfer"] and not facts["unauthorized_approval"]
        report = {"source_writes": False, "source_chain_id": 43113,
            "source_block": header.number, "source_block_hash": Web3.to_hex(header.hash),
            "fixture": "ephemeral local vault/keys; real LFJ/Circle/Chainlink bytecode on Fuji fork",
            "victim_usdc_base_units": amount, "pool": route["pair"],
            "proof_status": proof.status, "risk_debit_usd_e8": proof.risk_debit_usd_e8,
            "policy_hash": policy.hash, "proof_context_hash": proof.context_hash,
            "measurements": measurements, "scenarios": scenarios, "sandwich_grid": pnl,
            "limitations": "five fixed front sizes; no optimal search, flash loans, builder auctions or public ordering guarantee"}
        record_property("economic_fork_report", json.dumps(report))
        if os.getenv("PACEVANT_ECONOMIC_REPORT"):
            # Explicit caller-selected evidence destination; contains NO signing keys.
            from pathlib import Path
            Path(os.environ["PACEVANT_ECONOMIC_REPORT"]).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
