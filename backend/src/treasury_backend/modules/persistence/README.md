# persistence

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`portfolio.py` adds idempotent SQLite tables for immutable observed snapshots/events/links, per-treasury history versions, monitor jobs/leases, outcome observations and replaceable current projections. Existing workflows, proof records and attestations stay intact. Gas accounting uses canonical outcome projections with deduplicated legacy-event fallback. Reorgs invalidate observations instead of rewriting history. Objective revision is checked in the same write transaction that transitions an attestation from ATTESTED to SUBMITTING; Task Shield owns its additive `shield_*` tables.

Persist control workflows, attempts, decisions, proof records, spend reservations and audit history.

## Interface and files

`Store` and `dump` in `service.py`.

Input: validated application records. Output: SQLite rows and typed/serialized records consumed by workflows and signing. Decisions/attempt evidence are immutable; schema upgrades are additive and idempotent.

## Development boundary

Add schema migrations and repository methods here. Callers must not write SQL into HTTP handlers. Back up the database consistently with execution journals; current deployment supports one service instance.

Import public functions from `treasury_backend.modules.persistence` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_v2_gates.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).

Signer quarantine counts the latest terminal outcome per distinct attestation. Reorg reconfirmation of one reverted transaction must not count as a second protected revert. Focused regression: `uv run python -m pytest backend/src/treasury_backend/modules/persistence/tests/test_quarantine.py -q`.
