"""Run the production TaskShield engine on a frozen, read-only single-transaction corpus."""

import argparse
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment.engine import TaskShield
from treasury_backend.modules.alignment.provider import ChatProvider, ShieldConfig
from treasury_backend.modules.alignment.types import Message, TaskUpdate
from treasury_backend.modules.persistence import Store
from treasury_backend.operations.env import read_env
from treasury_backend.paths import ROOT

CONTEXT_FIELDS = (
    "input_asset",
    "output_asset",
    "input_price_usd",
    "output_price_usd",
    "reference_timestamp",
    "reference_quote_base_units",
    "quote_provenance",
    "quote_definition",
    "amount_rounding_usd",
    "price_provenance",
)


def model_input(case):
    """Gold, source IDs, source annotations and expected constraint parser output never enter inference."""
    return {
        "intent": case["curated_intent"],
        "transaction": case["curated_transaction"],
        "context": {k: case["required_context"][k] for k in CONTEXT_FIELDS},
    }


class Budget:
    def __init__(self, path, max_requests, max_tokens):
        self.path = path
        self.lock = threading.Lock()
        self.calls = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
        self.requests = len(self.calls)
        self.tokens = sum(c["charged_tokens"] for c in self.calls)
        self.reserved = 0
        self.max_requests, self.max_tokens = max_requests, max_tokens

    def start(self, maximum):
        with self.lock:
            if (
                self.requests >= self.max_requests
                or self.tokens + self.reserved + maximum > self.max_tokens
            ):
                raise ControlError("BENCHMARK_BUDGET_LIMIT")
            self.requests += 1
            self.reserved += maximum

    def finish(self, record, maximum):
        with self.lock:
            self.reserved -= maximum
            self.tokens += record["charged_tokens"]
            self.calls.append(record)
            with self.path.open("a", encoding="utf8") as out:
                out.write(json.dumps(record, separators=(",", ":")) + "\n")
                out.flush()


class Meter:
    def __init__(self, config, budget, opaque_id):
        self.provider = ChatProvider(config)
        self.evaluation_scope = "REAL_PROVIDER_OFFLINE_SOURCE_PROTOCOL"
        self.budget, self.opaque_id = budget, opaque_id
        self.calls = []

    @property
    def last_attempts(self):
        return self.provider.last_attempts

    def complete(self, messages):
        encoded = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode()
        maximum = len(encoded) + 4096
        self.budget.start(maximum)
        record = {
            "evaluation_id": self.opaque_id,
            "input_sha256": hashlib.sha256(encoded).hexdigest(),
            "input_bytes": len(encoded),
            "charged_tokens": maximum,
        }
        start = time.monotonic()
        try:
            result = self.provider.complete(messages)
            record["usage"] = result.usage
            record["charged_tokens"] = result.usage.get("total_tokens") or maximum
            record["status"] = "SUCCESS"
            return result
        except Exception:
            record["status"] = "FAILED"
            raise
        finally:
            record["latency_ms"] = round((time.monotonic() - start) * 1000)
            record["provider_trace"] = self.last_attempts
            self.calls.append(record)
            self.budget.finish(record, maximum)

    def close(self):
        self.provider.close()


