# Solidity contracts

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`PolicyVault` is the final enforcement boundary for signed swaps. Python authorizes and relays; Solidity executes on Avalanche/EVM after one explicit deployment. Hosting the backend does not deploy the contracts automatically.

- [src](src/README.md): vault enforcement and contract interfaces/adapters/mocks.
- [test](test/README.md): Foundry security, fuzz, rollback and hash-vector tests.
- [script](script/README.md): standalone Forge deployment helper; full V2 deployment is composed by Python operators.

```sh
uv sync --locked
uv run --locked python tools/contracts/bootstrap.py
uv run --locked python tools/contracts/foundry.py forge build
uv run --locked python tools/contracts/foundry.py forge test -vv
```

Native Forge resolves solc during build. `foundry.toml` pins compiler settings/remappings. The bootstrap downloads checksum-pinned OpenZeppelin source into ignored lib/. Docker compiles during its build stage; runtime keeps compiled artifacts and Anvil for forks, with no compiler required for API serving.

Signed fields, ABI, policy/session counters, nonce handling and rounding changes must be reviewed together with the shared SDK, proof engine, backend and V1/V2 golden vectors. A source or ABI update cannot upgrade existing immutable deployed code. V2 activation permanently disables V1 execution for that vault; use an explicit new deployment/owner policy flow.
