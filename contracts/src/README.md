# Vault source

`PolicyVault.sol` verifies domain-bound EIP-712 approvals, router/token allowlists, nonce/deadline and exact calldata, then enforces atomic token delta/Phi bounds and certified session/global/day risk debit for V2. Any failed condition rolls back the swap and accounting together. V1 remains for compatibility only until permanent V2 activation.

Adapter interfaces isolate external swap behavior. Current deployments use mock adapters/tokens; a production DEX adapter is not implemented. Do not assume a passing mock swap validates an external DEX integration.

See [contracts setup/review rules](../README.md), [proof assumptions](../../docs/security/proof_assumptions_v2_1.md) and [coverage](../../docs/security/policy_coverage_v2_1.md).
