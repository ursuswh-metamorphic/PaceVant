# Contract tests

Foundry suites exercise PolicyVault signatures/nonces/policy rotation, V2 atomic bounds and session/day budgets, protected rollback, directional caps, fuzz properties and the EIP-712 golden vectors. Tests use local accounts and mock assets; they send no Fuji transactions.

```sh
uv run --locked python tools/contracts/foundry.py forge test -vv
```

For any enforcement change add a case demonstrating the attack/revert and a valid execution. Keep hash vectors consistent with shared SDK/viem checks. See [contracts](../README.md).
