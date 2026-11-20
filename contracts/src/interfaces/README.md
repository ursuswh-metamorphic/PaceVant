# Contract interfaces

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

Shared Solidity adapter/token call boundaries. Keep signatures synchronized with implementations, Python ABI consumers and SDK exports. A change is a protocol review item and needs compile, Forge and golden-vector verification.

Run `uv run --locked python tools/contracts/foundry.py forge test -vv` from the repository root. See [contracts overview](../../README.md) for dependency bootstrap and protocol review.
