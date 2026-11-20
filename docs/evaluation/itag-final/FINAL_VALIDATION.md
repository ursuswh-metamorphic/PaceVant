# Final validation

Base: `39342cb9ca78e95fc84672a0d98d80974173de4e`. Feature branch: `codex/itag-final-security-validation`. Scope: synthetic comparisons, real DeepSeek inference on synthetic histories, local Anvil execution, and read-only public Fuji checks.

## Decision evidence

| Configuration | Scripted interventions on 12 adverse cases | Scripted approvals on 12 benign cases | Live interventions on 3 adverse cases, each pass | Live approvals on 3 benign cases, each pass |
|---|---:|---:|---:|---:|
| A. Wallet | 0 | 12 | 0 | 3 |
| B. Wallet and action Shield | 0 | 12 | 0 | 3 |
| C. Deterministic ITAG | 8 | 12 | 1 | 3 |
| D. Shield and deterministic ITAG | 8 | 12 | 1 | 3 |
| E. Full hybrid | 8 | 12 | 3 | 0 |

**Temporal contribution.** Of 12 adverse fixture histories, eight changed the decision once deterministic ITAG was added. Three were rejected, one required replanning and four escalated. The other four had explicit purpose conflicts within numerical bounds and were approved by all scripted configurations. C/D/E thus have intervention recall 8/12, false-positive rate 0/12, precision 8/8 and F1 16/20 in this suite. The matched benign candidates remained eligible. Thirty earlier regression cases also replayed without a label mismatch. Two older scripted hybrid-only cases reflect their scripted provider rules.

**Incremental Graph-Aware AI.** Seven-condition semantic-only lift was 0/4 eligible scripted cases and 0/2 eligible live cases in each of two passes on the same pairs. Raw v2.3 model verdicts were MISALIGNED on both purpose conflicts, ALIGNED on all three controls and ALIGNED on the budget case. Four responses failed evidence binding; two failed structured factual validation. All six became UNAVAILABLE and E escalated all six, including three false interventions on benign cases. All action Shield candidate results were ALIGNED. Five deterministic verdicts were PASS and one was REPLAN. Attribution to semantic detection is therefore zero, even though invalid model evidence materially affected the final SDE decision. This experiment did not produce a new validated real MISALIGNED/UNCERTAIN finding through SDE. The observed failure mode is a cost to availability. Candidate identifier namespaces, source attribution and structured factual reporting merit further held-out evaluation. Do not relax the evidence checks to improve the score.

**Explanation and provenance.** Nine checks compare the pre-sign records against graph and scenario inputs. Each holds in 24/24 scripted cases and 6/6 in each live batch. Scripted findings have a usable citation denominator of 24; live findings have zero. Correct projections of amount, objective, source trust and receipt state can coexist with invalid AI reasoning. First intervention is the terminal proposal. A causal point of persuasion, independent human semantic accuracy and the total number of false free-text claims remain unknown. The [review sheet](EXPLANATION_REVIEW.json) retains the seven attribution fields for each observation.

**Execution and recovery.** temporal/verifier.verify, TemporalSemanticEvaluator.before_decision, temporal/fusion.fuse and workflows/evaluation.py feed the SDE. Signing rechecks the current task and decision binding. In the bounded Anvil test, two distinct 100 USDC actions confirmed and reconciled. That run also hit the exposure limit on the third request. To isolate the enforcing component, the final regression uses two confirmed 10 USDC swaps within a 20 USDC budget followed by another 10 USDC candidate. All three have PASS risk and VERIFIED proof. Replaying the third candidate at its decision timestamp with the same Anvil proof, risk, simulation and block context gives A/B APPROVE and C/D/E REJECT. The actual full pipeline returned only ITAG_BUDGET_EXCEEDED and ITAG_BUDGET_ALREADY_SPENT, produced no signature and kept the relayer nonce unchanged. [Isolated counterfactuals and actual receipts](ANVIL_BUDGET_ISOLATION.json). Replan suggestions remain bounded by the available step/task budget and must re-enter the security checks. Existing regressions exercise cancellation, pending records, receipt mismatch, stale bindings, provider failure, proof, risk, preflight, replay and sponsor debit. Neither the synthetic benchmark nor a recovery suggestion can sign. See [local evidence](ANVIL_DEMOS.json) and [enforcement tests](INTEGRATION_SECURITY_RESULTS.json).

