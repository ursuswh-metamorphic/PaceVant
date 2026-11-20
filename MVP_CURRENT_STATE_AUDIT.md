# PaceVant MVP source audit

Audit started 20 November 2026, before implementing the narrowed two-operation scope. The current working tree includes unfinished V3 research changes from the preceding expansion request. These are not evidence of public Fuji deployment.

## Findings before implementation

* Existing system is one Python/FastAPI modular monolith with browser ES modules, SQLite, native Anvil, Z3, EIP-712 and immutable Solidity deployments. Keep this architecture.
* Baseline regression run: 542 Python tests passed, 5 skipped; baseline Foundry run passed. These runs predate the MVP changes.
* Existing Fuji manifest identifies three distinct public EOAs and one PolicyVault. Its pinned LFJ adapter explicitly rejects reverse swaps. PolicyVault V2 supports bounded swaps in principle but has no agent payment execution or payee receipt postcondition. A new immutable vault and adapter deployment is required for the full MVP; deployment is not authorized.
* Existing Task Shield and ITAG distinguish authenticated objectives from model/tool content. Existing proof is swap-specific; payment must credit measured payee receipt and independently debit payment spending limits.
* Operator relayer gas estimation/journaling exists, but physical gas-balance/fee ceilings are currently coupled to the Demo User ledger. System-funded executions need independent, mandatory fee guards and operational expense accounting.
* The unfinished V3 extension has real local swap/payment/deposit/redemption tests and a signed-manifest design, but it is Anvil-only, includes out-of-scope financial operations, and has incomplete final verification. It must not be activated as the MVP.
* V3 work exposed two implementation errors already corrected locally: share valuation correlation and unstable SMT serialization. Shares are now outside MVP scope. These fixes do not establish Fuji readiness.

## Module disposition

| Module | Decision | Required treatment |
|---|---|---|
| FastAPI modular composition / operator authentication | KEEP / EXTEND | Single tenant; no owner key in serving configuration |
| Planning / Task Shield / Temporal ITAG | KEEP / EXTEND | Two typed operations only; preserve semantic and deterministic vetoes |
| Portfolio / Chainlink / LFJ registry | KEEP / EXTEND | Verify exact Circle identities, both route directions, pinned pricing |
| Economic risk / Z3 / SDE / attestor | EXTEND | Receipt-backed payment credit; complete proof/evidence binding |
| Existing PolicyVault V1/V2 | KEEP | Existing immutable deployment retained; no silent address changes |
| New MVP vault and bidirectional adapter | EXTEND | Two financial operations; owner sessions, separate budgets, atomic receipts |
| Anvil simulation / extraction | KEEP / EXTEND | Same exact signed final preflight; no live fixture fallback |
| Relayer / journal / outcome monitor | FIX / EXTEND | System fee guards, actual expense ledger, conservative recovery/reorg handling |
| Demo User HMAC / wallet selection / sponsor charging | DISABLE / ARCHIVE | Preserve migration and security tests; remove default runtime activation |
| Gas credit storage | ARCHIVE | Existing records retained; no customer/sponsor billing in MVP |
| V3 deposits/redemptions/native or WAVAX payments | DISABLE | Local research code/tests retained; absent from MVP schemas and execution |
| Lending, staking, LP, bridges, arbitrary approvals/calls | DISABLE | No supported builder, API operation or on-chain execution selector |
| Frontend | EXTEND / FIX | Single treasury; two operations; public read-only status; operator-only execution |

## Affected dependencies and migration boundary

Shared SDK adds a strict MVP boundary over fixed-operation evidence; Solidity deployment changes require explicit owner migration. SQLite changes must be additive. Existing nonces, sessions, proof records, raw transaction journals and sponsor tables remain intact. Existing deployment manifests and private environment values must not be overwritten.

## Final implementation status — 21 November 2026

The two-operation boundary is implemented across the public schema, bounded planner, authorization, builder, proof, signing, API, frontend and `PolicyVaultMVP`. Shared PACE/PGS gates remain in the execution path. Payments require exact measured USDC receipt and use separate spending counters; system gas reservations share the durable broadcast journal. Demo User activation is disabled in canonical serving, while isolated compatibility tests and historical records remain.

The complete Python regression passed **586 tests with 10 skips** before final operator-startup cleanup, followed by **40 passing focused tests**; the [test report](MVP_TEST_REPORT.md) records the verification scopes. All **109 Foundry tests** passed. Both direct V1 routes executed on disposable Fuji forks. The new MVP vault and adapter have not been deployed publicly.

Read-only public verification established three distinct existing EOAs, matching deployment bytecode, exact Circle/WAVAX identities and actual balances. Funds are distributed across the EOAs and vault, rather than already available as treasury principal. The [runbook](MVP_DEMO_RUNBOOK.md) proposes funding and lists the required Owner actions; the generated migration plan is unsigned.

Remaining blockers are explicit: the old immutable vault has no secure payment entry point, its adapter is forward-only, current reverse quoter selection is outside the approved V1 route, and the pinned economic snapshot showed 9,886 bps loss against the unchanged 300 bps policy. A later economic fork case lacked fresh verified oracle evidence and was skipped. New public payment, deployment and funding are unverified. A complete payment using the configured real semantic provider confirmed on disposable local Anvil, with full receipt and zero trading-risk debit. Neither that local payment nor route-only fork execution is reported as full public Fuji authorization.

Serving the migrated MVP no longer depends on the retired vault's active session. Owner identity is read from the public manifest for serving, without parsing an Owner key. The separate frontend image uses the MVP landing page and proxies `/mvp/`; deployment/hosting smoke remains an explicit limitation.
