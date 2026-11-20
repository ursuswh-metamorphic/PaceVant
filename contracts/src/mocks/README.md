# Mock assets

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

MockUSDC/MockWAVAX and test helpers exist for controlled demo economics. They are not real stablecoins or wrapped AVAX and must not be represented as market assets. Test decimals, minting permissions and transfer behavior when extending them.

Run `uv run --locked python tools/contracts/foundry.py forge test -vv` from the repository root. See [contracts overview](../../README.md) for dependency bootstrap and protocol review.
