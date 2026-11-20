# Local PGS reference audit

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](../AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](../README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

Read-only reference commit `f8fca9341407e1bca2d4d9f7eeda0319e132bcad`. Local `LICENSE`: Apache-2.0. No code blocks copied. Independent integer/rational implementation of the method; no dependency on this folder at runtime or CI.

| Reference | Studied behavior | Adaptation |
|---|---|---|
| `pgs/guard.py`: Policy/prove/check | fixed simulated deltas, negated value clause, inflow tolerance, fallback zero tolerance | shared `treasury_contracts/proof.py`; exact USDC6/WAVAX18, independent assumptions SAT, monotonic lower-bound proof, certified debit |
| `pgs/chain.py` | isolated simulation and balance/allowance reads | preserve existing Anvil fork runner and guarded vault entrypoint |
| `contracts/Testbed.sol` | atomic checked execution; also exposes unchecked wallet | preserve PolicyVault authorization; unchecked path NEVER ported |
| `tests/test_api.py`, `pgs/scenarios.py`, `eval/` | controlled drift experiments | project-specific Foundry/pytest tests; no upstream percentages reused |

Upstream uses E18 normalization, floating policy inputs and realized session loss. This project uses exact base-unit normalization, USD-e8 and on-chain certified worst-case reservations. These are deliberate adaptations. Testbed is local Hardhat, custody incomplete; not a Fuji deployment or audit. Proof assumes trusted token semantics, complete registry, truthful price domain and correct wallet enforcement. It does not prove exposure, oracle honesty, gas expense, or universal MEV prevention.

Paper source checked: https://arxiv.org/abs/2610.00354 (method context only). Local source is the implementation reference. PGS remains local, ignored, and absent from root Git index.
