# Swap adapters

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`LFJSwapAdapter.sol` is the live Fuji adapter for the approved Circle test USDC -> WAVAX V1 pair. It checks vault access, fixed direction/path/recipient and temporary approvals; the backend also validates route/code/quote identities. The LFJ router is distinct from this adapter address. Reverse, multihop and Liquidity Book bin routing are not implemented. Mock adapters under `../mocks/` remain explicit local/testing components, not the current LFJ live route.

Adapter/router addresses are allowlisted and signed calldata is bound. Add a new adapter with explicit vault access, token approvals, return-value/token-delta behavior and revert tests; coordinate builder, simulator, extractor and proof/registry changes. A passing mock swap does not validate an external DEX.

Run `uv run --locked python tools/contracts/foundry.py forge test -vv` from the repository root. See [contracts overview](../../README.md) for dependency bootstrap and protocol review.
