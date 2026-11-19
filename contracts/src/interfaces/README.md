# Contract interfaces

Shared Solidity adapter/token call boundaries. Keep signatures synchronized with implementations, Python ABI consumers and SDK exports. A change is a protocol review item and needs compile, Forge and golden-vector verification.

Run `uv run --locked python tools/contracts/foundry.py forge test -vv` from the repository root. See [contracts overview](../../README.md) for dependency bootstrap and protocol review.
