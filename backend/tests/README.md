# Backend verification

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

Run commands from the repository root. `uv sync --locked` installs one environment. Native Foundry v1.7.1 and compiled contracts are required by chain integration tests:

```sh
uv run --locked python tools/contracts/bootstrap.py
uv run --locked python tools/contracts/foundry.py forge build
uv run --locked python -m pytest -q
uv run --locked python tools/contracts/foundry.py forge test -vv
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python tools/quality/scan_secrets.py
```

`control/` covers goal/alignment, immutable records, gate decisions, attestor revalidation and workflow recovery. `execution/` covers HTTP compatibility, exact simulation, relay journals, receipts/reorgs and independent consumers. `integration/` covers proof math/resource limits, container role separation, end-to-end local operator startup and frontend boundaries. `architecture/` checks module dependency rules. `execution/test_unified_app.py` covers one-app routes/auth, direct module injection, idempotency and no internal HTTP pool. The operator smoke also occupies the retired B port and checks that only one Uvicorn process starts.

Pytest also discovers `backend/src/treasury_backend/modules/**/tests/`: new feature-specific cases should live there. The existing suites retain broad regressions. No local test requires the user's Fuji private keys. The skipped test is the opt-in LOCAL ablation (RUN_V2_ABLATION), not a Fuji smoke test. Fuji verifier unit cases use mocked RPC. There is no automated live-Fuji smoke runner in this suite; use the manual operator runbook for a separately authorized testnet deployment.

Optional developer-only cross-language verification uses Node/viem:

```sh
npm ci --ignore-scripts
npm run test:integration
node tools/quality/check_frontend.mjs
```

These tools are not shipped in the Python backend image. Full comparative benchmark: `uv run --locked python tools/evaluation/evaluate_protocol.py`; see [evaluation tools](../../tools/evaluation/README.md).
