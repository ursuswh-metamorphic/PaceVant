# alignment

Task Shield was ported from main into this module. `engine.py` extracts authenticated user objectives and scores candidate instructions; `state.py` persists objective revisions/audit; `runtime.py` intercepts assistant/tool calls and outputs; `provider.py` supports bounded Chat Completions/Responses requests, including Xingchi. `api.py` exposes authenticated inspection/objective endpoints. `service.py` retains deterministic wallet constraints independently of the model.

The Fuji demo env template enables `wallet_pipeline` with official DeepSeek Flash, then Groq/Gemini/Xingchi fallback. Provider requests have bounded deadlines; actual provider/model/status/latency are audited. `paper` and `wallet_hardened` retain individual tool interception. `wallet_pipeline` inspects authenticated objectives/proposals/build arguments, batches fixed read/build/fork outputs before SDE/signing, and separately checks the execute call. Uninspected or malicious evidence cannot authorize signing; unavailable providers fail closed without fixture fallback. A passing LLM check never grants signing authority. No LLM request occurs inside the attestor reservation transaction. Final SUBMITTING also checks objective revision. Planner rotation has separate quotas/cache.

`serialization.py` defines the explicit semantic view of EVM data: complete natural-language strings and unknown trace keys remain visible, opaque machine bytes carry length/hash, and the full raw artifact remains subject to SDK/proof/effects verification. No trailing text truncation is allowed. Runtime output budget is configurable up to 65536 characters. This operational mode is not a paper benchmark reproduction. See [current Fuji runbook](../../../../../docs/demo/FUJI_ITAG_LIVE.md) for exact configuration, data sources and evidence scope.

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
