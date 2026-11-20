> Imported technical reference from `origin/main` at `08c35df`. Adapted paths below use the modular Python backend. Historical test counts/live metrics in this document belong to upstream; see [current merge verification](integrations/MAIN_SYNC_2026_11_20.md) for this checkout. The current `.env` explicitly sets Task Shield to `disabled`; `paper`/`wallet_hardened` are opt-in. The current Fuji Circle-USDC/Chainlink/PDR-V2 authorization path is supported; blanket Fuji valuation blockers below describe upstream faucet-USDC only.

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

# Portfolio state and outcome reconciliation v2

This extension keeps the A/B architecture and EIP-712 Approval unchanged. SDK **1.3.0** adds read-only reconciliation and historical snapshot requests. Existing BuiltTransaction, SimulationEvidence, SignedPDR, ExecutionResult and OnchainSnapshot shapes remain compatible.

## Trust boundaries

`ObservedPortfolioSnapshot` is a content-addressed schema 2.0 observation: mode, chain, Vault/account, block number/hash/time, observation time, RPC identity, actual token addresses/code/decimals, integer quantities, policy and oracle metadata. Missing balances are `null`, never fabricated zero. Symbols are display metadata. IDs are Keccak hashes of RFC8785 canonical normalized model content, excluding the ID/hash fields themselves. RPC identity includes origin and a path fingerprint, so credential-bearing provider paths are not published.

An observed snapshot **always** has `authorization_eligible=false`. `VerifiedDecisionSnapshot` separately binds the build, original observation hash, scoped history version and trusted test oracle. Only existing MOCK fixtures and LOCAL controlled-test-oracle policy can produce it. FUJI and LFJ faucet USDC still fail with `ORACLE_TOKEN_IDENTITY_MISMATCH`. There is no new USD peg, quote-as-oracle, or alternative economic-risk policy.

Balances and metadata are pinned to one block and its hash is checked again. A compares B's balances, chain, account, timestamp and policy at that exact block. Native AVAX belongs to the Vault; relayer gas is an operational expense, not a Vault token debit. Independent-reader outage preserves incomplete observation data and disables decision eligibility. B and A can share an RPC endpoint: these are independent read implementations, **not independent consensus providers**.

Oracle observations preserve the represented pair, provider/contract, normalized price/decimals, update time, round where available, status and eligibility flags. Stale values may be displayed with their status; they cannot authorize. An absent oracle does not prevent observing token holdings. The existing standalone Fuji Observatory remains available without B, a Treasury mandate, or a wallet key.

The shared `treasury_contracts.outcomes.verify_outcome` independently reads the transaction, canonical receipt and pinned state. It verifies signed build/PDR binding, exact Vault calldata/value/recipient/relayer, runtime hash when recorded, log-to-receipt binding, transfer/approval edges, SwapExecuted fields, minimum output, nonce and residual allowances. LFJ router/pair are read from the deployed adapter and constrained to the known Fuji route. A and B reuse one parser/verifier; A additionally compares its result to B's independent RPC read.

`INCLUDED` means one canonical receipt block. `DEPTH_CONFIRMED` means at least two blocks in the observed chain. These are depth confidence labels, **not a claim of Avalanche consensus finality**. Terminal jobs continue periodic canonicality checks. A block reorg invalidates the former post snapshot and removes its expense from the active projection; original evidence stays immutable. Later reinclusion can reconcile again.

Snapshot differences across blocks are not transaction attribution. Exact receipt logs establish transaction effects. Extra native/token balance differences remain `INCONCLUSIVE_EXTERNAL_DELTA` and public `RECEIPT_MISMATCH`, with residual quantities exposed for review. Archive-node absence or unavailable evidence stays unresolved; latest data is never substituted for historical pre/post state.

## SQLite migration and recovery

Opening `Store` applies additive, idempotent schema v2 DDL. Back up an existing live SQLite DB with SQLite's backup API (including WAL consistency), then start both upgraded services. No existing decisions, events, signed PDRs, nonce reservations or legacy DTOs are rewritten.

| Tables | Purpose |
|---|---|
| `portfolio_snapshots`, `portfolio_links`, `portfolio_status_events` | Immutable normalized observations, workflow/decision/build/tx links, append-only lifecycle |
| `monitor_jobs` | Durable tx discovery, attempts, next poll, exclusive lease |
| `outcome_observations` | Immutable verification/poll audit in insertion order |
| `outcome_projections` | Derived current outcome; one financial projection per scoped transaction |
| `treasury_versions` | `(mode, chain_id, vault)` semantic state version |
| `state_schema_versions` | Additive migration marker, currently 2 |

Snapshot/audit tables reject UPDATE and DELETE with SQLite triggers. Lifecycle events are OBSERVED, VERIFIED, RECONCILED, SUPERSEDED and INVALIDATED. Invalidated evidence is still queryable. A historical snapshot's embedded version records its observation context; `/portfolio/current` also returns the current scoped version. Semantic changes to canonical outcome, gas or token effects advance that version; duplicate polling and changing confirmation depth alone do not.

The old no-argument global `history_version()` remains for legacy consumers. New code always uses scoped arguments. Scoped v2 counters start at zero and advance as legacy/new executions are reconciled; they do not reinterpret the former global sequence. Legacy expenses remain readable/deduplicated until a canonical v2 projection covers that tx. Legacy pre-state is explicitly labelled `LEGACY_RECONSTRUCTED_PRE`, read at the originally recorded block and compared to saved balances. If the archive block cannot be read or matches incorrectly, reconciliation stays unavailable/mismatched.

