# decision

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

Combine alignment, simulation, risk and proof prerequisites into a security decision.

## Interface and files

`decide`, `simulation_issues` in `service.py`.

Input: the bound attempt and gate results. Output: `SecurityDecision` with APPROVE, REPLAN, REJECT or ESCALATE and reason codes. This module does not hold private keys.

## Development boundary

Add decision precedence here. Preserve fail-closed handling and binding to build/evidence/snapshot IDs. Never approve because a field is absent or because another gate happened to pass.

Import public functions from `treasury_backend.modules.decision` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_v2_gates.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).
