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
        if "subject" in data:
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
