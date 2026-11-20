# Vault source

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`PolicyVault.sol` verifies domain-bound EIP-712 approvals, router/token allowlists, nonce/deadline and exact calldata, then enforces atomic token delta/Phi bounds and certified session/global/day risk debit for V2. Any failed condition rolls back the swap and accounting together. V1 remains for compatibility only until permanent V2 activation.

Adapter interfaces isolate external swap behavior. The current Fuji profile uses `adapters/LFJSwapAdapter.sol` against an allowlisted real LFJ V1 pair for Circle test USDC -> Fuji WAVAX. Local tests also use mock tokens/adapters. The live adapter is one-direction, single-pair and vault-recipient only; it is not a general production DEX integration or mainnet audit. See the current design for deployed addresses and receipt scope.

See [contracts setup/review rules](../README.md), [proof assumptions](../../docs/security/proof_assumptions_v2_1.md) and [coverage](../../docs/security/policy_coverage_v2_1.md).
