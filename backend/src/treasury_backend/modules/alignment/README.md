# alignment

Task Shield was ported from main into this module. `engine.py` extracts authenticated user objectives and scores candidate instructions; `state.py` persists objective revisions/audit; `runtime.py` intercepts assistant/tool calls and outputs; `provider.py` supports bounded Chat Completions/Responses requests, including Xingchi. `api.py` exposes authenticated inspection/objective endpoints. `service.py` retains deterministic wallet constraints independently of the model.

The checked-in env template explicitly disables the LLM shield pending live latency/artifact validation. `paper` and `wallet_hardened` are opt-in; errors fail closed, with no fixture fallback. A passing LLM check never grants signing authority. No LLM request occurs inside the attestor reservation transaction. The final SUBMITTING write also checks objective revision. Planner provider rotation is separate from the shield provider.

Run `uv run --locked pytest backend/tests/control/test_task_shield.py backend/tests/control/test_responses_provider.py -q`. Scripted providers verify runtime behavior, not model detection accuracy. Read [Task Shield reference](../../../../../docs/TASK_SHIELD.md) and [current merge/configuration](../../../../../docs/integrations/MAIN_SYNC_2026_11_20.md).

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