Worker bootstrap imports up to 50 missing jobs per tick from durable legacy attestation/decision/event records. Each tick processes at most five jobs in the CLI/server. An SQLite write transaction claims a five-minute lease before RPC work. Concurrent workers cannot commit an old owner's result after lease takeover. A crashed lease becomes recoverable after expiry. Polling backs off 2, 4, 8, 16, 32, then 60 seconds; canonical terminal outcomes are rechecked every 30 seconds. No Redis/Celery is required. Preserve the DB and B's durable artifact/submission directory across restart.

Financial projection, scoped version and workflow transition commit atomically. The monitor never calls execution submission. Unknown hashes are discovered only through B's existing submission journal. Expired unknown outcomes remain `EXPIRED_UNESTABLISHED` internally and retain the reservation; the existing control-plane expiry proof path remains responsible for releasing it. A known hash is never silently replaced. Repeated calls reuse the canonical post snapshot and do not charge gas twice.

To reconstruct a timeline, read immutable snapshot bodies plus links/status events ordered by event sequence, and outcome observations ordered by row insertion. Current projections provide efficient queries; they are not a substitute for the original audit. If a projection needs administrative rebuilding, preserve the immutable tables and replay complete outcome observations in insertion order, excluding polling-only entries; no automatic destructive rebuild command is introduced.

## Public status/API mapping

| Internal observation | Existing A workflow state |
|---|---|
| Pending/missing receipt, RPC outage, unknown hash | Preserve SUBMITTING/SUBMITTED; expose monitoring state/reason |
| Canonical VERIFIED success plus reconciled snapshots | CONFIRMED |
| Canonical VERIFIED revert, zero swap effects | REVERTED; actual gas may still be charged |
| Contradiction, missing required event/state, reorg, unattributable balance changes | RECEIPT_MISMATCH; retain evidence for review |

B's legacy ExecutionResult `CONFIRMED` reports inclusion and uses `CRITICAL_MISMATCH_PAUSE_REVIEW` for unsafe success. Consumers must check the new reconciliation report before treating it as verified. A does so and never turns a missing event into safe confirmation. On RPC outage after an earlier canonical outcome, the last verified projection is retained with a separate current monitor UNAVAILABLE/PENDING observation; it is not a fresh proof.

Authenticated A and observer routes:

```text
GET  /v1/portfolio/current?chain_id=43113&vault_address=0x...
POST /v1/portfolio/observe?chain_id=43113&vault_address=0x...
GET  /v1/portfolio/history?chain_id=43113&vault_address=0x...&limit=50&before=TIMESTAMP
GET  /v1/portfolio/snapshots/{snapshot_id}
GET  /v1/history/transactions?chain_id=43113&vault_address=0x...&limit=50
GET  /v1/reconciliations/{decision_id}?limit=50
GET  /v1/workflows/{workflow_id}  # existing A route, now adds reconciliation/monitoring
```

`current` is explicitly a cached observation, not revalidated authorization. `observe` performs fresh reads and stores an observation. History limit is 1..100; audit returns the most recent bounded entries. The `before` timestamp is an inclusive observation-time filter, not a unique pagination cursor. Cross-mode reads are rejected. The existing MOCK anonymous convention is preserved unless an operator credential is configured; LOCAL/FUJI require the existing Bearer operator credential.

B's additive X-API-Key routes:

```text
GET /v1/portfolio/onchain-snapshot?block_number=123
GET /v1/executions/{tx_hash}/reconciliation
GET /v1/submissions/by-build/{build_id}
```

## Key-free observer operation

The observer loads only the following environment values; it does not invoke `Settings.from_env()` of the signing control plane, read `.env`, or access ATTESTOR_KEY / PRIVATE_KEY values:

```text
PACEVANT_MODE=FUJI                     # or LOCAL with loopback Anvil, chain 31337
PACEVANT_DB=<existing A SQLite DB>
PACEVANT_CHAIN_RPC_URL=https://api.avax-test.network/ext/bc/C/rpc
PACEVANT_B_URL=<B HTTPS or loopback origin>
PACEVANT_B_TOKEN=<existing B service credential>
PACEVANT_OPERATOR_TOKEN=<separate credential, at least 24 characters>
PACEVANT_RELAYER_ADDRESS=<public relayer address>
PACEVANT_MANDATE_FILE=<optional existing mandate for fresh portfolio scope verification>
```

From repo root in PowerShell:

```powershell
# Run from the repository root with the installed modular package.
uv run --locked python -m treasury_backend.operations.observe --once
# Continuous worker plus authenticated read-only API, loopback 8020:
uv run --locked python -m treasury_backend.operations.observe --port 8020
```

To observe a public Fuji account/pool without B credentials or a configured Treasury, use the acquisition CLI (this never treats a pool as a PolicyVault):

```powershell
uv run --locked python tools/operations/portfolio_observe.py 0x9371619C8E2A487D57FB9F8E36Bcb0317Bff0529 --output data/lfj-pool-observation.json
```

The continuous worker resumes durable jobs without a workflow GET. A still reconciles on workflow GET for compatibility. The read-only server exposes no signing/execution routes. Its RPC provider allowlists read methods, restricts expected chain to 31337/43113, requires Anvil for loopback, forbids privileged/sign/send methods, bounds response size to 1 MiB, bounds individual calls and per-provider operation time, rejects credential/query-bearing RPC URLs and disables redirects/proxies.

## Remaining limits

This is a tested POC, not a light client, a consensus-finality oracle, a full wallet inventory indexer or Temporal Action Graph. It observes native AVAX and the two mandated tokens (LFJ USDC/WAVAX for account-only Fuji observation). Archive data and honest RPC responses remain dependencies. Polling is bounded per job/batch, sequential, and intended for modest POC load. Original MOCK native balance is deliberately unknown. Current balances do not establish real USD value. LFJ faucet USDC valuation remains an upstream economic-risk dependency. No public Fuji execution receipt is created by this work.
