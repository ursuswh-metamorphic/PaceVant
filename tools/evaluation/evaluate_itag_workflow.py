"""Measure one normal MOCK workflow with real time and the configured live Shield provider."""

import argparse
import json
import secrets
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]

from treasury_backend.api.control import create_app  # noqa: E402
from treasury_backend.config.control import Settings  # noqa: E402
from treasury_backend.modules.alignment.provider import ShieldConfig  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = ShieldConfig.from_env("MOCK")
    if not config.api_key or config.mode not in {"paper", "wallet_hardened"}:
        parser.error("An active Task Shield provider profile is required.")
    with TemporaryDirectory() as temp:
        token = secrets.token_urlsafe(32)
        settings = Settings(
            db=Path(temp) / "probe.sqlite3",
            operator_token=token,
            internal_token=secrets.token_urlsafe(32),
            shield=config,
            require_itag=True,
        )
        with TestClient(
            create_app(settings), headers={"Authorization": "Bearer " + token}
        ) as client:
            goal = "Buy WAVAX with 100 USDC"
            spec = (
                client.post(
                    "/v1/itag/intents",
                    json={
                        "kind": "ONE_SHOT_SWAP",
                        "mandate_id": "mandate_demo",
                        "objective": goal,
                        "deadline": int(time.time()) + 600,
                        "total_budget": "100000000",
                        "steps": [
                            {
                                "step_id": "swap",
                                "min_amount": "100000000",
                                "max_amount": "100000000",
                            }
                        ],
                    },
                )
                .raise_for_status()
                .json()
            )
            started = time.perf_counter()
            run = (
                client.post(
                    "/v1/workflows/start",
                    json={
                        "goal": goal,
                        "mandate_id": "mandate_demo",
                        "temporal_intent": {
                            "spec_id": spec["spec_id"],
                            "revision": spec["revision"],
                            "step_id": "swap",
                        },
                    },
                )
                .raise_for_status()
                .json()
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            events = (
                client.get("/v1/workflows/" + run["workflow_id"])
                .raise_for_status()
                .json()["timeline"]
            )
            report = {
                "scope": "LIVE_MODEL_MOCK_EXECUTION_REAL_CLOCK",
                "model": config.model,
                "mode": config.mode,
                "approval_ttl_seconds": 30,
                "elapsed_ms": elapsed_ms,
                "status": run["status"],
                "public_broadcasts": 0,
                "attested": any(e["stage"] == "ATTESTED" for e in events),
                "timeline": [
                    {k: e[k] for k in ("stage", "reason_codes", "timing_ms", "verdict") if k in e}
                    for e in events
                ],
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": run["status"], "elapsed_ms": elapsed_ms}))


if __name__ == "__main__":
    main()
