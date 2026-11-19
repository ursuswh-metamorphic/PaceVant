# risk

Evaluate economic and policy limits for one immutable simulated attempt.

## Interface and files

`evaluate(...) -> Evaluation` in `service.py`; `Evaluation` carries the risk assessment and related facts.

Input: mandate, proposal, build, evidence, portfolio, balances, context and clock. Output: `EconomicRiskAssessment` with explicit issues. Checks include slippage, token deltas, spend, exposure and oracle provenance/freshness.

## Development boundary

Add a risk gate here and test rejection as well as safe cases. Do not mutate the decision record or sign. Proof verification is a separate prerequisite and cannot bypass these existing gates.

Import public functions from `treasury_backend.modules.risk` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_v2_gates.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).
