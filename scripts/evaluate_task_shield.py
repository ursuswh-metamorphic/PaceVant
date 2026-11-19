"""Run local-case LIVE LLM checks only. Never submits transactions or loads wallet keys."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/control-plane"))

from app.alignment.engine import TaskShield  # noqa: E402
from app.alignment.provider import ShieldConfig  # noqa: E402
from app.alignment.types import Message, TaskUpdate  # noqa: E402
from app.errors import ControlError  # noqa: E402
from app.models import Mandate  # noqa: E402
from app.settings import FIXTURES  # noqa: E402
from app.storage import Store  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--cases", type=Path, default=root / "fixtures/task_shield/wallet_cases.json"
    )
    parser.add_argument(
        "--output", type=Path, default=root / "data/task-shield-live-evaluation.json"
    )
    parser.add_argument("--input-usd-per-million", type=float)
    parser.add_argument("--output-usd-per-million", type=float)
    args = parser.parse_args()
    config = ShieldConfig.from_env("FUJI")
    if not config.api_key or config.mode not in {"paper", "wallet_hardened"}:
        print(
            json.dumps(
                {
                    "status": "NOT_RUN",
                    "reason": "Configure PACEVANT_SHIELD_API_KEY and paper/wallet_hardened mode; no live LLM metrics exist.",
                }
            )
        )
        return 2
    cases = json.loads(args.cases.read_text())
    with tempfile.TemporaryDirectory(prefix="pacevant-shield-eval-") as temp:
        store = Store(Path(temp) / "evaluation.sqlite3")
        shield = TaskShield(store, config)
        try:
            mandate = Mandate.model_validate_json((FIXTURES / "mandate.json").read_text())
            shield.state.create("session_eval", mandate, 0)
            shield.update_user(
                "session_eval",
                TaskUpdate(message_id="user_eval", content=cases["user_goal"], expected_revision=0),
                authenticated=True,
            )
            reports = []
            for case in cases["cases"]:
                message = Message(
                    message_id="case_" + case["id"],
                    role=case.get("source", "ASSISTANT"),
                    content=case.get("content", case.get("tool_name", "")),
                    tool_name=case.get("tool_name"),
                )
                tool = (
                    {k: case[k] for k in ("tool_name", "arguments")}
                    if case["kind"] == "TOOL_CALL"
                    else None
                )
                report = shield.check("session_eval", message, tool=tool)
                reports.append(
                    {
                        "case_id": case["id"],
                        "expected": case["expected"],
                        "report": report.model_dump(mode="json"),
                    }
                )
            benign = [r for r in reports if r["expected"] == "ALIGNED"]
            attacks = [r for r in reports if r["expected"] == "MISALIGNED"]
            positive = sum(r["report"]["status"] == "ALIGNED" for r in attacks)
            metrics = {
                "local_attack_acceptance_rate": positive / len(attacks) if attacks else None,
                "local_benign_alignment_rate": sum(
                    r["report"]["status"] == "ALIGNED" for r in benign
                )
                / len(benign)
                if benign
                else None,
                "false_positive_rate": sum(r["report"]["status"] == "MISALIGNED" for r in benign)
                / len(benign)
                if benign
                else None,
                "false_negative_rate": positive / len(attacks) if attacks else None,
                "unavailable_count": sum(r["report"]["status"] == "UNAVAILABLE" for r in reports),
                "llm_calls": sum(r["report"]["llm_calls"] for r in reports),
                "latency_ms": sum(r["report"]["latency_ms"] for r in reports),
                "task_completion_utility": None,
                "agentdojo_asr": None,
                "estimated_cost_usd": None,
            }
            usage = {
                k: sum(r["report"]["token_usage"].get(k, 0) for r in reports)
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            if args.input_usd_per_million is not None and args.output_usd_per_million is not None:
                metrics["estimated_cost_usd"] = (
                    usage["prompt_tokens"] * args.input_usd_per_million
                    + usage["completion_tokens"] * args.output_usd_per_million
                ) / 1_000_000
            result = {
                "status": "COMPLETED_LOCAL_CASES",
                "scope": cases["scope"],
                "config": config.public(),
                "metrics": metrics,
                "token_usage": usage,
                "reports": reports,
                "limits": [
                    "Not AgentDojo or comparable paper ASR",
                    "No wallet execution",
                    "Detection acceptance differs from successful agent attack or task completion",
                    "Extraction initialization costs are separate from checker metrics",
                ],
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(
                json.dumps(
                    {"status": result["status"], "metrics": metrics, "output": str(args.output)}
                )
            )
        except ControlError as error:
            print(json.dumps({"status": "UNAVAILABLE", "reason": error.code}))
            return 1
        finally:
            shield.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
