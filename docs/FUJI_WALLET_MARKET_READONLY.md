# Fuji Wallet + Portfolio Reader + Real Oracle/Market Reference

**Scope: Avalanche Fuji testnet ONLY (chain ID 43113).**
No mainnet endpoints, mainnet deployments, real funds, signing, swaps, private-key collection, or PDR attestations are performed by this feature.

## What was added

- `GET /v1/fuji/wallet/{address}` on the **Control Plane A** in `PACEVANT_MODE=FUJI`; requires existing Bearer operator token.
- `/fuji-wallet`: small wallet-observability page. Connect an injected Core/MetaMask account on Fuji (read address only) **or** paste any public EOA/PolicyVault address. Browser never calls signing or transaction methods.
- `scripts/fuji_wallet_read.py`: standalone read-only CLI usable without running the full A/B workflow.
- `apps/control-plane/app/fuji_data.py`: pin RPC reads to a single Fuji block, check chain ID 43113 and block freshness, get native AVAX plus explicitly identified Fuji USDC/WAVAX ERC-20 balances, verify token decimals/code, and query the Fuji Witnet AVAX/USD price router.
- Optional CoinGecko Demo API: live off-chain AVAX/USD market reference with price timestamp and freshness status. It is not an on-chain oracle.

## Commands

Use the project's existing setup (Python 3.12, `uv sync --locked` at root).

**Read any public Fuji address immediately (no private keys or B service):**

```powershell
uv run --locked python scripts/fuji_wallet_read.py 0xYOUR_PUBLIC_FUJI_ADDRESS
```

To use the protected web UI, configure the existing **FUJI** A + B services as described in `docs/B_HANDOFF.md`; authenticate as operator and open:

```
http://127.0.0.1:8000/fuji-wallet
```

The UI requires a Bearer operator token to read the backend API. The token stays only in the current page's input field (not localStorage or URL), and is sent only to the same-origin backend. Do not expose the demo Control Plane publicly.

Optional market feed:

```powershell
$env:PACEVANT_COINGECKO_DEMO_KEY = "YOUR_DEMO_API_KEY"
uv run --locked python scripts/fuji_wallet_read.py 0xYOUR_PUBLIC_FUJI_ADDRESS
```

Do not commit API keys. If no key is set, market source displays `NOT_CONFIGURED`; a network error gives `UNAVAILABLE`; no fallback prices are invented.

## Exact data sources & identifiers

| Item | Network/source |
|---|---|
| C-Chain RPC | `https://api.avax-test.network/ext/bc/C/rpc` |
| Chain ID | `43113` required |
| Fuji Circle test USDC | `0x5425890298aed601595a70AB815c96711a31Bc65` |
| Fuji WAVAX | `0xd00ae08403B9bbb9124bB305C09058E32C39A48c` |
| Witnet Price Router on Fuji | `0x1111AbA2164AcdC6D291b08DfB374280035E1111` |
| Witnet pair | `Price-AVAX/USD-6` (bytes32 keccak ID) |
| CoinGecko (optional) | Demo API `/simple/price?ids=avalanche-2&vs_currencies=usd&include_last_updated_at=true` |

Sources:
- https://support.avax.network/en/articles/6224787-how-to-connect-to-the-fuji-testnet
- https://build.avax.network/academy/blockchain/x402-payment-infrastructure/04-x402-on-avalanche/02-network-setup
- https://docs.witnet.io/smart-contracts/witnet-data-feeds/addresses/avalanche-price-feeds
- https://docs.witnet.io/smart-contracts/witnet-data-feeds/price-feeds-registry
- https://docs.witnet.io/smart-contracts/witnet-data-feeds/api-reference
- https://www.coingecko.com/learn/stream-real-time-crypto-prices-python

## Trust and valuation boundaries

1. Wallet/token balances are real `eth_getBalance` and `balanceOf` reads at one pinned block, **not mocked**, with chain/decimals/code checks.
2. The Witnet router provides **real on-chain oracle observations**, but the published Fuji AVAX/USD feed has a **24h heartbeat** and can be stale. Display freshness threshold (30h) is **not** acceptable as a transaction risk threshold. If oracle has not updated in a long time, UI shows `STALE`; errors show `UNAVAILABLE`.
3. CoinGecko is **off-chain market data**. Do not substitute its quote for an on-chain verified oracle or a DEX execution price. It's only a reference.
4. Testnet USDC has no guaranteed redemption/peg for our risk model; mock USDC from PolicyVault is a **different token contract**. `price_usd_e8` from AVAX is **not** enough to calculate or authorize a correct USD portfolio valuation.
5. This change does **not** alter `EconomicRiskEvaluator`, `SDE`, `Attestor`, `PolicyVault.sol`, or their existing sources/permission semantics. Specifically, it **does not** feed live observations into APPROVE/PDR. This is intentional: first validate reliable market/oracle feeds for both assets and compatible fork/execution state.
6. `getWallet` requests must be rate limited and authenticated as already provided by operator token. Public endpoint must not be exposed without extra auth and throttling.

## Tests / evidence

```powershell
uv run --locked python -m pytest apps/control-plane/tests/test_fuji_data.py -q
npm run test:ab
```

Tests mock the **HTTP transport**, not price logic, for deterministic assertions. They cover pinned chain reads, returned balances, price timestamps, stale/bad status, mainnet chain rejection, invalid wallet address, and forbidden transaction methods.

**Verification not yet performed here:** This authoring environment has no direct network route to the Fuji RPC; run CLI on your machine, capture output/receipt independently, and mark live read as `UNVERIFIED` until observed. This feature never submits a transaction, so there is no new Fuji transaction hash.

## Next steps to bring this into the agent workflow safely

- Add a vetted on-chain USD price feed or validated oracle route for **each permitted asset** and check staleness appropriately for each feed.
- Decide whether the PoC will use **Circle test USDC** or **your deployed MockUSDC** and use the **same token addresses** throughout wallet reader, quote builder, simulation, PDR, Vault and portfolio reader.
- Bind wallet snapshot `block_hash` and oracle observation reference to the risk decision, with recheck before signing.
- Keep an explicit hard failure when assets lack adequate pricing/price source freshness; do not set test USDC automatically to $1 in the authorization path.
- Optional: extend the Reader to include PolicyVault's owner, active mandate hash, allowances and daily spend via ABI, and an indexed transaction history.
