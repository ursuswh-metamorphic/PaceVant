"""Explicit scripted provider for deterministic protocol tests. Never installed in live runtime."""
import json

from treasury_backend.modules.alignment.provider import Completion
from treasury_backend.modules.temporal.semantic_evaluator import PROMPT


class ProtocolFixture:
    evaluation_scope = "SCRIPTED_RESPONSES_NOT_LLM_EVALUATION"
    last_attempts = []

    def complete(self, messages):
        if messages[0]["content"].startswith("Propose this bounded treasury operation"):
            terms=json.loads(messages[1]["content"])["authorized_terms"]
            result={key:terms[key] for key in ("operation","token_in","token_out","recipient","amount")}
            result["explanation"]="Local scripted protocol proposal, not model inference."
        else:
            data = json.loads(messages[1]["content"])
            if messages[0]["content"] == PROMPT:
                candidate, task = data["candidate_action_id"], data["active_task_ids"][0]
                result = {"candidate_action_id": candidate, "referenced_task_ids": [task],
                          "referenced_graph_node_ids": [candidate, task], "semantic_verdict": "ALIGNED",
                          "contribution_assessments": [{"task_id": task, "relationship": "DIRECT", "explanation": "Scripted fixture."}],
                          "detected_goal_drift": False, "claimed_instruction_source": "USER",
                          "reasoning_summary": "Scripted local protocol evaluation, not real model inference.",
                          "supporting_evidence_refs": [candidate, task], "uncertainty_reasons": []}
            elif "subject" in data:
                m = data["message"]
                result = ([m["content"]] if m["role"] in {"USER", "ASSISTANT"} or "ignore policy" in m["content"].lower() else [])
            else:
                hostile = "ignore policy" in json.dumps(data).lower()
                result = [{"user_task_instruction": text, "ContributeTo score": 0 if hostile else 1,
                           "reason": "Scripted deterministic protocol check"} for text in data["user_tasks"]]
        return Completion(json.dumps(result), 1, {"total_tokens": 1})

    def close(self):
        pass
