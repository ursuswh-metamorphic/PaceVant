# portfolio

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
