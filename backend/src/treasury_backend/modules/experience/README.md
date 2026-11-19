# experience

Suggest a smaller next amount after a failed economic attempt.

## Interface and files

`next_amount(store, workflow_id, current_amount)` in `service.py`.

Input: persisted workflow history and current base-unit amount. Output: a bounded revised amount or None. This is deterministic retry guidance, not a learned model.

## Development boundary

Add retry heuristics here. Every new proposal needs a new build/simulation and all gates again. Never reuse a previous approval or lower a policy limit to make a retry pass.

Import public functions from `treasury_backend.modules.experience` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_workflows.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).
