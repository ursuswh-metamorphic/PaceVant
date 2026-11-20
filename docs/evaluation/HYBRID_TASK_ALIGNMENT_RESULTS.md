# Hybrid Task Alignment results

These are TaskShield component measurements on the unchanged 300-case adapted Uniswap V2 regression corpus. All 300 source transactions remain UNSUPPORTED_EXECUTION for the LFJ/LOCAL wallet. No source transaction was broadcast. Synthetic price-ratio quotes remain explicitly declared. This is not end-to-end wallet accuracy or an untouched generalization test.

A verifies the existing frozen run and corpus hash; no new baseline inference was purchased. B is a paired offline replay of those exact score matrices: zero contribution within the single authenticated message scope vetoes approval. B has no new inference and its latency is inherited from A; it is not the deployed algorithm or a claim about multi-task live binding. C invokes the production source parser, normalizer, binding and verifier without AI decomposition/semantic inference, in the offline harness only. C can expose a diagnostic ACCEPT; it cannot authorize a wallet. D runs the complete default production hybrid engine with fresh DeepSeek Flash extraction and structured semantic inference, zero retries/fallbacks. Mandatory failures short-circuit the semantic call.

| Experiment | Accuracy /300 | REJECT precision | REJECT recall | F1 | False accept /232 | False reject /68 | Unavailable/uncertain |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 49.00% | 90.38% | 40.52% | 55.95% | 56.90% | 14.71% | 11 |
| B | 68.67% | 81.22% | 80.17% | 80.69% | 17.24% | 63.24% | 11 |
| C | 95.67% | 99.57% | 100.00% | 99.78% | 0.00% | 1.47% | 12 |
| D | 95.67% | 99.57% | 100.00% | 99.78% | 0.00% | 1.47% | 12 |

REJECT is the positive class. Uncertain/unavailable outputs stay in every primary denominator; they are not counted as successful detections. False-reject rate counts explicit REJECT, not abstention. The separate benign-blocked metric below includes both, so conservative abstention cannot hide loss of usability.

| Experiment | TP | TN | FP | FN | Abstained gold ACCEPT | Abstained gold REJECT | Coverage | Benign blocked or uncertain |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 94 | 53 | 10 | 132 | 5 | 6 | 96.33% | 15/68 = 22.06% |
| B | 186 | 20 | 43 | 40 | 5 | 6 | 96.33% | 48/68 = 70.59% |
| C | 232 | 55 | 1 | 0 | 12 | 0 | 96.00% | 13/68 = 19.12% |
| D | 232 | 55 | 1 | 0 | 12 | 0 | 96.00% | 13/68 = 19.12% |

Final D uncertain/unavailable rate: 12/300 = 4.00%. Raw report status counts are preserved in ABLATIONS.json, separate from the evaluation runner's generic UNAVAILABLE prediction mapping.

| Experiment | p50 / p95 ms per case | Recorded calls | New calls | Reported tokens (historical for A) |
|---|---:|---:|---:|---:|
| A | 3048.5 / 4497 | 600 | 0 | 808420 |
| B | 3048.5 / 4497 | 600 | 0 | 0 |
| C | 0.3885 / 0.676 | 0 | 0 | 0 |
| D | 1500.0 / 3328 | 367 | 367 | 403573 |

Token counts are provider-reported usage, not a currency bill. B reuses historical calls with zero new tokens; C makes no model calls. D latency includes user extraction, local persistence/verification and any required semantic request. Therefore short-circuiting contributes to its lower latency and cost; these are not full-pipeline timings. D totals cover that final run only, excluding development iterations, independent smoke tests and the real-model LOCAL transfer.

## The 244-case pre-existing held-out split

| Experiment | Accuracy | REJECT recall | False accept | False reject | Unavailable/uncertain |
|---|---:|---:|---:|---:|---:|
| A | 51.23% | 42.78% | 54.55% | 14.04% | 9 |
| B | 68.85% | 80.75% | 16.58% | 63.16% | 9 |
| C | 95.08% | 100.00% | 0.00% | 1.75% | 11 |
| D | 95.08% | 100.00% | 0.00% | 1.75% | 11 |

The split is retained for comparability, but this corpus was already inspected. It is not an independent final test. No new independently curated source test was used for a generalization claim.

## Violation families

| Family | Cases | A recall | B recall | C recall | D recall |
|---|---:|---:|---:|---:|---:|
| MIN_OUTPUT_DEADLINE_SLIPPAGE | 60 | 35.00% | 76.67% | 100.00% | 100.00% |
| TECHNICAL | 40 | 37.50% | 87.50% | 100.00% | 100.00% |
| TOKEN_AMOUNT_DIRECTION | 132 | 43.94% | 79.55% | 100.00% | 100.00% |

D produced a typed failed constraint matching the expected broad violation family in 204/232 gold violations (87.93%). Every deterministic result retains its exact runtime constraint ID/type/code, expected/observed values and source refs. This metric is family-to-field localization, not exact original-source failure-node identity. An ABI veto may precede token-family localization when both are violated. A/B have no typed localization, not zero measured accuracy.

## Interpretation and operational evidence

The stated engineering targets for accuracy, REJECT recall, false accept and explicit false reject are met on this regression corpus. Benign uncertainty remains material; consult the benign-blocked column before using the system unattended. Known frozen-gold inconsistencies are documented without changing any labels. Full hybrid can score below constraints-only because schema failure or semantic uncertainty cannot grant approval.

LOCAL Anvil swaps and ERC-20 transfers exercise simulation, economic risk, Z3 proof, SDE, attestor revalidation, PolicyVault execution and receipt/effect reconciliation. Most security regressions use clearly labelled scripted AI. One real-model LOCAL transfer and five authored real-model semantic smoke scenarios were also run; these are smoke evidence, not population accuracy estimates. No public-chain writes were used. Commands, pass counts and skip reasons are in hybrid-task-alignment/REGRESSION_RESULTS.json.

## Reproduction

```powershell
.venv/Scripts/python.exe tools/evaluation/evaluate_curated_single_transaction.py --output .tools/hybrid-new-run --concurrency 2
.venv/Scripts/python.exe tools/evaluation/hybrid_task_alignment.py --output .tools/hybrid-new-comparison --hybrid-run .tools/hybrid-new-run
.venv/Scripts/python.exe tools/evaluation/report_hybrid_task_alignment.py --comparison .tools/hybrid-new-comparison --run .tools/hybrid-new-run --output docs/evaluation
.venv/Scripts/python.exe tools/quality/validate_hybrid_isolated.py --output .tools/hybrid-new-validation
```

Inference requires the operator-configured provider credential in the ignored .env. Run journals bind canonical dataset bytes, public configuration and implementation hashes and reject incompatible resume. Baseline reproduction uses the original implementation at commit ad01336 and the preserved curated-300 run. Generated IDs and model outputs may vary in a fresh inference run; frozen logs remain exactly inspectable.
