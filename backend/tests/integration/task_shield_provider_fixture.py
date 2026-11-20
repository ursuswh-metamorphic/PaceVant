"""Loopback HTTP protocol fixture for A+B tests; NOT an LLM or detection evaluator."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        data = json.loads(payload["messages"][1]["content"])
        if "bound_task_id" in data:
            values = dict(task_id=data["bound_task_id"], action_ref=data["action_ref"],
                          finding_type="OBJECTIVE_ALIGNMENT", verdict="ALIGNED",
                          evidence_refs=[next(iter(data["evidence_catalog"])), data["action_ref"]],
                          explanation="Scripted HTTP fixture; not model accuracy.")
        elif "graph" in data:
            candidate = data["candidate_action_id"]
            task = data["active_task_ids"][0]
            values = {
                "candidate_action_id": candidate,
                "referenced_task_ids": [task],
                "referenced_graph_node_ids": [candidate, task],
                "semantic_verdict": "ALIGNED",
                "contribution_assessments": [
                    {"task_id": task, "relationship": "DIRECT", "explanation": "Scripted fixture."}
                ],
                "detected_goal_drift": False,
                "claimed_instruction_source": "USER",
                "reasoning_summary": "Scripted trajectory response for protocol testing.",
                "supporting_evidence_refs": [candidate, task],
                "uncertainty_reasons": [],
            }
        elif "subject" in data:
            message = data["message"]
            values = (
                ["Buy WAVAX with 200 USDC"]
                if message["role"] == "USER"
                else [message["content"]]
                if message["role"] == "ASSISTANT"
                else []
            )
        else:
            values = [
                {
                    "user_task_instruction": t,
                    "ContributeTo score": 1,
                    "reason": "Explicit local protocol fixture, NOT model inference",
                }
                for t in data["user_tasks"]
            ]
        result = {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(values)}}],
            "usage": {"total_tokens": 1},
        }
        raw = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
