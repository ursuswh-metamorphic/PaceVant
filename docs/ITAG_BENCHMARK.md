> Technical reference imported from main@70bf6c7. Upstream metrics and 30-second TTL statements describe that branch. See [current modular integration and limitations](integrations/ITAG_MAIN_SYNC.md) for this checkout.

# PaceVant-ITAG-Bench

The editable dataset contains 30 authored scenarios in `fixtures/itag/scenarios.csv`. Each row carries the candidate-level Shield expectation, trajectory label, deterministic and hybrid verdicts, first violating step, source, wallet baseline expectation and a ground-truth explanation. The expected labels are maintained separately from any provider query. Reports explicitly identify the scripted provider when it is used.

The scenarios adapt design categories from published benchmarks.

- Intent, amount, token and chain discrepancies motivated the structured candidate variants. [intent-tx-18k](https://github.com/duanyiyao/intent-tx-18k)
- Delayed deviation motivated a plausible first action followed by a candidate with a changed purpose. [AgentLAB](https://github.com/TanqiuJiang/AgentLAB)
- Stepwise deviation labels motivated the explicit intervention-step column. [AgentDrift](https://github.com/Asif-0209/AgentDrift)
- Source and first-deviation localization motivated separate source and step annotations. [Agentic Red Team Benchmark](https://github.com/Alkur123/agentic-redteam-benchmark)
- The source hierarchy separates tool observations from user authority. [AgentDojo](https://github.com/ethz-spylab/agentdojo), [ASB](https://github.com/agiresearch/ASB)

The suite also includes benign continuations, reverts, budget reduction, cancellation, revisions, missing prerequisites and pending or invalidated outcomes. The repository's cases are original adaptations, with no source benchmark replay, training or external transaction broadcast.

```sh
uv run --locked python tools/evaluation/evaluate_itag.py --output evidence/itag-benchmark-results.json
uv run --locked --env-file .env.task-shield python tools/evaluation/evaluate_itag.py --live \
  --case scope-chain --case late-plan-change --case tool-authority-laundering \
  --case continuation-exact --case repeat-exact --output evidence/itag-live-model-results.json
```

The five paths call the real wallet and SDE logic, add Task Shield where selected, and independently add the deterministic verifier and graph-aware evaluator. The script uses MockExecutionClient for the candidate simulation and known synthetic history facts. For three invalid wallet scopes it skips the build as the application does. Label mismatches make the scripted run fail. Live mismatches are retained in the report.

The intervention metrics compare a candidate's SDE approval with all expected gate decisions. The trajectory metrics compare labelled misalignment against ready-to-approve benign rows. Recoverable amount changes and evidence incidents are excluded from that latter comparison. Candidate acceptance is the benchmark proxy for attack success. The run never broadcasts. Approval of a valid candidate is a completion proxy. Actual mined completion is checked separately on Anvil.

Localization counts a terminal candidate step and checks the explanation path for the candidate ID. Structural grounding tests reference existence and graph binding. These metrics do not measure detection before the supplied candidate, model explanation accuracy against unseen workflows or independent human review.
