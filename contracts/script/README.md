# Forge scripts

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`Deploy.s.sol` is the standalone Solidity deployment helper. Canonical full V2.1 deployment uses `uv run treasury deploy --network local|fuji`, which validates owner risk parameters, creates a manifest and activates the proof policy/session through Python operators. These commands send transactions on the selected network.

Do not use a legacy helper alone as evidence that a complete V2 stack is ready. Read [demo runbook](../../docs/demo/AVALANCHE_FUJI_DEMO.md) and [contracts overview](../README.md) before changing deployment behavior. Never commit keys or broadcast artifacts.
