# Original V1 versus V2.1 through the full A/B protocol

Measured 2026-11-19 with `npm run benchmark:protocol`, equivalent to `uv run --locked python scripts/evaluate-protocol.py`. [Raw measured rows](v2_1_full_protocol_results.json). Fourteen real workflows, seven per configuration, with immutable-decision attestation, durable raw-transaction journal, source-chain mining and receipt reconciliation. All expected outcome assertions passed. Report metadata is derived from preserved workflow and SQLite build-context records. No user `.env` is loaded and no Fuji transaction is sent.

## Isolation and provenance

V1 source is archived from commit `1b09bd8dd04fd74868f30634abeec93276522d36`. Contract source bytes are checked against the Git blob; only Foundry dependency paths point to the already pinned node_modules. Original Python/vault/adapter behavior is retained. Instrumentation wraps existing functions and returns their unmodified values. V2.1 uses its full path, including repeated signer verification and final-Phi baseline/mild/adverse fork preflight. Neither application attestor has a bypass.

Both receive the same mock adapter, USDC6/WAVAX18, extra 10,000 mock USDC funding (to isolate repeated trades from the unchanged 25% exposure gate), nominal prices 1/20, 200-USDC intent and identical output-retention scenarios. V2 policy is explicitly TEST_ONLY: relative loss 250 bps, fixed loss $0, band 100 bps, tolerance 40 bps, session $10/global $20. Every independent scenario resets **chain and application SQL/journal state**; three cumulative trades share one scenario state. Otherwise the real two-protected-revert quarantine would correctly affect later unrelated tests. Owned Anvil timestamps track actual wall time; no application freshness/deadline check is relaxed.

Drift is applied **after all pre-sign/relay preflights**: a signed relayer transaction waits in the mempool; a higher-priority owner price change is mined first in the same block. The harness asserts receipt block numbers and transaction ordering. This is a controlled inclusion-drift capability, not a claim about controlling public Fuji mining.

## Outcomes and latency

| Full protocol | Harmful drift prevented | Benign allowed | Normal receipt gas | Normal workflow ms | All 7 rows p50 / p95 / p99 ms |
|---|---:|---:|---:|---:|---|
| Original FULL_V1 | 1/2 | 2/2 | 175,885 | 4,896.55 | 2,498.51 / 4,896.55 / 4,896.55 |
| V2_1_FULL_PROTOCOL | 2/2 | 2/2 | 242,683 | 5,634.46 | 12,007.90 / 12,591.63 / 12,591.63 |

Normal gas delta: +66,798 versus original V1. Below-minOut revert gas: 151,297 (V1) / 225,310 (V2.1). Above-minOut/below-Phi: V1 **commits** at 175,885; V2.1 reverts at 252,188. Calldata/signature zero bytes cause small per-run gas variations. Percentiles cover seven heterogeneous rows, including one V2 pre-sign refusal; p95/p99/worst are the largest observation. These are not steady-state throughput or confidence intervals.

Here APR means harmful output-drift scenarios prevented / the **two declared harmful scenarios**. BPR means benign executions confirmed / the **two declared benign scenarios**. APR is 1/2 versus 2/2; BPR is 2/2 in both. These denominators do not support a population attack-rate claim.

| Scenario | Original V1 | V2.1 |
|---|---|---|
| Quote retained 100% | confirmed | confirmed |
| Mild drift, 99.8% | confirmed | confirmed |
| Below minOut, 98% | protected revert | protected revert |
| Above minOut/below Phi, 99.4% | confirmed outside target modeled ValuePolicy | protected revert |
| Three 99.9% trades | all confirmed | first two confirmed, third refused before signing |

Cumulative V2 reservations: each first trade reserves $4.792 with nominal realized loss $0.20. Two trades leave **$0.416** session room and $10.416 global room. The third is `ESCALATED`, with **no signature and zero transaction gas**: the remaining-session disjunct in Check has a counterexample (`VALUE_POLICY_COUNTEREXAMPLE`). This is not a claim that three trades realized a $10 loss. For output-drift reverts, actual treasury deltas and USDC daily spend rollback are asserted; contract security tests separately assert session/global/nonce rollback.

## Stage timings

Measured nested totals for the first normal workflow, milliseconds:

| Stage | Original V1 | V2.1 |
|---|---:|---:|
| Build | 316.08 | 166.33 |
| Initial fork simulation, including reads/extraction | 1,735.64 | 1,339.44 |
| Pure extraction parse/assess subset | 0.29 | 0.15 |
| Proof total, including repeated verification | n/a | 104.58 |
| SMT Check solver subset | n/a | 2.17 |
| Phi feasibility + Compile solver subset | n/a | 5.72 |
| Certified bound solver verification subset | n/a | 1.61 |
| Final exact-Phi guarded fork preflight | n/a | 1,220.07 |
| Attestation, including trusted revalidation | 610.52 | 2,082.28 |
| Relay | 285.44 | 277.26 |
| Receipt reconciliation | 262.56 | 280.75 |

Durations are nested: **do not sum them**. Pure extraction excludes acquiring RPC balances/storage/traces; those reads remain in simulation. Analytical rational bound calculation is included in proof total; its solver check is separately timed. Proof totals aggregate all calls in the workflow. Raw rows also retain setup block, actual policy version, source/context hashes, token deltas, gas, retry/unknown/signature flags and budget remaining. The codebases have different on-chain policy versions because V2 adds a configuration action; both bind their actual version.

## Environment, reproduction and limits

Windows 11 build 26200, Intel64 Family 6 Model 154 Stepping 3, control Python 3.12.14 / execution Python 3.13.15, solc 0.8.38 viaIR optimizer 200, Anvil chain 31337, Z3 4.15.4.0. Exact Node/runtime strings are in the raw JSON. Ports, wallets, databases and source archive are isolated under ignored `.control-data-v2/evaluation/run-<timestamp>/`. Run after `npm ci --ignore-scripts`, `npm run setup`, `uv sync --locked` and `npm run compile`. Keep baseline Git commit available; this optional benchmark needs its history and is not run for every CI change.

The script validates source bytes, expected outcomes and mined transaction ordering before publishing results. Partial records and per-process logs remain local for troubleshooting. Completed runs write `docs/evaluation/v2_1_full_protocol_results.json`; timings naturally vary on rerun. Postprocessing enriches rows from the actual workflow/SQLite journals without rerunning or changing measured durations.

[Four-mode guard ablation and proof liveness sweep](v1_vs_v2_1_ablation.md) isolate Phi, SMT and budget contributions. B/C switches exist only in that TEST_ONLY guard harness; no full-application B/C latency is claimed. Wider attacks, multiple random seeds, memory profiling, sustained load, real AMM/MEV, larger registries and Fuji performance remain outside these bounded measurements. The MVP forbids arrays beyond exactly two tracked assets/two allowances. No paper percentages, universal safety claims or audited-production claims follow from these experiments.
