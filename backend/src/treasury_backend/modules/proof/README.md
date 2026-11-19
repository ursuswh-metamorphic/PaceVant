# proof

The live Circle/LFJ bridge requires direct Chainlink evidence for the exact Circle-USDC/Fuji-WAVAX addresses. `OracleEvidence.feeds` binds raw rounds, original timestamps, feed identities and configured age limits into the oracle hash; its observation timestamp remains the pinned block time. The shared engine checks per-feed age separately from the owner-bound short state/session age. A legacy controlled snapshot cannot substitute for this provenance. LFJ effect evidence records `lfj-v1-fuji-v1`, not the mock adapter label.

Adapt backend facts to the shared V2.1 proof engine.

## Interface and files

`prove(...)` in `service.py`.

Input: mandate, built transaction, simulation, snapshot, context, time and optional query sink. Output: typed proof evidence and bindings used by decision/signing. Exact Check/Compile/Phi arithmetic and Z3 logic live only in `packages/contracts-api/treasury_contracts/proof.py`.

## Development boundary

Change backend input mapping here. Changes to proof formulas, canonical hashes or signed fields belong to the shared protocol package with cross-language and contract review. UNKNOWN, timeout, invalid evidence and ineligible inputs must never become VERIFIED.

Import public functions from `treasury_backend.modules.proof` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/integration/test_proof_v2.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).
