"""Publish measured hybrid comparison and transparent residual-error analysis."""

import argparse
import json
import shutil
from pathlib import Path


def percent(value):
    return "unscored" if value is None else f"{100*value:.2f}%"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comparison", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    artifact = args.output / "hybrid-task-alignment"
    artifact.mkdir(exist_ok=True)
    run = artifact / "run"
    run.mkdir(exist_ok=True)
    for name in ("run.json","predictions.jsonl","provider_calls.jsonl"):
        shutil.copy2(args.run / name,run / name)
    matrices = json.loads((args.comparison / "ABLATIONS.json").read_text())
    rows = json.loads((args.comparison / "ABLATION_PREDICTIONS.json").read_text())
    shutil.copy2(args.comparison / "ABLATIONS.json",artifact / "ABLATIONS.json")
    compact = {key:[{k:r[k] for k in ("benchmark_id","gold","prediction","family","split")} for r in data] for key,data in rows.items()}
    (artifact / "ABLATION_DECISIONS.json").write_text(json.dumps(compact,indent=2)+"\n")
    errors = [r for r in rows["D"] if r["gold"] != r["prediction"]]
    (artifact / "ERROR_CASES.json").write_text(json.dumps(errors,indent=2)+"\n")
    lines = ["# Hybrid Task Alignment results", "",
        "These are TaskShield component measurements on the unchanged 300-case adapted Uniswap V2 regression corpus. All 300 source transactions remain UNSUPPORTED_EXECUTION for the LFJ/LOCAL wallet. No source transaction was broadcast. Synthetic price-ratio quotes remain explicitly declared. This is not end-to-end wallet accuracy or an untouched generalization test.", "",
        "A verifies the existing frozen run and corpus hash; no new baseline inference was purchased. B is a paired offline replay of those exact score matrices: zero contribution within the single authenticated message scope vetoes approval. B has no new inference and its latency is inherited from A; it is not the deployed algorithm or a claim about multi-task live binding. C invokes the production source parser, normalizer, binding and verifier without AI decomposition/semantic inference, in the offline harness only. C can expose a diagnostic ACCEPT; it cannot authorize a wallet. D runs the complete default production hybrid engine with fresh DeepSeek Flash extraction and structured semantic inference, zero retries/fallbacks. Mandatory failures short-circuit the semantic call.", "",
        "| Experiment | Accuracy /300 | REJECT precision | REJECT recall | F1 | False accept /232 | False reject /68 | Unavailable/uncertain |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key in "ABCD":
        m = matrices[key]["full"]
        lines.append(f"| {key} | {percent(m['accuracy_full_denominator'])} | {percent(m['precision'])} | {percent(m['recall_full_denominator'])} | {percent(m['f1'])} | {percent(m['false_accept_rate'])} | {percent(m['false_positive_rate'])} | {m['abstained_accept']+m['abstained_reject']} |")
    lines += ["", "REJECT is the positive class. Uncertain/unavailable outputs stay in every primary denominator; they are not counted as successful detections. False-reject rate counts explicit REJECT, not abstention. The separate benign-blocked metric below includes both, so conservative abstention cannot hide loss of usability.", "",
              "| Experiment | TP | TN | FP | FN | Abstained gold ACCEPT | Abstained gold REJECT | Coverage | Benign blocked or uncertain |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for key in "ABCD":
        m=matrices[key]["full"]
        lines.append(f"| {key} | {m['tp']} | {m['tn']} | {m['fp']} | {m['fn']} | {m['abstained_accept']} | {m['abstained_reject']} | {percent(m['coverage'])} | {m['fp']+m['abstained_accept']}/68 = {percent((m['fp']+m['abstained_accept'])/68)} |")
    lines += ["", "| Experiment | p50 / p95 ms per case | Recorded calls | New calls | Reported tokens (historical for A) |",
              "|---|---:|---:|---:|---:|"]
    for key in "ABCD":
        m=matrices[key]["measurement"]
        lines.append(f"| {key} | {m['p50_wall_ms']} / {m['p95_wall_ms']} | {m['recorded_model_calls']} | {m['new_model_calls']} | {m['charged_tokens']} |")
    lines += ["", "Token counts are provider-reported usage, not a currency bill. B reuses historical calls with zero new tokens; C makes no model calls. D latency includes user extraction, local persistence/verification and any required semantic request. Therefore short-circuiting contributes to its lower latency and cost; these are not full-pipeline timings. D totals cover that final run only, excluding development iterations, independent smoke tests and the real-model LOCAL transfer.", "",
              "## The 244-case pre-existing held-out split", "",
              "| Experiment | Accuracy | REJECT recall | False accept | False reject | Unavailable/uncertain |",
              "|---|---:|---:|---:|---:|---:|"]
    for key in "ABCD":
        m=matrices[key]["held_out"]
        lines.append(f"| {key} | {percent(m['accuracy_full_denominator'])} | {percent(m['recall_full_denominator'])} | {percent(m['false_accept_rate'])} | {percent(m['false_positive_rate'])} | {m['abstained_accept']+m['abstained_reject']} |")
    lines += ["", "The split is retained for comparability, but this corpus was already inspected. It is not an independent final test. No new independently curated source test was used for a generalization claim.", "", "## Violation families", "", "| Family | Cases | A recall | B recall | C recall | D recall |", "|---|---:|---:|---:|---:|---:|"]
    for family,m in matrices['D']['per_family'].items():
        if m['gold_reject']:
            scores=" | ".join(percent(matrices[k]['per_family'][family]['recall_full_denominator']) for k in "ABCD")
            lines.append(f"| {family} | {m['n']} | {scores} |")
    loc=matrices['D']['typed_family_localization']
    lines += ["", f"D produced a typed failed constraint matching the expected broad violation family in {loc['matching_typed_failure']}/232 gold violations ({percent(loc['rate'])}). Every deterministic result retains its exact runtime constraint ID/type/code, expected/observed values and source refs. This metric is family-to-field localization, not exact original-source failure-node identity. An ABI veto may precede token-family localization when both are violated. A/B have no typed localization, not zero measured accuracy.", "",
              "## Interpretation and operational evidence", "",
              "The stated engineering targets for accuracy, REJECT recall, false accept and explicit false reject are met on this regression corpus. Benign uncertainty remains material; consult the benign-blocked column before using the system unattended. Known frozen-gold inconsistencies are documented without changing any labels. Full hybrid can score below constraints-only because schema failure or semantic uncertainty cannot grant approval.", "",
              "LOCAL Anvil swaps and ERC-20 transfers exercise simulation, economic risk, Z3 proof, SDE, attestor revalidation, PolicyVault execution and receipt/effect reconciliation. Most security regressions use clearly labelled scripted AI. One real-model LOCAL transfer and five authored real-model semantic smoke scenarios were also run; these are smoke evidence, not population accuracy estimates. No public-chain writes were used. Commands, pass counts and skip reasons are in hybrid-task-alignment/REGRESSION_RESULTS.json.", "",
              "## Reproduction", "", "```powershell",
              ".venv/Scripts/python.exe tools/evaluation/evaluate_curated_single_transaction.py --output .tools/hybrid-new-run --concurrency 2",
              ".venv/Scripts/python.exe tools/evaluation/hybrid_task_alignment.py --output .tools/hybrid-new-comparison --hybrid-run .tools/hybrid-new-run",
              ".venv/Scripts/python.exe tools/evaluation/report_hybrid_task_alignment.py --comparison .tools/hybrid-new-comparison --run .tools/hybrid-new-run --output docs/evaluation",
              ".venv/Scripts/python.exe tools/quality/validate_hybrid_isolated.py --output .tools/hybrid-new-validation",
              "```", "",
              "Inference requires the operator-configured provider credential in the ignored .env. Run journals bind canonical dataset bytes, public configuration and implementation hashes and reject incompatible resume. Baseline reproduction uses the original implementation at commit ad01336 and the preserved curated-300 run. Generated IDs and model outputs may vary in a fresh inference run; frozen logs remain exactly inspectable."]
    (args.output / "HYBRID_TASK_ALIGNMENT_RESULTS.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    lines=["# Hybrid Task Alignment error analysis", "",
           "Gold labels and all 300 frozen inputs are unchanged. The component run is D in HYBRID_TASK_ALIGNMENT_RESULTS.md. Detailed rows, actual reports and typed findings are in hybrid-task-alignment/ERROR_CASES.json.", "",
           "## Root causes", "",
           "- Baseline fusion: score compensation is confirmed by the saved contribution matrices, including single_tx_070 and single_tx_073. B isolates a replay veto effect but causes excessive false rejections. The default runtime does not use that rule.",
           "- Intent interpretation: the hybrid source grammar leaves unsupported operation/amount/time/slippage/minimum wording unresolved. This is not an LLM authorization fallback. It preserves ambiguity at the cost of benign coverage. LLM decomposition cannot widen the original text's permissions.",
           "- Task binding: the frozen corpus contains one authenticated source message per action, so it cannot establish multi-task binding accuracy. Paired production-engine regressions cover unrelated tasks, ambiguous matches, partial cancellation and stale revisions.",
           "- Deterministic verification: an initial development run missed the general phrase 'minimum receive'. A paired wording regression and unresolved-minimum guard fixed that omission; D was rerun from scratch with new inference afterward. That development run is not substituted for final D.",
           "- Semantic judgment/evidence: semantic uncertainty and invalid/fabricated citations fail closed. Five independent authored smoke scenarios with real inference check legitimate prerequisites, goal substitution and tool-authority laundering. This small set does not establish a broad detection rate.",
           "- Provider/schema: successful HTTP inference does not prove a valid assessment. Strict output-schema/citation failures remain UNCERTAIN and in the primary denominator.",
           "- Frozen gold: single_tx_036 is labelled ACCEPT but its intent says 'Min 5.8837 ETH' and amountOutMin is 5883699678499999744 wei = 5.883699678499999744 ETH. The declared tolerance covers USD sizing, not output-token minimum. The runtime correctly enforces the literal bound; the apparent false rejection stays in the reported matrix. No label correction was made.", "",
           "## Residual outcomes", "", "| Case | Gold | Predicted | Recorded cause |", "|---|---|---|---|"]
    for r in errors:
        cause=(r['actual'].get('report') or {}).get('feedback',{}).get('explanation',r['actual'].get('error'))
        lines.append(f"| {r['benchmark_id']} | {r['gold']} | {r['prediction']} | {str(cause).replace('|','/')} |")
    lines += ["", "No false ACCEPT was observed in final D on the declared 232 gold violations. That is a finite inspected regression-set result, not a proof of zero production risk. Remaining grammar ambiguity needs authenticated clarification or a broader independently validated interpretation layer; do not silently relax source constraints, tolerances, binding uniqueness or citation validation to raise coverage."]
    (args.output / "HYBRID_TASK_ALIGNMENT_ERRORS.md").write_text("\n".join(lines)+"\n",encoding="utf8")


if __name__ == "__main__":
    main()
