# Canonical V2.1 ABI and signature bindings

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](../AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](../README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

Authoritative models: `packages/contracts-api/treasury_contracts/v2.py`; Solidity: `contracts/src/PolicyVault.sol`. Golden fixture: `fixtures/v2_1/golden.json`. Regenerate with `npm run golden:v2`; test with `npm run test:integration` and Foundry `testGoldenPythonAbiAndEip712`.

EIP-712 domain: `TreasuryPolicyVault`, version **2**, actual chain ID, actual vault address. V1 keeps domain version 1 only for legacy deployments. Once V2 is activated, legacy execution is permanently rejected.

```
ApprovalV2(bytes32 intentHash,bytes32 calldataHash,bytes32 policyHash,
bytes32 evidenceRoot,bytes32 proofContextHash,bytes32 postConditionsHash,
bytes32 sessionId,uint256 riskDebitUsdE8,uint256 nonce,uint256 deadline,
address adapter,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut)
```

The above is a single line in the Solidity typehash; line breaks here are display only. `intentHash = keccak256(UTF8(intent_id))`. Adapter calldata is exactly the 4-byte exactInput selector and five standard ABI words, including `recipient=vault`. Length is exactly 164 bytes; noncanonical address padding, appended bytes, selectors and mismatched signed fields are rejected.

Phi encoding is **one struct argument**, including the outer dynamic-tuple offset:

```
abi.encode( ((address asset,int256 minDelta)[] balanceBounds,
             (address token,address spender,uint256 maxRemaining)[] allowanceCaps) )
```

Each array has exactly two entries. Balance assets sort numerically by 20-byte address, are unique and equal the owner registry's USDC/WAVAX pair. Allowances sort by `(token,spender)`; token order is the same registry and spender is the single configured adapter; cap is zero. Unsupported receipt/ownership/exposure fields do not exist in this ABI, so no ignored field can appear protected. The input lower bound is exactly `-amountIn`; the output bound is at least `minAmountOut` and is the effective runtime requirement. Deltas outside int256 magnitude are rejected before casting.

Registry commitment: `keccak256(abi.encode(uint256(1), (address,uint8)[] assets))`, sorted and exactly USDC6/WAVAX18. Decimals are read and validated on deployment/chain context.

Binding design (distinct meanings, one proof-context hash):

- PDR `evidenceRoot` retains the existing content-addressed simulation **manifest** commitment. That manifest includes the exact typed V2 effects.
- Proof artifact `evidence_root` is the **ABI effect evidence** commitment (chain/vault/intent/policy/call/block/time/registry/read arrays/flags/versions). It is included in `proofContextHash`.
- `proofContextHash` is the ABI commitment specified by `ProofArtifactV2.context_hash`: bytes32 list of source-bound artifacts/versions/verdicts/Phi/query hashes, plus uint256 certified debit and feasibility/fallback flags. It binds oracle assumptions, registry, exact call, session state and the certificate once.
- `postConditionsHash = keccak256(abi.encode(Phi))` separately lets the vault enforce exactly the signed executable conditions. It is not an arbitrary remappable database ID.
- `activePolicyHash` preserves V1's monotonically versioned owner configuration. In V2 it additionally commits to `v2ConfigHash`, proof adapter, fixed registry, vault and chain. Changing policy/signing configuration invalidates old sessions and approvals; global/day counters persist.

Python, viem and Foundry test the same bytes and digest. Tests alter all 15 approval fields, Phi, calldata, chain/domain, replay and owner configuration. Diagnostic JSON, display labels, signature IDs and timing measurements are not security hashing inputs.
