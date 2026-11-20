# portfolio

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`observations.py:PortfolioReader` now acquires native and token balances at an explicit block/hash, checks token identity/decimals, optionally compares the independent execution reader, and creates an immutable content-hashed `ObservedPortfolioSnapshot`. This observation alone never authorizes a trade. `decision_snapshot` binds it to validated prices, build, owner policy and history version; V2 Fuji uses Circle USDC/WAVAX with the existing direct Chainlink source, including reverse swaps. Faucet-token prices remain ineligible.

Portfolio history is persisted by `modules/persistence/portfolio.py` and exposed by `modules/monitoring/api.py`. Oracle observations shown for information remain distinct from the authoritative provider used for approval. Tests: `uv run --locked pytest backend/tests/control/test_portfolio_state.py -q`. [Integration and limitations](../../../../../docs/integrations/MAIN_SYNC_2026_11_20.md).

Build an economic portfolio snapshot from chain balances, verified prices and spend history.

## Interface and files

`snapshot`, `policy_issues`, `fresh` in `service.py`.

Input: mandate, on-chain context/balances, `oracle.OraclePrice`, history and clock. Output: `PortfolioSnapshot`, integer-valued economic facts and policy/freshness issues. Execution-side snapshots contain no trusted USD prices.

## Development boundary

Add portfolio calculations here with exact units and rounding rules. Preserve chain/vault scope and freshness checks. Exposure is a pre-sign check, not an atomic on-chain allocation guarantee.

Import public functions from `treasury_backend.modules.portfolio` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_workflows.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).
