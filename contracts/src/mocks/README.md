# Mock assets

MockUSDC/MockWAVAX and test helpers exist for controlled demo economics. They are not real stablecoins or wrapped AVAX and must not be represented as market assets. Test decimals, minting permissions and transfer behavior when extending them.

Run `uv run --locked python tools/contracts/foundry.py forge test -vv` from the repository root. See [contracts overview](../../README.md) for dependency bootstrap and protocol review.
