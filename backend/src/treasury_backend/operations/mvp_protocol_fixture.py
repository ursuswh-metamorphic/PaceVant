"""Explicit local semantic protocol fixture. Not a live model or detection benchmark."""

import json

from treasury_backend.modules.alignment.provider import Completion
from treasury_backend.modules.temporal.semantic_evaluator import PROMPT


class ProtocolFixture:
    evaluation_scope = "SCRIPTED_RESPONSES_NOT_LLM_EVALUATION"
    last_attempts = []

    def complete(self, messages):
        if messages[0]["content"].startswith("Propose this bounded treasury operation"):
            terms = json.loads(messages[1]["content"])["authorized_terms"]
            result = {
                key: terms[key]
                for key in ("operation", "token_in", "token_out", "recipient", "amount")
            }
            result["explanation"] = "LOCAL TEST: scripted bounded proposal; no model inference."
        else:
            data = json.loads(messages[1]["content"])
            if messages[0]["content"] == PROMPT:
                candidate, task = data["candidate_action_id"], data["active_task_ids"][0]
                result = {
                    "candidate_action_id": candidate,
                    "referenced_task_ids": [task],
                    "referenced_graph_node_ids": [candidate, task],
                    "semantic_verdict": "ALIGNED",
                    "contribution_assessments": [
                        {
                            "task_id": task,
                            "relationship": "DIRECT",
                            "explanation": "LOCAL scripted protocol fixture.",
                        }
                    ],
                    "detected_goal_drift": False,
                    "claimed_instruction_source": "USER",
                    "reasoning_summary": "LOCAL scripted protocol fixture, not LLM inference.",
                    "supporting_evidence_refs": [candidate, task],
                    "uncertainty_reasons": [],
                }
            elif "subject" in data:
                message = data["message"]
                result = (
                    [message["content"]]
                    if message["role"] in {"USER", "ASSISTANT"}
                    or "ignore policy" in message["content"].lower()
                    else []
                )
            else:
                hostile = "ignore policy" in json.dumps(data).lower()
                result = [
                    {
                        "user_task_instruction": text,
                        "ContributeTo score": 0 if hostile else 1,
                        "reason": "LOCAL scripted protocol fixture",
                    }
                    for text in data["user_tasks"]
                ]
        return Completion(json.dumps(result), 1, {"total_tokens": 1})

    def close(self):
        pass
