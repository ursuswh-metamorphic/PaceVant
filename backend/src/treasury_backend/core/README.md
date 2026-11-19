# Shared application kernel

Contains typed mandate, goal, balances/context, portfolio, risk and decision records plus `ControlError` and duplicate-key-rejecting JSON parsing. It depends only on shared protocol/libraries, never feature modules. Place feature-specific models in that feature (for example oracle prices in `modules/oracle/models.py`). Changes affect multiple modules and need compatibility review.

See [backend setup](../../../README.md), [module boundaries](../../../MODULES.md) and [environment/deployment](../../../../deploy/README.md).

```sh
uv run --locked python -m pytest backend/tests/architecture backend/tests/control backend/tests/integration -q
```

Run from the repository root. Integration tests need native Foundry. Keep routes, config, deployment composition and feature behavior in their respective folders; add regression cases for any changed security boundary.
