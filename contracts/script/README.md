# Forge scripts

`Deploy.s.sol` is the standalone Solidity deployment helper. Canonical full V2.1 deployment uses `uv run treasury deploy --network local|fuji`, which validates owner risk parameters, creates a manifest and activates the proof policy/session through Python operators. These commands send transactions on the selected network.

Do not use a legacy helper alone as evidence that a complete V2 stack is ready. Read [demo runbook](../../docs/demo/AVALANCHE_FUJI_DEMO.md) and [contracts overview](../README.md) before changing deployment behavior. Never commit keys or broadcast artifacts.
