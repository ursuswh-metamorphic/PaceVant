# signing

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

Live Fuji revalidation supplies the owner-configured on-chain TTL (1–300 seconds; current profile 300) together with the verified proof/session. LOCAL defaults to 30. The signer checks the immutable decision and exact build deadline against that verified window after final Phi preflight. It does not invent a new deadline or authorize from unverified API/file prices. Demo User gas credit is a separate relayer budget check; it never bypasses signing or changes treasury risk budgets.

Issue a typed approval only for a persisted, bound, revalidated approved decision.

## Interface and files

`Attestor` in `service.py`; digest/signature helpers in `typed.py`.

Input: immutable approved records and live context; private attestor key is injected during control composition. Output: signed PDR V1/V2 with chain/vault/domain binding. This key is distinct from the owner and relayer keys.

## Development boundary

Keep signing rules here. Do not expose a generic sign-arbitrary-bytes endpoint. The workflow authorization pipeline rechecks state immediately before calling this module; replay protection and persisted decisions remain required.

Import public functions from `treasury_backend.modules.signing` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_v2_gates.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).
