# workflows

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

The coordinator now owns a `TaskShield` runtime per active workflow (when enabled) and composes a read-only `modules.monitoring.OutcomeMonitor`. `evaluation.py` persists block-hashed pre-observations, optional shield proof and the existing V2 proof; `authorization.py` revalidates each, then checks the final execute call; `monitoring.py` handles workflow-facing recovery/detail queries. A known transaction hash is stored before any post-broadcast shield check, so a provider failure cannot trigger a replacement transaction. The underlying V2 attestor and on-chain gates remain mandatory. [Main integration details](../../../../../docs/integrations/MAIN_SYNC_2026_11_20.md).

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

Current security hardening: live composition rejects fixture clients and missing execution transports. Approval deadlines are bounded by session expiry. After guarded preflight the authorization pipeline rereads latest Chainlink rounds and verifies current Fuji head/fork/drift before signing/submission; stale/mismatched evidence never receives an automatic replacement signature. Current demo session is 24h, drift 200 blocks, with independent approval/snapshot age 300s. See [the system review](../../../../../docs/audit/SYSTEM_SECURITY_REAL_DATA_REVIEW.md).
