"""Measured offline ablations and comparison. Never alters the frozen corpus or labels."""

import argparse
import importlib.util
import json
import time
from collections import Counter
from math import ceil
from pathlib import Path
from statistics import median

from treasury_backend.modules.alignment.hybrid import bind, extract_constraints, normalize
from treasury_backend.modules.alignment.types import Instruction
from treasury_backend.paths import ROOT


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--hybrid-run", type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    corpus = ROOT / "fixtures/evaluation/curated-300/benchmark_300_curated.jsonl"
    cases = [json.loads(s) for s in corpus.read_text().splitlines()]
    historical = ROOT / "docs/evaluation/curated-300/run"
    import hashlib

    baseline_manifest = json.loads((historical / "run.json").read_text())
    if hashlib.sha256(corpus.read_bytes().replace(b"\r\n",b"\n")).hexdigest() != baseline_manifest["dataset_lf_sha256"]:
        raise ValueError("Frozen corpus changed")
    baseline = {
        r["benchmark_id"]: r
        for r in map(json.loads, (historical / "predictions.jsonl").read_text().splitlines())
    }
    if len(baseline) != 300:
        raise ValueError("Incomplete frozen baseline")
    report_tool = load("report_curated_single_transaction")
    input_tool = load("evaluate_curated_single_transaction")
    matrices, all_results = {}, {}
    for experiment in ("A", "B", "C", "D"):
        if experiment == "D" and not args.hybrid_run:
            continue
        actual = (
            {
                r["benchmark_id"]: r
                for r in map(
                    json.loads, (args.hybrid_run / "predictions.jsonl").read_text().splitlines()
                )
            }
            if experiment == "D"
            else {}
        )
        rows = []
        for case in cases:
            id_ = case["benchmark_id"]
            original = baseline[id_]
            start = time.perf_counter()
            checks = []
            if experiment == "A":
                prediction, result = original["prediction"], original
            elif experiment == "B":
                # Paired, labelled REPLAY ablation: the corpus has one authenticated
                # message scope per action. Veto zero-contribution requirements inside
                # that scope, not unrelated tasks in a live session. No new AI inference.
                assessed = (original.get("report") or {}).get("results", [])
                prediction = (
                    "UNAVAILABLE"
                    if not assessed
                    else "REJECT"
                    if any(
                        any(float(c["score"]) <= 0 for c in a["contributions"]) for a in assessed
                    )
                    else "ACCEPT"
                )
                result = dict(original, prediction=prediction, replay_only=True)
            elif experiment == "C":
                data = input_tool.model_input(case)
                schema = dict(
                    chain_id=data["transaction"]["chain_id"],
                    protocol="Uniswap V2",
                    authority="OFFLINE_BENCHMARK_INPUT_ONLY",
                    fixed_benchmark_context=data["context"],
                    assets=[data["context"]["input_asset"], data["context"]["output_asset"]],
                )
                instruction = Instruction(
                    instruction_id="objective",
                    text=data["intent"],
                    source="USER",
                    source_message_id="authenticated",
                    extracted_at=data["context"]["reference_timestamp"],
                )
                intent = extract_constraints(data["intent"], [instruction], 1)
                try:
                    tx = normalize(data["transaction"], schema)
                    binding, checks = bind(
                        [intent], tx, schema, data["context"]["reference_timestamp"], "candidate", 1
                    )
                    prediction = (
                        "REJECT"
                        if any(c.status == "FAIL" for c in checks)
                        or binding.verdict == "UNAUTHORIZED"
                        else "UNAVAILABLE"
                        if any(c.status == "UNKNOWN" for c in checks) or binding.verdict != "VALID"
                        else "ACCEPT"
                    )
                except (ValueError, TypeError, KeyError):
                    prediction = "REJECT"
                result = dict(
                    benchmark_id=id_,
                    prediction=prediction,
                    constraints=[c.model_dump(mode="json") for c in checks],
                    wall_ms=round((time.perf_counter() - start) * 1000, 3),
                    calls=[],
                    execution_eligibility="UNSUPPORTED_EXECUTION",
                )
            else:
                result = actual[id_]
                prediction = result["prediction"]
            rows.append(
                dict(
                    benchmark_id=id_,
                    gold=case["expected_decision"],
                    prediction=prediction,
                    family=case["expected_violation_type"],
                    split=case["split"],
                    execution_eligibility="UNSUPPORTED_EXECUTION",
                    actual=result,
                )
            )
        matrices[experiment] = dict(
            full=report_tool.metrics(rows),
            held_out=report_tool.metrics([r for r in rows if r["split"] == "held_out"]),
        )
        families = sorted({r["family"] for r in rows})
        matrices[experiment]["per_family"] = {family:report_tool.metrics([r for r in rows if r["family"] == family]) for family in families}
        walls = sorted(r["actual"].get("wall_ms",0) for r in rows)
        calls = [c for r in rows for c in r["actual"].get("calls",[])]
        matrices[experiment]["measurement"] = dict(
            p50_wall_ms=median(walls), p95_wall_ms=walls[ceil(.95*len(walls))-1],
            new_model_calls=0 if experiment in {"A","B"} else len(calls),
            recorded_model_calls=len(calls),
            charged_tokens=sum(c.get("charged_tokens",0) for c in calls) if experiment != "B" else 0,
            charged_tokens_new=sum(c.get("charged_tokens",0) for c in calls) if experiment in {"C","D"} else 0,
            replay=experiment == "B", no_inference=experiment == "C",
            verdicts=dict(Counter((r["actual"].get("report") or {}).get("status",r["prediction"]) if experiment != "B" else r["prediction"] for r in rows)),
        )
        expected_kinds = {"TOKEN_AMOUNT_DIRECTION":{"TOKEN_IN","TOKEN_OUT","AMOUNT"},
                          "MIN_OUTPUT_DEADLINE_SLIPPAGE":{"MIN_OUTPUT","SLIPPAGE","DEADLINE"},
                          "TECHNICAL":{"ABI","SCOPE","TRANSACTION_SHAPE"}}
        localized = 0
        for row in rows:
            checks = (row["actual"].get("report") or {}).get("constraints",row["actual"].get("constraints",[]))
            found = {c["constraint_type"] for c in checks if c["status"] == "FAIL"}
            if row["gold"] == "REJECT" and found & expected_kinds.get(row["family"],set()):
                localized += 1
        matrices[experiment]["typed_family_localization"] = dict(
            matching_typed_failure=localized, gold_reject=232,
            rate=localized/232 if experiment in {"C","D"} else None,
            note="Expected family mapped to typed constraint fields; not exact original failure-node ID accuracy. A/B have no typed localization.",
        )
        all_results[experiment] = rows
    (args.output / "ABLATIONS.json").write_text(json.dumps(matrices, indent=2) + "\n")
    (args.output / "ABLATION_PREDICTIONS.json").write_text(json.dumps(all_results, indent=2) + "\n")
    print(json.dumps(matrices, indent=2))


if __name__ == "__main__":
    main()
