# Python backend

New public adapter: `api/judge.py` + bounded `modules/workflows/judge.py`, native entrypoint `operations/judge_serve.py`. It uses fixed anonymous fork presets and the existing PACE/PGS workflow with temporary fork-only roles, not public signer keys. Authenticated `/mvp` remains separate. See [native deployment](../VPS_DEPLOYMENT.md).

Current scope: [two-operation single-tenant MVP](../MVP_FINAL_ARCHITECTURE.md). Canonical composition exposes `/mvp/...`, serves the MVP dashboard, retires environment-based Demo User activation, and uses system-paid Relayer expense accounting. The optional new execution port requires an Owner-signed manifest; existing Fuji deployment files remain unchanged. See the [MVP runbook](../MVP_DEMO_RUNBOOK.md). Earlier component/checkpoint descriptions below retain compatibility context.

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

Current full-system reference: [V2.1 system design](../docs/AI_Treasury_Security_System_Design_v2.1.md), [reviewer guide](../docs/REVIEWER_GUIDE.md), [one-click Demo User runbook](../docs/demo/DEMO_USER_GAS_CREDIT.md). Earlier integration/audit reports retain checkpoint scope and do not certify current readiness.

One Python 3.12 distribution, `pacevant-backend`, import namespace `treasury_backend`. One root `pyproject.toml`, `uv.lock`, `.venv` and **one FastAPI/Uvicorn application** for workflow and execution modules. No Node.js backend process.

## Setup and run

From repository root, with Python 3.12, uv and native Foundry v1.7.1:

```sh
uv sync --locked
uv run --locked python tools/contracts/bootstrap.py
uv run --locked treasury init-env
uv run --locked treasury local --once
```

The final command creates a local chain, compiles/deploys mocks, runs one backend API, proves/signs/submits a workflow, confirms its receipt and stops owned processes. `treasury local` keeps the dashboard at port 8000. `init-env` preserves existing wallet values; generating a missing attestor requires `--generate-attestor`.

UI work without chain tools: `uv run --locked python -m treasury_backend.api.serve` (MOCK by default). Full LOCAL/FUJI configuration is composed by the operator CLI. [Fuji demo](../docs/demo/AVALANCHE_FUJI_DEMO.md) covers explicit testnet transactions.

## Layout

- `src/treasury_backend/modules/`: business capabilities, each with README/public interface.
- `core/`: application DTOs, errors, strict JSON; `config/`: validated settings.
- `api/app.py`: canonical app factory, one lifespan, dependency injection and execution router registration.
- `api/local_execution.py`: direct module adapter reusing SDK validation, with no internal HTTP connection.
- `operations/`: env/profile/deploy/process composition and CLI.
- `tests/`: control, execution, integration and architecture regressions. Feature-specific tests can be colocated in `modules/**/tests/`.

Execution exposes `ExecutionService` over its builder/simulator/relayer/storage. Workflow depends on its client port; the API composition injects the local adapter. Chain facts, evidence hashes, proof/revalidation, final preflight and durable idempotency are still verified. See [MODULES.md](MODULES.md) and [single-app architecture](../docs/architecture/UNIFIED_BACKEND.md).

## Routes and keys

Workflow/treasury routes retain `/v1/...`, `/v2/...`; execution routes are `/execution/v1/...` and `/execution/v2/...`. One Swagger at `/docs`. `X-API-Key` protects execution routes; operator/internal bearer credentials retain separate privileges. Internal module calls do not need an HTTP token hop.

Attestor and relayer keys now share one process. The owner private key remains outside serving environments. Keep one instance/worker with durable SQLite/proof/journal storage. `B_API_KEY` is retained for execution endpoint auth; the old B URL/token/port are only compatibility settings and are not needed by the canonical runtime.

## Deployment and verification

The root Dockerfile compiles Solidity during build, then runs Python plus native Anvil for isolated fork simulations. Runtime does not need Forge/solc/Node/npm. Frontend can deploy separately; set `PACEVANT_SERVE_FRONTEND=false` and an explicit CORS allowlist if origins differ. [Deploy](../deploy/README.md), [Render/VPS](../docs/deployment/PYTHON_BACKEND_RENDER_VPS.md), [tests](tests/README.md).

Standalone control/execution factories/CLIs are retained for legacy consumer tests; default operator/container startup uses only `api.app:create_app`. Do not use the legacy two-server guide to deploy the current backend.
