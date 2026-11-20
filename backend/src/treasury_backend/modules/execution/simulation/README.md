# Fork simulation module

For the live Circle route, `lfj_stress.py` provisions a **hypothetical external actor only on isolated loopback Anvil**: impersonate the existing Circle masterMinter, configure/mint to that actor, then trade through the real LFJ router/pool. Setup preserves the treasury's pinned balance, feed rounds, policy and counters. Actor funding is a scenario assumption, not historical liquidity or live funding. Artifacts record setup transactions and the achieved 20/200-bps shift. The legacy faucet route retains its earlier guarded-treasury stress model. Missing impact/setup cannot yield a verified simulation.

A cold fork may lazily read many public historical slots in one EVM call. The local Anvil request timeout is bounded separately at at least 60 seconds; source reads remain bounded. This changes neither timestamps nor approval freshness. See the [live runbook](../../../../../../docs/demo/FUJI_LIVE_END_TO_END.md).

`TREASURY_FUJI_FORK_RPC_URL` optionally supplies the fork source (`B_FORK_RPC_URL` in execution settings); normal chain reads use the primary RPC. Both simulation and preflight verify the pinned fork header hash against the saved build context. Splitting providers changes performance, not chain identity or evidence authority. See the [current ITAG runbook](../../../../../../docs/demo/FUJI_ITAG_LIVE.md).

This module already implements actual EVM simulation; it is part of the unified backend, not a separate API process. `runner.py` owns `Simulator`, `fork_node`, pinned fork lifecycle and baseline/stress/preflight execution. `Simulator` is created once by `ExecutionService.start` and called through the injected execution client.

## Interfaces

- `Simulator.simulate(build_id, expected_hash)` loads an immutable build, pins the source block, runs the exact guarded vault path and fixed reserve-shift stresses, then returns shared `SimulationEvidence`.
- `Simulator.preflight_v2(request)` uses the exact compiled Phi, certified risk debit, session and required stresses, checking the final guarded transaction before attestation.
- `fork_node` starts/stops native Anvil on a temporary loopback port. The test attestor override exists only on this isolated fork. Source RPC receives reads, not a simulation swap transaction.

Final preflight replays the original pinned build block and caches results by build/proof/stress. It is not a full latest-block re-simulation. The workflow separately refreshes chain facts and the relayer estimates the live transaction; vault postconditions and counters enforce the signed limits at inclusion. See the [current system design](../../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) for assumptions and remaining gaps.

External routes on the one FastAPI app:

```text
POST /execution/v1/simulations
POST /execution/v2/simulations/preflight
```

They require `X-API-Key`, `Idempotency-Key` and the shared typed request body. The normal workflow calls the same ExecutionService directly; it does not call these URLs over HTTP. Service-level rate limiting and mutation locks apply to both paths.

## Inputs, evidence and boundaries

Inputs are the immutable build/policy, chain settings/deployment, native Anvil path, and V2 proof/session where applicable. Evidence includes baseline/stress outcomes, before/after balances and allowances, receipts, logs/traces, provenance, source block/hash and content-addressed artifact references. Extraction logic belongs to `../evidence/extractor.py`; persistence belongs to `../storage.py`.

Simulation does not authorize or sign a live transaction. Workflow still verifies evidence hashes/bindings, chain state, oracle freshness, economic risk and proof; signing revalidates before final submission. Missing/stale/mismatched evidence must fail closed. Keep final compiled Phi/debit on the preflight path; never substitute an unguarded adapter quote.

LOCAL supports MockUSDC/MockWAVAX/MockSwapAdapter. The live Fuji environment uses Circle test USDC, WAVAX and the LFJ adapter, including concrete reserve-shift stresses and Chainlink reference rounds. An adapter quote is not a trusted market oracle. Additional protocols require their own builder, stress, evidence and policy review.

## Development and verification

Install Python dependencies, native Foundry v1.7.1 and compiled contracts from repository root:

```sh
uv run --locked python tools/contracts/bootstrap.py
uv run --locked python tools/contracts/foundry.py forge build
uv run --locked python -m pytest backend/tests/execution/test_v2_execution.py backend/tests/execution/test_integration.py -q
uv run --locked python -m pytest backend/tests/integration/test_treasury_ops.py -q
```

The operator smoke exercises one real local workflow through this module and receipt confirmation with no Node executable and with the retired execution API port occupied. For changes, cover both accepted simulation and missing/stale/wrong-binding/protected-revert cases. Add feature-specific tests in this module's `tests/` directory when needed. See [execution](../README.md) and [single-app architecture](../../../../../../docs/architecture/UNIFIED_BACKEND.md).

Managed Anvil processes receive only the SDK native-tool OS/path/cache/certificate environment. Wallet/model/service credentials are excluded. This is environment minimization, not an OS sandbox; native tools remain trusted local executables.
