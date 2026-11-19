# monitoring

Read-only reconciliation of durable workflow submissions. `service.py:OutcomeMonitor` polls receipt/build/PDR facts through an injected read client. `worker.py:start_monitor` runs it in the unified FastAPI lifespan; `api.py` provides authenticated portfolio/outcome history routes.

`tick` bootstraps jobs from existing durable submissions, claims a SQLite lease, reads chain facts, reconciles pre/post observations and commits a projection. Missing RPC data stays PENDING/UNAVAILABLE; a reorg invalidates the affected projection and schedules another read. The worker never signs, executes, renews a session or rebroadcasts. Gas is a relayer expense, deduplicated by canonical transaction rather than poll count. Unexplained balance deltas are reported, not called profit.

Persistence belongs to `modules/persistence/portfolio.py`; block-pinned observations belong to `modules/portfolio`; pure V1/V2 receipt checks belong to `packages/contracts-api/treasury_contracts/outcomes*.py`. The monitor does not import workflow or execution implementations. Fixture clients advertise `fixture_mode` only in explicitly MOCK tests.

Optional key-free process composition is in `operations/observer.py` and `operations/observe.py`. It can target the unified backend under `/execution`; a second server is not required for normal operation.

Run `uv run --locked pytest backend/tests/control/test_portfolio_state.py backend/tests/execution/test_outcome_reconciliation.py backend/tests/execution/test_v2_execution.py -q`. Execution tests require native Foundry and use isolated Anvil, not public broadcasts. See [current integration report](../../../../../docs/integrations/MAIN_SYNC_2026_11_20.md).
