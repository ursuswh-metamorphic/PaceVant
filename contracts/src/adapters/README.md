# Swap adapters

Current mock adapter provides deterministic swaps for local/Fuji demonstration. Adapter/router addresses are allowlisted and signed calldata is bound. Add a new adapter with explicit vault access, token approvals, return-value/token-delta behavior and revert tests; coordinate builder, simulator and extractor changes.

Run `uv run --locked python tools/contracts/foundry.py forge test -vv` from the repository root. See [contracts overview](../../README.md) for dependency bootstrap and protocol review.