**Time.** From case input to five counterfactual SDE outputs, live inference runs had median 6.58 s / 7.07 s and nearest-rank p95 6.80 s / 7.63 s for six cases per pass. The graph-model portion had median 3.32 s / 4.27 s. These are offline candidate times with real network inference. On Anvil with scripted models, the two approved workflows reached SDE in 2.016 s and 1.849 s; the recorded proposal-to-confirmed interval was four seconds each at one-second resolution. See [latency](LATENCY_REPORT.json) and [cumulative function profile](ANVIL_PROFILE.json). Nested profiler values overlap. No new public Fuji completion latency was measured.

## Reproduction

Run inside a disposable checkout with the locked Python environment, Node dependencies, Foundry 1.7.1 and project Solidity dependencies. Full LOCAL regression uses disposable signing accounts. Use an isolated checkout without a personal .env for pytest; the optional live benchmark reads a provider configuration explicitly. Each new result path must be unused. The reports can be reviewed offline.

```sh
uv sync --locked
npm ci --ignore-scripts
uv run --locked python tools/contracts/bootstrap.py
uv run --locked python tools/contracts/foundry.py forge build
uv run --locked python -m pytest -q
uv run --locked python tools/contracts/foundry.py forge test -vv
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python tools/quality/scan_secrets.py
npm run test:integration
npm run check:frontend
node --check frontend/itag-viewer.js
uv run --locked python tools/evaluation/evaluate_itag.py --output /tmp/itag-legacy.json
uv run --locked python tools/evaluation/itag_final.py --output /tmp/itag-scripted.json
uv run --locked python tools/evaluation/itag_final.py --live --env-file /path/to/provider.env --output /tmp/itag-live.json
uv run --locked python tools/evaluation/itag_final.py --live --allow-repair --env-file /path/to/provider.env --output /tmp/itag-replication.json
uv run --locked python tools/evaluation/review_itag_runs.py docs/evaluation/itag-final /tmp/itag-review
uv run --locked python -m pytest backend/tests/execution/test_itag_unified.py -q -k two-authorized --basetemp=/tmp/new-itag-demo-test
uv run --locked python tools/evaluation/export_itag_local.py /tmp/new-itag-demo-test/test_itag_v2_artifact_budget_a0/itag.sqlite3 /tmp/new-itag-demo.json
uv run --locked treasury doctor --network fuji --live
uv run --locked python tools/evaluation/verify_fuji_queries.py --report docs/audit/web-demo-fuji-chain-evidence.json --queries docs/audit/web-demo-live-proof
```

In PowerShell substitute fresh temporary paths for `/tmp`. Pytest's generated subdirectory can vary by version; use the local bounded-case DB. The historical proof command currently reports CURRENT_ENCODER_MISMATCH. The secret scanner writes its standard local report. Raw report files preserve the measured prompt revisions; rerunning today uses the current prompt and produces new IDs, model outputs and timings.

## Release checks and limits

Baseline 481 Python passed and 4 skipped; final full regression 490 passed and 4 skipped. All 60 Solidity tests passed. A focused rerun passed the final, more discriminating 10 USDC bounded-case assertion and the final label-flip test. The four default skips are enumerated with reasons in INTEGRATION_SECURITY_RESULTS.json. Browser/wire vectors and Ruff are separate checks. See [read-only readiness](DEMO_READINESS.md) for the specific vault/adapter, historical transaction and current limits. There was no real-provider + actual Anvil run in the new controlled suite, independent human labeling, broad external dataset evaluation, new public transaction, mainnet audit, hosted failover test or multi-user custody validation. The established public execution and this experiment answer different questions.
