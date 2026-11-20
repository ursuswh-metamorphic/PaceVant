"""Replay the ITAG benchmark against the five configured approval paths."""

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/control-plane"))

from app.alignment.provider import ShieldConfig  # noqa: E402
from app.models import Mandate  # noqa: E402
from app.storage import Store  # noqa: E402
from app.temporal.benchmark import load_cases, metrics, run_case  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", action="append")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = load_cases(ROOT / "fixtures/itag/scenarios.csv")
    if args.case:
        unknown = set(args.case) - {c["id"] for c in cases}
        if unknown:
            parser.error("Unknown case IDs: " + ", ".join(sorted(unknown)))
        cases = [c for c in cases if c["id"] in args.case]
    if not cases:
        parser.error("No matching benchmark cases.")
    config = (
        ShieldConfig.from_env("FUJI")
        if args.live
        else ShieldConfig(mode="paper", context_chars=100000)
    )
    if args.live and (not config.api_key or config.mode not in {"paper", "wallet_hardened"}):
        parser.error("The live evaluation requires an existing Task Shield provider profile.")
    mandate = Mandate.model_validate_json((ROOT / "fixtures/mock/mandate.json").read_bytes())
    fixture = json.loads((ROOT / "fixtures/mock/normal_swap.json").read_bytes())
    # Reuse configured provider infrastructure only when explicitly requested.

    from app.alignment.provider import ChatProvider

    rows = []
    with TemporaryDirectory() as temp:
        db = Store(Path(temp) / "itag-bench.sqlite3")
        for case in cases:
            row = run_case(
                db, config, case, mandate, fixture, ChatProvider(config) if args.live else None
            )
            rows.append(row)
            print(json.dumps({"case": row["id"], "sde": row["sde"]}), flush=True)
    mismatches = [
        r["id"]
        for r in rows
        if any(r[k] != r["case"][k] for k in ("action_alignment", "deterministic", "hybrid"))
        or (r["sde"]["wallet"] != "APPROVE") != (r["case"]["baseline_blocks"] == "true")
        or r["sde"]["hybrid"]
        != ("APPROVE" if r["case"]["hybrid"] == "PASS" else r["case"]["hybrid"])
        or r["first_intervention_step"]
        != (int(r["case"]["first_violation"]) if r["case"]["first_violation"] else None)
        or not r["explanation_references_grounded"]
        or (r["first_intervention_step"] is not None and not r["candidate_localized"])
        or r["untrusted_authorizes"]
    ]
    results = {
        "benchmark": "PaceVant-ITAG-Bench",
        "scope": "LIVE_LLM_SYNTHETIC_CHAIN_HISTORY"
        if args.live
        else "SCRIPTED_PROVIDER_AND_CHAIN_FIXTURES",
        "scenario_count": len(rows),
        "label_mismatches": mismatches,
        "broadcasts": 0,
        "metrics": metrics(rows),
        "rows": rows,
        "localized_interventions": sum(
            r["candidate_localized"] and r["first_intervention_step"] is not None for r in rows
        ),
        "exact_first_step_matches": sum(
            r["first_intervention_step"] == int(r["case"]["first_violation"])
            for r in rows
            if r["case"]["first_violation"]
        ),
        "grounded_reference_sets": sum(r["explanation_references_grounded"] for r in rows),
        "hybrid_only_interventions": [
            r["id"]
            for r in rows
            if r["sde"]["shield_temporal"] == "APPROVE" and r["sde"]["hybrid"] != "APPROVE"
        ],
        "average_graph_ms": round(sum(r["graph_ms"] for r in rows) / len(rows), 3),
        "average_deterministic_ms": round(sum(r["deterministic_ms"] for r in rows) / len(rows), 3),
        "shield_and_semantic_ms": sum(r["llm_ms"] for r in rows),
        "provider_reported_tokens": sum(r["tokens"] for r in rows),
        "live_attack_success_rate": None,
        "live_task_completion_rate": None,
        "human_review": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return 1 if mismatches and not args.live else 0


if __name__ == "__main__":
    raise SystemExit(main())