def evaluate(case, config, budget):
    opaque_id = case["benchmark_id"]
    context = model_input(case)
    start = time.monotonic()
    provider = Meter(config, budget, opaque_id)
    prediction = "UNAVAILABLE"
    report = None
    error = None
    with TemporaryDirectory() as directory:
        shield = TaskShield(
            Store(Path(directory) / "evaluation.db"),
            config,
            provider,
            clock=lambda: case["required_context"]["reference_timestamp"],
        )
        try:
            schema = {
                "chain_id": context["transaction"]["chain_id"],
                "protocol": "Uniswap V2",
                "assets": [context["context"]["input_asset"], context["context"]["output_asset"]],
                "fixed_benchmark_context": context["context"],
                "execution_supported": False,
            }
            shield.state.create_evaluation(
                "sample", schema, case["required_context"]["reference_timestamp"]
            )
            shield.update_user(
                "sample",
                TaskUpdate(message_id="user", content=context["intent"], expected_revision=0),
                authenticated=True,
            )
            report = shield.check(
                "sample",
                Message(
                    message_id="proposal",
                    role="ASSISTANT",
                    content="Propose this single swap with the exact supplied call arguments.",
                    tool_name="source_uniswap_v2_swap",
                ),
                tool={"tool_name": "source_uniswap_v2_swap", "arguments": context["transaction"]},
            )
            prediction = {
                "ALIGNED": "ACCEPT",
                "MISALIGNED": "REJECT",
                "UNAVAILABLE": "UNAVAILABLE",
                "UNCERTAIN": "UNAVAILABLE",
            }[report.status]
        except ControlError as exc:
            error = exc.code
        finally:
            shield.close()
    return {
        "benchmark_id": opaque_id,
        "prediction": prediction,
        "report": report.model_dump(mode="json") if report else None,
        "error": error,
        "calls": provider.calls,
        "wall_ms": round((time.monotonic() - start) * 1000),
        "execution_eligibility": "UNSUPPORTED_EXECUTION",
        "broadcasts": 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "fixtures/evaluation/curated-300/benchmark_300_curated.jsonl",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--limit", type=int, default=300)
    p.add_argument("--concurrency", type=int, choices=(1, 2), default=2)
    p.add_argument("--max-requests", type=int, default=650)
    p.add_argument("--max-tokens", type=int, default=2000000)
    args = p.parse_args()
    rows = [json.loads(s) for s in args.dataset.read_text().splitlines()][: args.limit]
    cfg = ShieldConfig.from_values("FUJI", read_env(ROOT / ".env"))
    cfg = replace(
        cfg,
        mode="paper",
        retries=0,
        fallbacks=(),
        timeout=min(cfg.timeout, 25),
        context_chars=32000,
        max_calls=2,
    )
    if not cfg.api_key:
        p.error("Primary provider credential missing")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "implementation_sha256": {
            str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(
                path.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            for path in sorted(
                (ROOT / "backend/src/treasury_backend/modules/alignment").glob("*.py")
            )
        },
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "dataset_lf_sha256": hashlib.sha256(
            args.dataset.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "config": cfg.public(),
        "base": "ad01336dbce5e512a48bdea8207df85972f8eb3e",
        "mode": "PRODUCTION_TASK_SHIELD_PAPER_OFFLINE",
        "native_transactions": 0,
        "maximum_requests": args.max_requests,
        "maximum_tokens": args.max_tokens,
    }
    path = args.output / "run.json"
    if path.exists():
        previous = json.loads(path.read_text())
        stable_keys = (
            "implementation_sha256",
            "config",
            "base",
            "mode",
            "native_transactions",
            "maximum_requests",
            "maximum_tokens",
        )
        if (
            any(previous[k] != manifest[k] for k in stable_keys)
            or previous.get("dataset_lf_sha256", previous["dataset_sha256"])
            != manifest["dataset_lf_sha256"]
        ):
            p.error("Run input or configuration changed; use a new directory")
    else:
        path.write_text(json.dumps(manifest, indent=1) + "\n")
    journal = args.output / "predictions.jsonl"
    completed = (
        {json.loads(s)["benchmark_id"] for s in journal.read_text().splitlines()}
        if journal.exists()
        else set()
    )
    budget = Budget(args.output / "provider_calls.jsonl", args.max_requests, args.max_tokens)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(evaluate, row, cfg, budget): row["benchmark_id"]
            for row in rows
            if row["benchmark_id"] not in completed
        }
        for future in as_completed(futures):
            result = future.result()
            with journal.open("a", encoding="utf8") as out:
                out.write(json.dumps(result, separators=(",", ":")) + "\n")
            completed.add(result["benchmark_id"])
            print(
                len(completed),
                result["benchmark_id"],
                result["prediction"],
                "calls",
                budget.requests,
                flush=True,
            )


if __name__ == "__main__":
    main()
