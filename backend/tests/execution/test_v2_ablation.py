"""Opt-in measured ablation. Test keys + private Anvil only; no runtime bypass flags.

FULL_V1 uses the existing complete V1 gates and compatibility entrypoint.
The B/C ablations use explicitly labelled local TEST_ONLY signatures to remove
proof/budget layers. Those modes are unavailable in the application signer.
"""

import json
import os
import platform
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

import pytest
from eth_account import Account
from web3 import Web3

from treasury_backend.operations.execution import send
from treasury_backend.modules.execution.crypto import approval_for, approval_tuple, domain_for, message
from treasury_backend.modules.execution.models import BuiltTransaction, SimulationEvidence, TransactionProposal
from treasury_backend.config.execution import ROOT
from treasury_backend.modules.execution.simulation.runner import rpc
from treasury_backend.modules.execution.storage import Store
from treasury_backend.modules.execution.transaction.builder import Builder
from treasury_backend.modules.execution.simulation.runner import Simulator
from conftest import proposal, mine_current_block
from v2_setup import activate
from treasury_contracts.proof import PGSProofEngine, loss_e8
from treasury_contracts.v2 import (
    Registry,
    ProofPolicy,
    SessionContext,
    OracleEvidence,
    Price,
    PostConditionsV2,
    BalanceBound,
    AllowanceCap,
    ApprovalV2,
    DomainV2,
    approval_v2,
    message_v2,
    keccak,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_V2_ABLATION") != "1", reason="opt-in quantitative local ablation"
)


def v1_gates(c, chain, b, p, sim, saved):
    mandate = json.loads((ROOT / "fixtures/mock/mandate.json").read_text())
    mandate.update(
        {
            k: c[k]
            for k in (
                "chain_id",
                "vault_address",
                "owner",
                "router",
                "token_in",
                "token_out",
                "policy_hash",
            )
        }
    )
    mandate.update(
        expires_at=c["policy_expires_at"],
        max_usdc_per_swap_base_units=c["max_per_swap_base_units"],
        max_usdc_spend_per_day_base_units=c["max_spend_per_day_base_units"],
        max_slippage_bps=c["max_slippage_bps"],
    )
    # Control plane normalizes addresses exactly as in its production SDK.
    lower = lambda a: a.lower()
    context = dict(
        deployment="LOCAL",
        chain_id=c["chain_id"],
        vault_address=lower(c["vault_address"]),
        owner=lower(c["owner"]),
        router=lower(c["router"]),
        token_in=lower(c["token_in"]),
        token_out=lower(c["token_out"]),
        token_in_decimals=6,
        token_out_decimals=18,
        policy_hash=c["policy_hash"],
        policy_version=c["policy_version"],
        policy_expires_at=c["policy_expires_at"],
        paused=False,
        attestor=lower(c["attestor"]),
        relayer=lower(chain.deployment["relayer"]),
        block_number=c["block_number"],
        block_timestamp=c["timestamp"],
        bytecode_hash=sim.bytecode_hash,
        nonce_used=False,
        max_usdc_per_swap_base_units=c["max_per_swap_base_units"],
        max_usdc_spend_per_day_base_units=c["max_spend_per_day_base_units"],
    )
    snapshot = dict(
        snapshot_id="TEST_ONLY_snapshot",
        chain_id=c["chain_id"],
        vault_address=lower(c["vault_address"]),
        block_number=c["block_number"],
        usdc_base_units=saved["usdc_base_units"],
        wavax_base_units=saved["wavax_base_units"],
        price_usdc_usd_e8="100000000",
        price_wavax_usd_e8="2000000000",
        price_source="TRUSTED_TEST_ORACLE",
        price_timestamp=c["timestamp"],
        history_version=0,
    )
    balances = {
        k: snapshot[k]
        for k in (
            "chain_id",
            "vault_address",
            "block_number",
            "usdc_base_units",
            "wavax_base_units",
        )
    }
    balances.update(
        policy_hash=c["policy_hash"],
        block_timestamp=c["timestamp"],
        utc_day=c["timestamp"] // 86400,
        daily_spent_usdc_base_units=saved["daily_spent_usdc_base_units"],
        daily_execution_cost_usd_e8="0",
        max_fee_per_gas_wei=str(chain.w3.eth.gas_price),
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(ROOT / "backend/src"), str(ROOT / "packages/contracts-api"))
        ),
    }
    proposal_data = p.model_dump()
    for field in ("vault_address", "router", "token_in", "token_out", "recipient"):
        proposal_data[field] = proposal_data[field].lower()
    payload = dict(
        mandate=mandate,
        proposal=proposal_data,
        goal="Buy WAVAX with 200 USDC",
        build=b.model_dump(),
        simulation=sim.model_dump(mode="json"),
        context=context,
        snapshot=snapshot,
        balances=balances,
        now=int(time.time()),
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/evaluation-v1-gates.py")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=ROOT,
        check=True,
    )
    gates = json.loads(result.stdout)
    assert (
        gates["alignment"]["verdict"] == "ALIGNED"
        and gates["risk"]["result"] == "PASS"
        and gates["decision"]["verdict"] == "APPROVE"
    ), gates
    return gates


