"""Generate illustrative wire fixtures; these artifacts never authorize execution."""

import json

from treasury_backend.config.execution import ROOT
from treasury_backend.modules.execution.crypto import canonical, content_hash
from treasury_backend.modules.execution.models import (
    Baseline,
    BuiltTransaction,
    ExecutionResult,
    SimulationEvidence,
    StressTest,
    TransactionProposal,
)


def generate():
    v = json.loads((ROOT / "fixtures/eip712_golden/vector.json").read_text())
    a = v["approval"]
    p = TransactionProposal(
        intent_id="intent_fixture_normal",
        mandate_id="mandate_demo",
        mandate_version=1,
        action="SWAP_EXACT_INPUT",
        chain_id=43113,
        vault_address=v["domain"]["verifyingContract"],
        router=a["router"],
        token_in=a["tokenIn"],
        token_out=a["tokenOut"],
        amount_in_base_units="200000000",
        slippage_bps=40,
        recipient=v["domain"]["verifyingContract"],
        deadline=int(a["deadline"]),
        user_goal_reason="Input template only; replace addresses and deadline from live context",
    )

    def save(path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(obj))

    save(ROOT / "fixtures/normal_swap.json", p.model_dump())
    save(
        ROOT / "fixtures/exposure_limit.json",
        {
            **p.model_dump(),
            "intent_id": "intent_fixture_exposure",
            "amount_in_base_units": "500000000",
        },
    )
    save(
        ROOT / "fixtures/injection.json",
        {
            **p.model_dump(),
            "intent_id": "intent_fixture_injection",
            "recipient": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        },
    )
    b = BuiltTransaction(
        build_id="build_mock_001",
        intent_id="intent_fixture_mock",
        chain_id=43113,
        vault_address=v["domain"]["verifyingContract"],
        router=a["router"],
        token_in=a["tokenIn"],
        token_out=a["tokenOut"],
        amount_in_base_units=a["amountIn"],
        min_amount_out_base_units=a["minAmountOut"],
        router_calldata=v["router_calldata"],
        calldata_hash=a["calldataHash"],
        policy_hash=a["policyHash"],
        nonce=a["nonce"],
        deadline=int(a["deadline"]),
        quote_ref="mock://quote_001",
    )
    save(ROOT / "fixtures/mock/built_transaction.json", b.model_dump())
    baseline = Baseline(
        execution_status="SUCCESS",
        token_in_delta_base_units="-500000000",
        token_out_delta_base_units="25000000000000000000",
        unexpected_transfer=False,
        unauthorized_approval=False,
        gas_used="210000",
    )
    stress = [
        StressTest(
            scenario_id="reserve_shift_mild",
            status="SUCCESS_SAFE",
            scenario_hash=content_hash({"mock": "mild"}),
            output_base_units="24950000000000000000",
        ),
        StressTest(
            scenario_id="reserve_shift_adverse",
            status="PROTECTED_REVERT",
            scenario_hash=content_hash({"mock": "adverse"}),
            output_base_units="0",
            revert_reason="MIN_OUTPUT_NOT_MET",
        ),
    ]
    manifest = {
        "chain_id": b.chain_id,
        "vault_address": b.vault_address,
        "policy_hash": b.policy_hash,
        "calldata_hash": b.calldata_hash,
        "fork_block": 12345678,
        "bytecode_hash": content_hash({"mock": "bytecode"}),
        "scenario_artifacts": [],
        "parser_version": "extractor-v1",
        "verification_status": "INCOMPLETE",
        "source": "MOCK_FIXTURE",
        "baseline": baseline.model_dump(),
        "stress_tests": [s.model_dump() for s in stress],
    }
    save(ROOT / "fixtures/mock/manifest.json", manifest)
    e = SimulationEvidence(
        intent_id=b.intent_id,
        build_id=b.build_id,
        chain_id=b.chain_id,
        vault_address=b.vault_address,
        policy_hash=b.policy_hash,
        calldata_hash=b.calldata_hash,
        nonce=b.nonce,
        deadline=b.deadline,
        fork_block=12345678,
        bytecode_hash=manifest["bytecode_hash"],
        simulation_mode="LOCAL_TEST_ATTESTOR",
        baseline=baseline,
        stress_tests=stress,
        verification_status="INCOMPLETE",
        source="MOCK_FIXTURE",
        artifact_refs=[],
        evidence_manifest_ref="mock://fixtures/mock/manifest.json",
        evidence_root=content_hash(manifest),
    )
    save(ROOT / "fixtures/mock/simulation_evidence.json", e.model_dump())
    result = ExecutionResult(
        build_id=b.build_id,
        decision_id="decision_mock_only",
        chain_id=43113,
        tx_hash=content_hash({"mock": "not-a-real-transaction"}),
        status="CONFIRMED",
        block_number=12345680,
        gas_used="210000",
        actual_token_in_delta_base_units="-500000000",
        actual_token_out_delta_base_units="25000000000000000000",
        event_refs=["SwapExecuted"],
        artifact_refs=["mock://receipt"],
    )
    save(ROOT / "fixtures/mock/execution_result.json", result.model_dump())
