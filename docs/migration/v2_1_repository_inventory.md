# Repository inventory (2026-11-19)

Baseline commit: `1b09bd8dd04fd74868f30634abeec93276522d36`, branch `feat/pgs-implement-paper`.
Initial user files: untracked implementation plan and local PGS reference. No tracked edits.

| Component | Actual implementation / tests | Baseline status |
|---|---|---|
| Owner mandate | `apps/control-plane/app/models.py`, `portfolio`, `contracts/src/PolicyVault.sol`; workflow/Foundry tests | IMPLEMENTED_TESTED |
| Planner/alignment | `apps/control-plane/app/planner`, `alignment`; `tests/test_workflows.py` injection/exposure | IMPLEMENTED_TESTED |
| Builder | `apps/execution-plane/app/transaction/builder.py`; integration/wire tests | IMPLEMENTED_TESTED |
| Simulation | `apps/execution-plane/app/simulation/runner.py`; isolated pinned Anvil fork, storage-only test attestor override, fixed reserve stresses | IMPLEMENTED_TESTED |
| Evidence | `apps/execution-plane/app/evidence/extractor.py`, `treasury_contracts/client.py`; balance reads baseline, supplemental logs/traces | IMPLEMENTED_TESTED |
| Risk | `apps/control-plane/app/economic_risk`; exact integer exposure/fees; no formal loss policy | PARTIAL |
| SDE/attestor | `apps/control-plane/app/sde`, `attestor`, orchestration `_verify_approval`; SQLite immutable decisions + nonce reservation | IMPLEMENTED_TESTED |
| Vault/adapter | `contracts/src/PolicyVault.sol`, `adapters/MockSwapAdapter.sol`; 27 baseline Foundry tests | IMPLEMENTED_TESTED |
| Monitor/store/UI | `execution/relayer.py`, control `storage`, orchestration `_reconcile`, `apps/dashboard`; logs used for receipt deltas | PARTIAL (receipt finality/reorg gap) |
| Shared API | `packages/contracts-api/treasury_contracts`, generated schemas, Python/viem golden | IMPLEMENTED_TESTED |
| Proof/Phi/session risk | absent at baseline | MISSING |
| Reverse swap | absent at baseline; vault and builder forward only | MISSING |
| CI/deploy | `.github/workflows`, `app/cli.py`, `contracts/script/Deploy.s.sol`, Foundry 1.7.1, solc 0.8.38 via IR, Python/uv | IMPLEMENTED_TESTED locally; Fuji UNKNOWN |

Baseline commands (before runtime edits): `npm run check`: 27 Foundry + 38 execution Python passed, viem golden PASS, secret scan PASS. `uv run --locked python -m pytest -q`: 33 passed. No baseline failures; two deprecation warnings per Python environment. Existing tests cover normal/minOut rollback/replay/700+200+200/day/exposure rejection. No baseline performance or live Fuji assertions.

Insertion points: shared V2 wire/ABI + pure proof module; existing simulator emits complete effects; existing SDE and attestor require/revalidate proof when mandate/deployment is V2; existing vault activates V2 permanently and disables V1 entrypoint; existing relayer submits immutable Phi. V1 deployments retain their versioned ABI/domain.

The separately named V2.1 design document is not present; supplied implementation plan is the target specification. No assumed backend replacement or second executor.