def test_measured_matched_ablation(plane, tmp_path):
    _, chain, keys, _ = plane
    owner, relayer = Account.from_key(keys["owner"]), Account.from_key(keys["relayer"])
    send(chain.w3, owner, chain.usdc.functions.mint(chain.vault.address, 10000 * 10**6))
    initial = rpc(chain.w3, "evm_snapshot", [])
    records = []
    for mode in ("FULL_V1", "V1_PLUS_PHI", "PGS_CORE", "V2_1_CORE"):
        assert rpc(chain.w3, "evm_revert", [initial])
        initial = rpc(chain.w3, "evm_snapshot", [])
        # Reset local manifest metadata after chain rollback; keep runtime tests independent.
        chain.deployment.pop("pdr_version", None)
        chain.deployment.pop("session_id", None)
        if mode != "FULL_V1":
            activate(chain, keys, tmp_path / mode, {"max_relative_loss_bps": 250})
        policy = (
            ProofPolicy.model_validate(chain.context()["proof_policy"])
            if mode != "FULL_V1"
            else None
        )
        for scenario, multiplier, trades in (
            ("benign", 10000, 1),
            ("benign_mild_drift", 9980, 1),
            ("below_minout", 9800, 1),
            ("above_minout_below_phi", 9940, 1),
            ("cumulative_reservation", 9990, 3),
        ):
            scenario_snapshot = rpc(chain.w3, "evm_snapshot", [])
            for i in range(trades):
                started = time.perf_counter()
                mine_current_block(chain)
                send(chain.w3, owner, chain.router.functions.setOutputPerUsdc(5 * 10**16))
                c = chain.context()
                store = Store(tmp_path / f"{mode}-{scenario}-{i}")
                p = TransactionProposal.model_validate(
                    proposal(chain, intent_id=f"TEST_ONLY_{mode}_{scenario}_{i}", slippage_bps=100)
                )
                b = BuiltTransaction.model_validate(Builder(chain, store).build(p))
                t = time.perf_counter()
                sim = SimulationEvidence.model_validate(
                    Simulator(chain, store).simulate(b.build_id, b.policy_hash)
                )
                sim_ms = (time.perf_counter() - t) * 1000
                assert sim.verification_status == "COMPLETE"
                saved = chain.snapshot(c)
                v1_gates(c, chain, b, p, sim, saved)
                proof = None
                proof_ms = 0.0
                debit = 0
                registry = Registry.model_validate(c["registry"]) if policy else None
                if mode in {"PGS_CORE", "V2_1_CORE"}:
                    session = SessionContext.model_validate(c["proof_session"])
                    if mode == "PGS_CORE":
                        session = session.model_copy(
                            update={"used_usd_e8": "0", "global_used_usd_e8": "0"}
                        )
                    oracle = OracleEvidence(
                        chain_id=31337,
                        vault=b.vault_address,
                        source_hash=policy.oracle_source_hash,
                        timestamp=c["timestamp"],
                        block_number=c["block_number"],
                        block_hash=c["block_hash"],
                        prices=tuple(
                            Price(
                                asset=a.address,
                                nominal_usd_e8=str(n),
                                low_usd_e8=str(n * 99 // 100),
                                high_usd_e8=str(n * 101 // 100),
                            )
                            for a in registry.assets
                            for n in [10**8 if a.decimals == 6 else 20 * 10**8]
                        ),
                    )
                    t = time.perf_counter()
                    proof = PGSProofEngine().prove(
                        b, sim.effects_v2, policy, registry, oracle, session, int(time.time())
                    )
                    proof_ms = (time.perf_counter() - t) * 1000
                    debit = int(proof.risk_debit_usd_e8 or "0")
                row = dict(
                    config=mode,
                    attackFamily=scenario,
                    seed=1,
                    tradeIndex=i,
                    setupBlock=c["block_number"],
                    policyVersion=c["policy_version"],
                    sim_ms=sim_ms,
                    proof_ms=proof_ms,
                    solverUnknown=bool(proof and proof.status == "INCONCLUSIVE"),
                    retryCount=0,
                )
                if proof and proof.status != "VERIFIED":
                    records.append(
                        row
                        | dict(
                            actualResult="preSignRefuse",
                            reason=proof.reason,
                            solidityGasUsed=0,
                            certifiedRiskDebit="0",
                            actualTokenDeltas=["0", "0"],
                            attackerGainWavax="0",
                            modeledRealizedLossUsdE8="0",
                            endToEnd_ms=(time.perf_counter() - started) * 1000,
                        )
                    )
                    break
                if mode == "FULL_V1":
                    a = approval_for(b, sim.evidence_root)
                    signature = Account.sign_message(
                        message(domain_for(b), a), keys["attestor"]
                    ).signature
                    fn = chain.vault.functions.executeApprovedSwap(
                        approval_tuple(a), b.router_calldata, signature
                    )
                else:
                    phi = (
                        proof.phi
                        if proof
                        else PostConditionsV2(
                            balance_bounds=tuple(
                                BalanceBound(
                                    asset=a.address,
                                    min_delta=str(
                                        -int(b.amount_in_base_units)
                                        if a.address == b.token_in.lower()
                                        else int(sim.baseline.token_out_delta_base_units)
                                        * 9960
                                        // 10000
                                    ),
                                )
                                for a in registry.assets
                            ),
                            allowance_caps=tuple(
                                AllowanceCap(token=a.address, spender=b.router)
                                for a in registry.assets
                            ),
                        )
                    )
                    if proof:
                        a = approval_v2(
                            b, sim.evidence_root, proof, c["proof_session"]["session_id"]
                        )
                    else:
                        a = ApprovalV2(
                            intentHash=keccak(b.intent_id.encode()),
                            calldataHash=b.calldata_hash,
                            policyHash=b.policy_hash,
                            evidenceRoot=sim.evidence_root,
                            proofContextHash=keccak(b"TEST_ONLY_NO_SMT_ABLATION"),
                            postConditionsHash=phi.hash,
                            sessionId=c["proof_session"]["session_id"],
                            riskDebitUsdE8="0",
                            nonce=b.nonce,
                            deadline=str(b.deadline),
                            adapter=b.router,
                            tokenIn=b.token_in,
                            tokenOut=b.token_out,
                            amountIn=b.amount_in_base_units,
                            minAmountOut=b.min_amount_out_base_units,
                        )
                    if mode != "V2_1_CORE":
                        a = a.model_copy(update={"riskDebitUsdE8": "0"})
                    signature = Account.sign_message(
                        message_v2(DomainV2(chainId=31337, verifyingContract=b.vault_address), a),
                        keys["attestor"],
                    ).signature
                    fn = chain.vault.functions.executeApprovedSwapV2(
                        a.abi_tuple, b.router_calldata, phi.abi_tuple, signature
                    )
                send(
                    chain.w3,
                    owner,
                    chain.router.functions.setOutputPerUsdc(5 * 10**16 * multiplier // 10000),
                )
                before = chain.balances()
                tx = fn.build_transaction(
                    {
                        "from": relayer.address,
                        "nonce": chain.w3.eth.get_transaction_count(relayer.address),
                        "gas": 1500000,
                        "gasPrice": chain.w3.eth.gas_price,
                    }
                )
                receipt = chain.w3.eth.wait_for_transaction_receipt(
                    chain.w3.eth.send_raw_transaction(relayer.sign_transaction(tx).raw_transaction)
                )
                after = chain.balances()
                di = int(after["usdc_base_units"]) - int(before["usdc_base_units"])
                do = int(after["wavax_base_units"]) - int(before["wavax_base_units"])
                if receipt.status == 0:
                    assert (
                        before == after and not chain.vault.functions.usedNonce(int(b.nonce)).call()
                    )
                loss = -Fraction(di * 10**8, 10**6) - Fraction(do * 20 * 10**8, 10**18)
                records.append(
                    row
                    | dict(
                        actualResult="confirmed" if receipt.status else "protectedRevert",
                        solidityGasUsed=receipt.gasUsed,
                        certifiedRiskDebit=str(
                            debit if mode == "V2_1_CORE" and receipt.status else 0
                        ),
                        actualTokenDeltas=[str(di), str(do)],
                        attackerGainWavax=str(max(0, 10 * 10**18 - do)) if receipt.status else "0",
                        modeledRealizedLossUsdE8=str(loss),
                        endToEnd_ms=(time.perf_counter() - started) * 1000,
                    )
                )
            assert rpc(chain.w3, "evm_revert", [scenario_snapshot])
    output = Path(os.environ.get("V2_ABLATION_OUTPUT", ROOT / "docs/evaluation/v2_1_ablation_results.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "environment": {
                    "os": platform.platform(),
                    "cpu": platform.processor(),
                    "python": platform.python_version(),
                    "chain": "private Anvil 31337",
                    "compiler": "solc 0.8.38 viaIR optimizer200",
                    "z3": __import__("z3").get_version_string(),
                    "baseline": "complete V1 gates + current legacy compatibility entrypoint (includes V2-disabled flag overhead)",
                },
                "records": records,
            },
            indent=2,
        )
        + "\n"
    )
    final = [
        r for r in records if r["attackFamily"] == "cumulative_reservation" and r["tradeIndex"] == 2
    ]
    assert [r["actualResult"] for r in final] == [
        "confirmed",
        "confirmed",
        "confirmed",
        "preSignRefuse",
    ]
