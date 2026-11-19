# alignment

Check that a proposal follows the goal and owner mandate before execution work.

## Interface and files

`check(mandate, proposal, goal, tool_output=...)` in `service.py`.

Input: typed mandate/proposal and untrusted goal/tool text. Output: `Alignment`, including status and reason codes. Prompt injection and ambiguous goals are explicit rejection/escalation cases.

## Development boundary

Add deterministic detectors and reason codes here. Do not call the builder or wallet. Tool output remains untrusted input; a passing check alone is insufficient for approval.

Import public functions from `treasury_backend.modules.alignment` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_workflows.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).
