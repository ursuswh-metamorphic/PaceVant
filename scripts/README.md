# Compatibility entrypoints

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`serve.py` now starts the canonical unified app. Standalone control/execution runners are legacy protocol adapters only. Existing Python commands in this directory delegate to `treasury_backend.operations` or `tools/` so older local workflows continue to work. New development belongs in the canonical module/tool folder. These wrappers are not a second backend implementation.

Use `uv run treasury ...` for the complete V2.1 system and `uv run python -m treasury_backend.operations.execution ...` for legacy B-only commands. `foundry.mjs` is an optional legacy developer wrapper; Python serving/deployment does not execute it.

Optional npm aliases `dev`, `local`, `dev:local`, `dev:fuji`, `demo` and `deploy:*` now target the unified backend/operator. `dev` is MOCK; `local`/`dev:local` start full LOCAL V2.1; `demo` calls an already running LOCAL API. Only explicitly prefixed `b:*` aliases retain B-only compatibility behavior. Do not use them as full-system deployment commands. `schemas`, `fixtures` and `golden` are protocol-generation tools, not backend startup paths.

See [backend](../backend/README.md), [tools](../tools/README.md) and [contributing](../CONTRIBUTING.md).
