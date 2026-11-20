"""Derive inspectable review and performance tables from saved synthetic experiments."""

import argparse
import json
from pathlib import Path
from statistics import median


def summarize(rows):
    valid = [r for r in rows if r["semantic_finding"]]
    benign = [r for r in rows if r["truth"]["type"] == "benign"]
    return dict(
        n=len(rows),
        valid_findings=len(valid),
        benign_n=len(benign),
        benign_approved=sum(r["sde"]["hybrid"] == "APPROVE" for r in benign),
        raw_votes={
            v: sum(r["semantic_provider"].get("prevalidation_verdict") == v for r in rows)
            for v in ("ALIGNED", "MISALIGNED", "UNCERTAIN")
        },
        effective={
            v: sum(r["semantic"] == v for r in rows)
            for v in ("ALIGNED", "MISALIGNED", "UNCERTAIN", "UNAVAILABLE")
        },
        median_wall_ms=median(r["wall_ms"] for r in rows),
        median_semantic_ms=median(r["semantic_ms"] for r in rows),
        total_tokens=sum(r["tokens"] for r in rows),
        mean_tokens_per_candidate=sum(r["tokens"] for r in rows) / len(rows),
        semantic_token_usage=[
            r["explanation"]["assessment"]["semantic"]["token_usage"] for r in rows
        ],
        graph_input_chars=[r["semantic_provider"].get("input_chars") for r in rows],
        provider_calls=sum(len(r["calls"]) for r in rows),
    )


def review(row):
    nodes = {n["node_id"]: n for n in row["graph"]["nodes"]}
    finding = row["semantic_finding"]
    conditions = dict(row["lift_conditions"])
    # Explicit exclusive-purpose pairs were reviewed against the retained objective and rationale.
    # This is an agent review, and retains provisional independent-review status.
    anchors = row["semantic_provider"].get("semantic_anchors", [])
    objective_ok = bool(anchors) and all(
        any(
            a["objective_quote"] == n["data"].get("terms", {}).get("objective")
            and n["trust"] == "AUTHENTICATED"
            for n in nodes.values()
        )
        for a in anchors
    )
    candidate_ok = all(
        a["candidate_quote"]
        == nodes[row["explanation"]["assessment"]["candidate_action_id"]]["data"]["proposal"][
            "user_goal_reason"
        ]
        for a in anchors
    )
    grounded = bool(finding) and all(n in nodes for n in finding["referenced_graph_node_ids"])
    refs = bool(finding) and set(finding["supporting_evidence_refs"]) <= {
        ref for n in finding["referenced_graph_node_ids"] for ref in nodes[n]["evidence_refs"]
    }
    conditions["explanation_factually_supported"] = bool(
        conditions["explicit_objective_conflict"]
        and conditions["valid_model_misalignment"]
        and objective_ok
        and candidate_ok
        and grounded
        and refs
    )
    return dict(
        case=row["id"],
        repetition=row.get("repetition"),
        conditions=conditions,
        semantic_only_lift=all(v is True for v in conditions.values()),
        nodes_resolve=grounded,
        refs_match_selected_nodes=refs,
        objective_anchor=objective_ok,
        candidate_anchor=candidate_ok,
        raw_vote=row["semantic_provider"].get("prevalidation_verdict"),
        effective=row["semantic"],
        sde=row["sde"],
        reviewer="IMPLEMENTING_AGENT",
        independent_human_review=None,
        free_text_factual_accuracy=None,
        first_blocked_candidate=row["first_intervention_step"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    base = Path(__file__).resolve().parents[2] / "docs/evaluation"
    package = base / "itag-semantic-reliability"
    names = (
        "LIVE_MODEL_RESULTS",
        "LIVE_MODEL_RETEST",
        "FINAL_LIVE_RESULTS",
        "ABLATION_RESULTS",
        "FINAL_SIX_CASE_SCRIPTED",
    )
    runs = {name: json.loads((package / (name + ".json")).read_bytes())["rows"] for name in names}
    evidence = {
        "review_method": "Exact anchor and reference comparison, agent semantic review of explicit exclusive-purpose pairs. Labels provisional.",
        "runs": {name: [review(r) for r in rows] for name, rows in runs.items()},
    }
    perf = {name: summarize(rows) for name, rows in runs.items()}
    perf["historical_v2_3"] = summarize(
        json.loads((base / "itag-final/LIVE_MODEL_REPLICATION.json").read_bytes())["rows"]
    )
    perf["comparison_limit"] = (
        "Different prompts, runtime IDs and non-deterministic provider outputs. Final live rows use ten cases twice. Source preview refinement followed these live measurements."
    )
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in (("EXPLANATION_VALIDATION", evidence), ("PERFORMANCE_COMPARISON", perf)):
        with (args.output / (name + ".json")).open("x", encoding="utf8") as out:
            json.dump(data, out, indent=1)
            out.write("\n")


if __name__ == "__main__":
    main()
