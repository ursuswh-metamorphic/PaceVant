# workflows

Orchestrate use cases across business modules and the execution client port.

## Interface and files

`ControlPlane` in `service.py` is the facade. `evaluation.py` owns attempts/gates; `authorization.py` owns bound approval, revalidation and submission; `monitoring.py` owns receipt reconciliation, recovery and expiry.

Input: authenticated API commands, immutable IDs, settings and injected clock. Output: persisted workflow state and query views. `context.py` defines the approved-attempt context. `client.py` provides VerifiedExecutionClient, which verifies authoritative chain facts. The canonical app injects an in-process SDK adapter; RestExecutionClient remains for legacy HTTP consumers, `evidence.py` verifies artifacts, `fuji.py` independently verifies chain facts, `mock.py` is the test adapter.

## Development boundary

Add a use case in its phase file. Keep math, SQL, signature encoding and transaction building in their owning modules. Mixins compose the facade without importing it back, avoiding circular imports. SUBMITTED is not CONFIRMED; ambiguous submission must reconcile rather than blindly resend.

Import public functions from `treasury_backend.modules.workflows` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_workflows.py backend/tests/integration/test_execution_wire.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).

Submission recovery is exposed through the operator-authenticated POST /v1/workflows/{id}/recover endpoint. It binds an existing SUBMITTING workflow to a known execution tx hash, verifies its identity and reconciles the receipt without signing/resending. The CLI helper calls the running unified API; see tools/operations/README.md.
