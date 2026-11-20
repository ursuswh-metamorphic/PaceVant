# Contract tooling

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`bootstrap.py` downloads a pinned OpenZeppelin archive, verifies its SHA256 and installs source under ignored lib/. `foundry.py` resolves native Forge/Anvil binaries without invoking Node. `generate_v2_vectors.py` generates shared V2 approval/proof fixtures; review all resulting fixture/ABI changes.

```sh
uv run --locked python tools/contracts/bootstrap.py
uv run --locked python tools/contracts/foundry.py forge build
uv run --locked python tools/contracts/foundry.py forge test -vv
```

Install native Foundry v1.7.1 for local work. Existing development installations may provide native binaries under node_modules; executing those binaries still does not start Node. The root Dockerfile uses native release binaries and excludes node_modules.
