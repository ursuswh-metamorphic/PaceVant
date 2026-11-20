import json
from types import SimpleNamespace

import pytest

from treasury_backend.modules.alignment.provider import Completion, ShieldConfig
from treasury_backend.modules.temporal.graph_builder import GraphBuilder
from treasury_backend.modules.temporal.semantic_evaluator import TemporalSemanticEvaluator


@pytest.mark.parametrize("mode", [
    "aligned", "misaligned", "changes_core", "fabricated", "claimed_execution", "uncited_user",
])
def test_only_known_reference_links_can_be_repaired_without_changing_verdict(mode):
    graph = GraphBuilder()
    graph.node("action", "AGENT_ACTION", "UNVERIFIED", ["action"], {})
    graph.node("task", "AUTHENTICATED_USER_INTENT", "AUTHENTICATED", ["task"], {"source": "USER"})
    graph.node("observation", "TOOL_OBSERVATION", "UNTRUSTED", ["evidence"], {})
    calls = []

    class Fixture:
        evaluation_scope = "SCRIPTED_CITATIONS_NOT_LLM_ACCURACY"
        last_attempts = []

        def complete(self, messages):
            data = json.loads(messages[1]["content"])
            calls.append(data)
            repair = bool(data["citation_repair"])
            verdict = "MISALIGNED" if mode == "misaligned" else "ALIGNED"
            if repair and mode == "changes_core":
                verdict = "MISALIGNED"
            self.last_attempts = [{"status": "SUCCESS", "model": "fixture", "provider": "fixture"}]
            return Completion(json.dumps({
                "candidate_action_id": "action", "referenced_task_ids": ["task"],
                "referenced_graph_node_ids": ["action"] + ([] if mode == "uncited_user" else ["task"]) + (["observation"] if repair else []),
                "semantic_verdict": verdict,
                "contribution_assessments": [{"task_id": "task", "relationship": "DIRECT", "explanation": "Fixture"}],
                "detected_goal_drift": False, "claimed_instruction_source": "USER",
                "reasoning_summary": "Fixture semantics stay fixed while node linkage is corrected.",
                "supporting_evidence_refs": ["invented" if mode == "fabricated" else "evidence"],
                "uncertainty_reasons": [],
                "factual_claims": [{"node_id": "action", "field": "execution_state", "value": "CONFIRMED"}]
                if mode == "claimed_execution" else [],
            }), 1, {"total_tokens": 3})

    shield = SimpleNamespace(config=ShieldConfig(mode="wallet_pipeline", retries=1, context_chars=100000),
                             provider=Fixture(), config_hash="0x" + "12" * 32, active=True)
    result = TemporalSemanticEvaluator(shield).assess(graph.finish(), "action")
    if mode in {"fabricated", "claimed_execution", "uncited_user"}:
        assert result.verdict == "UNAVAILABLE" and len(calls) == 1
        assert result.finding is None
    elif mode == "changes_core":
        assert result.verdict == "UNAVAILABLE" and result.finding is None and len(calls) == 2
    else:
        assert result.verdict == mode.upper() and len(calls) == 2
        assert result.token_usage["total_tokens"] == 6
        assert result.provider_metadata["citation_repair"]["semantic_core_preserved"]

@pytest.mark.parametrize("field, asserted, invalidated, valid", [
    ("execution_state", "CONFIRMED", False, True),
    ("execution_state", "CONFIRMED", True, False),
    ("execution_state", "REVERTED", False, False),
    ("amount_in_base_units", "1", False, True),
    ("amount_in_base_units", "1 USDC", False, False),
])
def test_exact_amount_and_canonical_outcome_claims(field, asserted, invalidated, valid):
    from treasury_backend.modules.temporal.semantic_evaluator import validate_claims

    node = SimpleNamespace(node_id="evidence",
                           kind="TRANSACTION_OUTCOME" if field == "execution_state" else "AGENT_ACTION",
                           trust="VERIFIED_RECORD",
                           data={"state": "CONFIRMED", "invalidated": invalidated,
                                 "proposal": {"amount_in_base_units": "1"}})
    args = ([{"node_id": node.node_id, "field": field, "value": asserted}], {node.node_id: node}, {node.node_id})
    if valid:
        validate_claims(*args)
    else:
        with pytest.raises(ValueError):
            validate_claims(*args)
