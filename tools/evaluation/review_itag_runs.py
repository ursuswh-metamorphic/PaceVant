"""Derive per-case grounding, attribution and latency tables from immutable evaluation runs."""

import argparse
import json
from collections import Counter
from math import ceil
from pathlib import Path
from statistics import median

RUNS = ("ABLATION_RESULTS", "LIVE_MODEL_RESULTS", "LIVE_MODEL_REPLICATION")


def stats(values):
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p50": median(ordered),
        "p95_nearest_rank": ordered[ceil(0.95 * len(ordered)) - 1],
        "max": max(ordered),
    }


def audit(row, sample):
    explanation = row["explanation"]
    graph = row["graph"]
    nodes = {n["node_id"]: n for n in graph["nodes"]}
    edge_map = {e["edge_id"]: e for e in graph["edges"]}
    assessment = explanation["assessment"]
    candidate = assessment["candidate_action_id"]
    facts = explanation["recorded_facts"]
    proposal = nodes[candidate]["data"]["proposal"]
    terms = [n["data"]["terms"] for n in nodes.values() if "terms" in n["data"]]
    expected_outcomes = [
        {
            "node": n["node_id"],
            "state": n["data"]["state"],
            "trust": n["trust"],
            "invalidated": n["data"]["invalidated"],
        }
        for n in nodes.values()
        if n["kind"] == "TRANSACTION_OUTCOME"
    ]
    amounts = [
        int(h["usdc"]) * 10**6 for h in sample["input"]["history"] if h["state"] == "confirmed"
    ]
    checks = {
        "candidate_fields_match": all(proposal.get(k) == v for k, v in facts["candidate"].items()),
        "amount_and_purpose_match_input": facts["candidate"]["amount_in_base_units"]
        == str(sample["input"]["amount"] * 10**6)
        and facts["candidate"]["user_goal_reason"] == sample["input"]["purpose"],
        "objective_matches_input": any(
            t["objective"] == sample["input"]["objective"] for t in terms
        ),
        "prior_outcomes_match_graph": expected_outcomes == facts["prior_outcomes"],
        "edges_exist_with_same_provenance": all(
            edge_map.get(e["edge_id"]) == e for e in explanation["evidence_path"]
        ),
        "trust_matches_nodes": all(
            nodes[k]["trust"] == v for k, v in explanation["source_trust"].items()
        ),
        "no_untrusted_authority": not row["untrusted_authorizes"],
        "path_references_resolve": row["explanation_references_grounded"],
        "budget_matches_confirmed_inputs": int(facts["budget_in_token_base_units"]["spent"])
        == sum(amounts),
    }
    v = row["semantic"]
    conditions = dict(row["lift_conditions"])
    # An invalid/absent or aligned finding supplies no explanation of a genuine deviation.
    # A possible positive requires an actual semantic review before assigning credit.
    conditions["explanation_factually_supported"] = None if v == "MISALIGNED" else False
    return {
        "case": row["id"],
        "checks": checks,
        "citation_checks": row["review"],
        "conditions": conditions,
        "confirmed_semantic_only_lift": all(v is True for v in conditions.values()),
        "first_blocked_candidate": row["first_intervention_step"],
        "expected_first_blocked_candidate": sample["truth"]["first_blocked_candidate"],
        "model_vote": v,
        "enforcement": row["sde"]["hybrid"],
        "independent_reviewer": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    samples = {
        r["id"]: r
        for r in (
            json.loads(s)
            for s in (args.package / "LONG_HORIZON_SCENARIOS.jsonl").read_text().splitlines()
        )
    }
    review = {
        "method": "Record comparisons. Free-text factual accuracy and independent human judgments unscored.",
        "runs": {},
    }
    latency = {
        "unit": "milliseconds",
        "percentile_method": "nearest rank p95; median p50",
        "runs": {},
    }
    for run in RUNS:
        rows = json.loads((args.package / (run + ".json")).read_bytes())["rows"]
        details = [audit(r, samples[r["id"]]) for r in rows]
        review["runs"][run] = {
            "cases": details,
            "passed_by_check": dict(
                Counter(k for d in details for k, v in d["checks"].items() if v)
            ),
            "confirmed_lift": sum(d["confirmed_semantic_only_lift"] for d in details),
            "objective_conflicts": sum(
                d["conditions"]["explicit_objective_conflict"] for d in details
            ),
            "invalid_factual_claim_responses": sum(
                "ITAG_UNSUPPORTED_FACTUAL_CLAIM" in r["semantic_reasons"] for r in rows
            ),
            "total_contradicted_free_text_claims": None,
            "unavailable": sum(r["semantic"] == "UNAVAILABLE" for r in rows),
            "cases_with_valid_finding": sum(bool(r["semantic_finding"]) for r in rows),
            "held_out_ids": [r["id"] for r in rows if r["split"] == "held_out"],
        }
        fields = (
            "extraction_ms",
            "shield_ms",
            "graph_ms",
            "deterministic_ms",
            "semantic_ms",
            "wall_ms",
        )
        latency["runs"][run] = {f: stats([r[f] for r in rows]) for f in fields}
        latency["runs"][run]["provider_reported_tokens_per_case"] = stats(
            [r["tokens"] for r in rows]
        )
        latency["runs"][run]["logical_calls"] = sum(len(r["calls"]) for r in rows)
        latency["runs"][run]["provider_attempts_with_trace"] = sum(
            len(c["provider_trace"]) for r in rows for c in r["calls"]
        )
    demos = json.loads((args.package / "ANVIL_DEMOS.json").read_bytes())["rows"]
    latency["local_anvil"] = [
        {
            "workflow": r["workflow"],
            "sde": r["sde"],
            "timings_ms": r["timings_ms"],
            "stage_timestamps": r["stages"],
            "resolution": "integer Unix seconds outside ITAG_ASSESSED",
        }
        for r in demos
    ]
    latency["missing_durations"] = [
        "per-stage planner, fork init, baseline/stress, proof, signing, pre-submit and receipt high-resolution timers",
        "standalone explanation and citation repair",
        "new completed public Fuji workflow",
    ]
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for name, data in (("EXPLANATION_REVIEW", review), ("LATENCY_REPORT", latency)):
        with (args.output_directory / (name + ".json")).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=1)
            stream.write("\n")


if __name__ == "__main__":
    main()
