# Local V1 / V2.1 guard ablation (2026-11-19)

**Additional completed experiment:** [actual original-commit/full A/B protocol comparison](full_protocol_results.md), with immutable-decision attestation, durable relay, mined drift ordering, original-bytecode gas and per-stage timings. The limitations below describe this separate four-mode guard harness; the additional report closes original-source/full-protocol A/D measurement gaps without claiming full-protocol B/C measurements.

Commands: `RUN_V2_ABLATION=1 uv run --directory apps/execution-plane python -m pytest tests/test_v2_ablation.py -q` (PowerShell: set `$env:RUN_V2_ABLATION="1"` first); `uv run --locked python scripts/benchmark-v2-proof.py`. The measured ablation test passed; raw rows are in `v2_1_ablation_results.json` and `v2_1_proof_sweep.json`.

## Scope and fairness

Private Anvil chain 31337, identical initial balances, USDC6/WAVAX18, one mock adapter, 200-USDC input, 1% legacy minOut, owner test loss limit 2.5%, independent oracle band 1%, tolerance 0.4%, session $10/global $20. Each scenario restores its initial state. V1 alignment, exact builder, pinned guarded simulation/stresses, complete economic risk (exposure/fee/slippage/freshness), and SDE run for EVERY configuration; none are deliberately removed. Baseline commit full tests passed before edits, and the original two-process V1 journey remains in integration tests.

`FULL_V1` below is the complete deterministic V1 gate path + preserved legacy vault compatibility entrypoint in the current build. It includes the new `v2Enabled=false` check overhead; it is not a byte-for-byte original-bytecode gas benchmark. The quantitative harness uses local test signatures and synchronous receipt reads for every mode, rather than the application immutable-decision attestor/monitor protocol. Those complete protocols are validated separately by two-process A/B tests. No claim of a full production-protocol throughput or original-bytecode gas comparison is made.

B intentionally removes SMT; C intentionally reserves zero debit and reads zero previous risk to ablate cumulative accounting. Only the private, opt-in TEST_ONLY harness can produce those signatures; the application signer has neither mode nor bypass flags. All use the same actual guarded V2 entrypoint for B/C/D.

## Measured results

| Config | Benign pass | Drift prevention | Normal swap receipt gas | Gas delta vs compatibility V1 | E2E p50 / p95 / p99 ms | Proof p50 ms |
|---|---:|---:|---:|---:|---|---:|
| FULL_V1 | 2/2 | 1/2 | 178,596 | +0 | 4922.4 / 5181.2 / 5181.2 | n/a |
| V1_PLUS_PHI | 2/2 | 2/2 | 202,823 | +24,227 | 5971.7 / 6324.0 / 6324.0 | n/a |
| PGS_CORE | 2/2 | 2/2 | 202,835 | +24,239 | 5781.3 / 6132.5 / 6132.5 | 32.42 |
| V2_1_CORE | 2/2 | 2/2 | 242,671 | +64,075 | 5848.1 / 6383.4 / 6383.4 | 31.13 |

Drift prevention denominator is exactly TWO controlled harmful output-retention cases per configuration, not a broad APR estimate. Benign pass denominator is exactly TWO scenarios (normal and mild drift), with zero observed false rejections in those two cases. Tiny deterministic fixtures do not support statistical or real-world claims. Attacker gain is independently defined as additional WAVAX retained by the controlled adapter relative to its pre-drift quote; raw token deltas are measured from balances, and gas comes from receipts. No paper percentages are used.

- Below legacy minOut: all configurations revert; this is existing V1 protection.
- Output above old minOut but below signed Phi (0.994 of quote): V1 commits, B/C/D protectively revert; exact nonce/token/budget rollback is checked. With the tested 2.5% loss policy and worst price corner, this outcome is outside modeled ValuePolicy.
- Cumulative reservation: V1/B/C commit three 0.999-of-quote executions; D refuses the third before signing. Each first trade reserves $4.792 despite only $0.20 modeled realized loss. In this independent scenario D reserves $9.584 for two trades with $0.40 realized loss, versus $0.60 after three in A/B/C. These are conservative reservations, not a measured $10 loss.
- B and C have the same runtime outcomes in this small suite. SMT adds a source-bound universal conditional certificate, tested with SAT witnesses and unknown cases; this experiment does NOT establish an attack-rate improvement from SMT beyond these deterministic guards.

`modeledRealizedLossUsdE8 = -deltaUSDC * 1e8 / 1e6 - deltaWAVAX * 20e8 / 1e18`. Scenario states reset; summing budget fields across independent scenarios is meaningless. Successful/reverted transactions both incur gas; pre-sign refusals consume zero transaction gas. Timings include isolated fork creation, trace extraction and a fresh V1-gate subprocess, so these are harness wall-clock observations, not service latency promises. Simulation/extraction are combined; check/compile/risk/attestation/relay stage timing was not separately instrumented.

## Liveness sweep

128 exact-arithmetic fair-swap fixtures sweep relative loss {0,100,250,300} bps, band {0,10,100,300} bps, tolerance {0,40,100,500} bps, and fixed loss {$0,$1}. Actual nominal realized loss is zero. Wider assumed price domains may still justify rejection; that is conservatism rather than proof unsoundness. No inclusion/chain claim is made for this pure sweep.

Observed: 80 verified, 48 refused (37.5% of this declared nominal-benign parameter grid), 0 inconclusive. Proof latency p50/p95/p99/worst = 9.55/17.72/19.62/90.93 ms. Tau=0 fallback is recorded per case; it can tighten inclusion bounds and reduce liveness.

## Environment and limits

{"os": "Windows-11-10.0.26200-SP0", "cpu": "Intel64 Family 6 Model 154 Stepping 3, GenuineIntel", "python": "3.13.15", "chain": "private Anvil 31337", "compiler": "solc 0.8.38 viaIR optimizer200", "z3": "4.15.4", "baseline": "complete V1 gates + current legacy compatibility entrypoint (includes V2-disabled flag overhead)"}

Raw row seed = 1. One machine/run, no confidence intervals, no real AMM/MEV search, no Fuji, no full adversary taxonomy, no memory benchmark. Gas is measured for the fixed two-token/two-allowance arrays; larger arrays are forbidden rather than benchmarked. Optional runtime exposure configuration E is unavailable by design. Expanding the scenario taxonomy, independent original-bytecode deployment and per-stage instrumentation remain evaluation work; these do not block the tested core local pipeline.
