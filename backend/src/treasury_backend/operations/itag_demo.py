"""Run one explicit, operator-authorized ITAG goal against the running backend."""

import json
import time

import httpx

from treasury_backend.modules.planning import requested_amount, reverse_goal

from .env import atomic_json
from .errors import OpsError


def demo(p, goal):
    amount = requested_amount(goal)
    if amount is None or amount <= 0 or reverse_goal(goal):
        raise OpsError("ITAG demo needs an exact positive USDC swap goal")
    from .fuji_demo import wait_for_oracle_window

    wait_for_oracle_window(p)
    mandate = json.loads((p.control_data / "mandate.json").read_text(encoding="utf-8"))
    with httpx.Client(
        base_url=f"http://127.0.0.1:{p.a_port}",
        headers={"Authorization": "Bearer " + p.values["PACEVANT_OPERATOR_TOKEN"]},
        timeout=900,
        trust_env=False,
    ) as client:
        spec = (
            client.post(
                "/v1/itag/intents",
                json={
                    "kind": "ONE_SHOT_SWAP",
                    "mandate_id": mandate["mandate_id"],
                    "objective": goal,
                    "deadline": min(int(time.time()) + 1800, mandate["expires_at"]),
                    "total_budget": str(amount),
                    "steps": [
                        {"step_id": "swap", "min_amount": str(amount), "max_amount": str(amount)}
                    ],
                },
            )
            .raise_for_status()
            .json()
        )
        payload = {
            "goal": goal,
            "mandate_id": mandate["mandate_id"],
            "temporal_intent": {
                "spec_id": spec["spec_id"],
                "revision": spec["revision"],
                "step_id": "swap",
            },
        }
        print(
            json.dumps({"stage": "ITAG_WORKFLOW_STARTED", "spec_id": spec["spec_id"]}), flush=True
        )
        result = client.post("/v1/workflows/start", json=payload).raise_for_status().json()
        for _ in range(60):
            workflow = (
                client.get("/v1/workflows/" + result["workflow_id"]).raise_for_status().json()
            )
            if workflow["status"] not in {"SUBMITTING", "SUBMITTED"}:
                break
            time.sleep(1)
        path = p.control_data / ("itag-demo-" + result["workflow_id"] + ".json")
        atomic_json(path, workflow)
        receipt = next(
            (e["receipt"] for e in reversed(workflow["timeline"]) if e.get("receipt")), None
        )
        output = {
            "workflow_id": result["workflow_id"],
            "spec_id": spec["spec_id"],
            "status": workflow["status"],
            "tx_hash": receipt["tx_hash"] if receipt else None,
            "report": str(path),
            "reason_codes": workflow["timeline"][-1].get(
                "reason_codes", workflow["timeline"][-1].get("decision", {}).get("reason_codes", [])
            ),
        }
        print(json.dumps(output), flush=True)
        return output
