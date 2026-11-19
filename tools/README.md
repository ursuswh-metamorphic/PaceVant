# Developer tools

Canonical tool locations, invoked from the repository root:

- [contracts](contracts/README.md): native Foundry wrapper, pinned OpenZeppelin bootstrap and V2 vector generation.
- [quality](quality/README.md): source secret scan and browser-module syntax checks.
- [evaluation](evaluation/README.md): scoped proof/protocol benchmarks and legacy comparison.
- [operations](operations/README.md): narrowly scoped submission recovery tool.

Application operator commands belong to `treasury_backend.operations`, exposed through `uv run treasury`. `scripts/` retains thin legacy compatibility entrypoints only. Add new tool behavior here, not in a compatibility shim.
