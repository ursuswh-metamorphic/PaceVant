# DEX integrations

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`lfj.py` supports exactly two explicitly selected Fuji token identities: legacy LFJ faucet USDC and Circle test USDC, both against Fuji WAVAX. The default client preserves legacy diagnostics; the owner-approved live demo explicitly selects Circle. Every builder/simulator client uses the manifest token address. A different asset is rejected, even when symbol/decimals match.

`v1_route` verifies router/quoter/factory/pair/token/code identities at a block. `verified_quote` requires the quoter-selected best route to remain the single supported V1 pair, and independently recomputes the V1 997/1000 reserve quote. Quotes commit to a block hash. The Solidity LFJSwapAdapter supports only the verified one-direction exact-input call, vault recipient and temporary approvals; reverse/multihop/LB-bin routing is not implemented.

A DEX quote is never the USD oracle. Only the Circle route with reviewed direct Chainlink evidence can reach live signing/relaying. The faucet route remains blocked at asset valuation. Stress is implemented by the simulation module on Anvil, not by changing DEX quotes in live execution.

See [live runbook](../../../../../../docs/demo/FUJI_LIVE_END_TO_END.md), [Solidity adapter](../../../../../../contracts/src/adapters/LFJSwapAdapter.sol) and [execution module](../README.md).
