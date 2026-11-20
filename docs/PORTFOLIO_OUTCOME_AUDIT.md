> Imported technical reference from `origin/main` at `08c35df`. Adapted paths below use the modular Python backend. Historical test counts/live metrics in this document belong to upstream; see [current merge verification](integrations/MAIN_SYNC_2026_11_20.md) for this checkout. The current `.env` explicitly sets Task Shield to `disabled`; `paper`/`wallet_hardened` are opt-in. The current Fuji Circle-USDC/Chainlink/PDR-V2 authorization path is supported; blanket Fuji valuation blockers below describe upstream faucet-USDC only.

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

# Portfolio / outcome audit before implementation

Baseline: main `8e833d3d6eef4872f65312d2de23df47d0b1c0ab`. Feature branch: `codex/portfolio-outcome-reconciliation`.

## Existing implementation

- A `PortfolioSnapshot` stores quantities, prices, block number and a random snapshot ID. `portfolio.snapshot()` drops hash/timestamp/token identities. `history_version()` selects a global confirmed event sequence.
- B `OnchainSnapshot` is pinned internally and includes block hash/policy/balances, but the API cannot request a historical block. A checks the returned header but does not independently compare ERC-20 balances/decimals.
- Fuji reader already bounds requests, checks chain/block hash/code/decimals and keeps invalid/stale oracles in display-only observations. LFJ faucet USDC remains distinct from Circle USDC.
- A persists immutable decision bundles and attestation state with transactional reservation/CAS. `_reconcile()` checks B summaries and independently verifies receipt gas. Post-balances are best-effort latest reads and are not immutable snapshots. Confirmed workflows are not re-audited for reorgs.
- B monitor reuses ERC-20 facts and checks SwapExecuted/nonce/allowances, but does not fully check transaction calldata, canonical receipt/transaction binding or a durable reconciliation lifecycle. Receipt mismatch is signalled through a legacy result reason.
- A handles pending/unknown submission in workflow GETs, but has no durable polling queue, restart worker or read-only discovery of B's journaled build→tx mapping. Gas/history projection is event-based.

## Planned minimal extensions

1. Keep legacy economic-risk snapshot compatibility; add versioned `ObservedPortfolioSnapshot` and `VerifiedDecisionSnapshot` with canonical hashes, scoped identity and explicit eligibility. Observations cannot grant authorization. FUJI valuation remains fail-closed.
2. Add immutable SQLite snapshots/links/status events, per-environment `(chain_id, vault)` history versions, durable monitor leases/backoff and idempotent outcome/cost projections. Preserve original decisions/events and document legacy migration.
3. Reuse the existing ERC-20 extractor in the shared SDK; add one read-only on-chain outcome verifier used by B and independently by A. New read-only reconciliation report/API and build→submission lookup leave existing DTOs/PDR format intact.
4. Add historical block query to existing B snapshot/context APIs; A independently acquires balances/code/decimals/policy at the same block and compares B when available.
5. Persist pre/post observations, distinguish exact tx-log effects from unrelated snapshot balance changes, separate relayer expenses, invalidate projections on reorg and retain original evidence.
6. Add a bounded read-only reconciliation worker/API. It never calls execute, signs, broadcasts, deploys or loads wallet private keys. Existing local/fork transaction fixtures remain isolated test setup.

No alternative LFJ test-USD risk policy, Graph DB, Temporal Action Graph, Redis or Celery is introduced. Public workflow statuses and EIP-712 Approval/domain remain compatible; new internal verification/finality statuses are explicit. New SDK read-only endpoints/types are versioned together for A/B.
