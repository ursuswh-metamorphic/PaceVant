# Hybrid Task Alignment error analysis

Gold labels and all 300 frozen inputs are unchanged. The component run is D in HYBRID_TASK_ALIGNMENT_RESULTS.md. Detailed rows, actual reports and typed findings are in hybrid-task-alignment/ERROR_CASES.json.

## Root causes

- Baseline fusion: score compensation is confirmed by the saved contribution matrices, including single_tx_070 and single_tx_073. B isolates a replay veto effect but causes excessive false rejections. The default runtime does not use that rule.
- Intent interpretation: the hybrid source grammar leaves unsupported operation/amount/time/slippage/minimum wording unresolved. This is not an LLM authorization fallback. It preserves ambiguity at the cost of benign coverage. LLM decomposition cannot widen the original text's permissions.
- Task binding: the frozen corpus contains one authenticated source message per action, so it cannot establish multi-task binding accuracy. Paired production-engine regressions cover unrelated tasks, ambiguous matches, partial cancellation and stale revisions.
- Deterministic verification: an initial development run missed the general phrase 'minimum receive'. A paired wording regression and unresolved-minimum guard fixed that omission; D was rerun from scratch with new inference afterward. That development run is not substituted for final D.
- Semantic judgment/evidence: semantic uncertainty and invalid/fabricated citations fail closed. Five independent authored smoke scenarios with real inference check legitimate prerequisites, goal substitution and tool-authority laundering. This small set does not establish a broad detection rate.
- Provider/schema: successful HTTP inference does not prove a valid assessment. Strict output-schema/citation failures remain UNCERTAIN and in the primary denominator.
- Frozen gold: single_tx_036 is labelled ACCEPT but its intent says 'Min 5.8837 ETH' and amountOutMin is 5883699678499999744 wei = 5.883699678499999744 ETH. The declared tolerance covers USD sizing, not output-token minimum. The runtime correctly enforces the literal bound; the apparent false rejection stays in the reported matrix. No label correction was made.

## Residual outcomes

| Case | Gold | Predicted | Recorded cause |
|---|---|---|---|
| single_tx_003 | ACCEPT | UNAVAILABLE | MISSING_EXPLICIT_ASSET_OR_AMOUNT; UNRESOLVED_DEADLINE |
| single_tx_013 | ACCEPT | UNAVAILABLE | MISSING_CRITICAL_EVIDENCE; UNRESOLVED_OPERATION; MISSING_EXPLICIT_ASSET_OR_AMOUNT |
| single_tx_014 | ACCEPT | UNAVAILABLE | MISSING_CRITICAL_EVIDENCE; UNRESOLVED_OPERATION; MISSING_EXPLICIT_ASSET_OR_AMOUNT |
| single_tx_017 | ACCEPT | UNAVAILABLE | MISSING_EXPLICIT_ASSET_OR_AMOUNT |
| single_tx_018 | ACCEPT | UNAVAILABLE | UNRESOLVED_DEADLINE |
| single_tx_034 | ACCEPT | UNAVAILABLE | MISSING_CRITICAL_EVIDENCE; UNRESOLVED_OPERATION; MISSING_EXPLICIT_ASSET_OR_AMOUNT |
| single_tx_036 | ACCEPT | REJECT | INTENT_MIN_OUTPUT_VIOLATION |
| single_tx_042 | ACCEPT | UNAVAILABLE | UNRESOLVED_SLIPPAGE |
| single_tx_045 | ACCEPT | UNAVAILABLE | UNRESOLVED_MINIMUM_OUTPUT |
| single_tx_053 | ACCEPT | UNAVAILABLE | UNRESOLVED_DEADLINE |
| single_tx_057 | ACCEPT | UNAVAILABLE | UNRESOLVED_DEADLINE |
| single_tx_061 | ACCEPT | UNAVAILABLE | UNRESOLVED_DEADLINE |
| single_tx_064 | ACCEPT | UNAVAILABLE | MISSING_EXPLICIT_ASSET_OR_AMOUNT |

No false ACCEPT was observed in final D on the declared 232 gold violations. That is a finite inspected regression-set result, not a proof of zero production risk. Remaining grammar ambiguity needs authenticated clarification or a broader independently validated interpretation layer; do not silently relax source constraints, tolerances, binding uniqueness or citation validation to raise coverage.
