import json
from types import SimpleNamespace

import pytest

from treasury_backend.modules.alignment.provider import Completion, ShieldConfig
from treasury_backend.modules.temporal.graph_builder import GraphBuilder
from treasury_backend.modules.temporal.semantic_evaluator import TemporalSemanticEvaluator


@pytest.mark.parametrize("mode", ["aligned", "misaligned", "changes_core", "fabricated"])
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
                "referenced_graph_node_ids": ["action", "task"] + (["observation"] if repair else []),
                "semantic_verdict": verdict,
                "contribution_assessments": [{"task_id": "task", "relationship": "DIRECT", "explanation": "Fixture"}],
                "detected_goal_drift": False, "claimed_instruction_source": "USER",
                "reasoning_summary": "Fixture semantics stay fixed while node linkage is corrected.",
                "supporting_evidence_refs": ["invented" if mode == "fabricated" else "evidence"],
                "uncertainty_reasons": [],
            }), 1, {"total_tokens": 3})

    shield = SimpleNamespace(config=ShieldConfig(mode="wallet_pipeline", retries=1, context_chars=100000),
                             provider=Fixture(), config_hash="0x" + "12" * 32, active=True)
    result = TemporalSemanticEvaluator(shield).assess(graph.finish(), "action")
    if mode == "fabricated":
        assert result.verdict == "UNAVAILABLE" and len(calls) == 1
    elif mode == "changes_core":
        assert result.verdict == "UNAVAILABLE" and result.finding is None and len(calls) == 2
    else:
        assert result.verdict == mode.upper() and len(calls) == 2
        assert result.token_usage["total_tokens"] == 6
        assert result.provider_metadata["citation_repair"]["semantic_core_preserved"]
