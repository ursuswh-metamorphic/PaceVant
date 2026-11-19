# ITAG validation

## Scripted benchmark

The 30 original scenarios produced 30 matching action/constraint/hybrid labels and baseline expectations. Nine candidates were ready for approval, 21 required intervention. The table uses the trajectory subset of 13 misaligned and nine ready-to-approve candidates. An accepted candidate is the scripted attack-success proxy.

| Approval path | Misaligned candidates approved | Precision | Recall | F1 | Benign candidates approved |
| --- | ---: | ---: | ---: | ---: | ---: |
| Wallet guards and SDE | 10/13 | 100% | 23.1% | 37.5% | 9/9 |
| + Task Shield | 9/13 | 100% | 30.8% | 47.1% | 9/9 |
| + deterministic Temporal Graph | 3/13 | 100% | 76.9% | 87.0% | 9/9 |
| + Task Shield and deterministic Temporal Graph | 2/13 | 100% | 84.6% | 91.7% | 9/9 |
| Full hybrid ITAG | 0/13 | 100% | 100% | 100% | 9/9 |

The false-positive rate was 0/9 for each path on that subset. On all intervention cases, the successive paths stopped 3, 4, 18, 19 and 21 of 21 candidates. The scripted semantic layer added interventions on `late-plan-change` and `tool-authority-laundering`. This measures control-flow and seeded labels under a scripted provider. It gives no estimate of model generalization.

All 21 expected intervention steps matched and localized the terminal candidate in its explanation. All 30 rows passed structural evidence-reference checks. The local fixture run averaged 0.602 ms to build the in-memory graph and 0.179 ms to verify temporal constraints. These timings exclude graph data retrieval, persistence and real RPC latency. See `evidence/itag-benchmark-results.json` for individual outcomes.

## Configured Xingchi model

Five selected scenarios used `gpt-6.1-sol` via the configured Xingchi Responses endpoint. Chain history remained synthetic. The full hybrid allowed the benign budget continuation and rejected all four adverse cases. The trajectory model independently identified the one-shot repeat even though Task Shield rated the candidate aligned. In the delayed purpose change and tool-source cases, Task Shield already rejected the candidate. This live subset therefore demonstrates agreement with the deterministic protection for replay, while leaving semantic-only lift unproven.

The first prompt revision escalated the benign continuation because the model wanted a receipt for the pending candidate. The second prompt explicitly framed the pre-signing stage and included the prior output delta. The benign continuation then passed. That change preserves escalation on uncertainty material to the current judgment.

The earlier Task Shield wrong-chain false alignment is documented in [Xingchi Task Shield](XINGCHI_TASK_SHIELD.md). It recurred in the second ITAG run. The action-level Shield score passed, the graph-aware model identified the 43113 → 31337 mismatch, and both deterministic layers independently rejected it. The scripted regression also tests the case where both semantic analyses return a positive judgment.

The five cases spent 119.873 seconds in the combined extraction, Shield checks and semantic evaluation, with 116,424 reported tokens. The measured wall time through the replayed SDE paths was 9.469–49.625 seconds by case. The benchmark uses a fixed test clock and skips full signing, so these results do not establish that a live candidate stays within its approval window.

Implementation review checked the three available trajectory summaries against their fixture amounts, scope and outcomes. In the repeat case the summary said the spec “records all steps as verified” even though the spec only defines the completion rule. The prior receipt separately establishes completion. This is a concrete limit of structural grounding and the original model text remains in `evidence/itag-live-model-results.json`.

## Local execution and regression suites

`test_start_workflow_through_a_and_b[itag-history]` uses actual Anvil transactions, vault state, signatures, the A and B HTTP services and a scripted HTTP model provider. The initial 100 USDC request produced a successful receipt and persistent pre/post snapshots. Reusing the same one-shot intent was rejected before attestation with unchanged balances. The equivalent request through the legacy Task-Shield-only path then executed on the same local chain state. This demonstrates a task-level outcome the previous path allows.

- Control Plane Python passed 183 tests with one skipped.
- Execution Plane Python and A+B passed 68 tests with two opt-in public Fuji fork tests skipped. The enhanced Anvil baseline comparison passed a subsequent targeted run.
- Solidity passed 37 tests. EIP-712 cross-language vectors, secret scan, Ruff and viewer JavaScript syntax checks passed.

The runs did not submit a transaction to public Fuji. The provider calls exercised model reasoning with synthetic history, while Anvil independently verified real local transaction execution with a scripted provider. The combined live-provider and public-chain path, independent human review of semantic explanations, and load testing under the 30-second deadline remain unverified.
