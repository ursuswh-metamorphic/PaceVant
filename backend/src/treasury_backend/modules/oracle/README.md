# Oracle

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`chainlink.py` is the live Fuji provider. It reads the two allowlisted contract feeds directly at the simulation block, checks exact metadata, positive/completed rounds, original timestamps and pinned block/hash, then returns `OraclePrice` with `FeedObservation` provenance. It does not approve transactions. Workflow composition selects it from the owner-approved source hash, not from a file's claimed source name.

The shared policy in `treasury_contracts/oracle.py` maps Circle test USDC to USDC/USD (86400-second age) and Fuji WAVAX to AVAX/USD (600 seconds). Its canonical configuration hash is committed by the owner proof policy. These are **testnet reference USD valuations**, not redeemable/mainnet prices for the test assets. Every original round is included in the oracle evidence hash. `price_timestamp` retains the oldest updatedAt; `oracle_observed_at` is the pinned block time. Block/session freshness remains a separate bounded policy.

`service.py` retains `JsonFilePriceProvider` for explicit controlled demos/external writers using `TRUSTED_TEST_ORACLE`. It refuses JSON claiming to be direct Chainlink evidence. `demo.py` is still a configured nominal-price producer for MOCK/LOCAL, never the live Circle/LFJ workflow. Live serving does not run a redundant oracle file heartbeat; consumers read RPC directly. `refresh_oracle` writes an audit snapshot during prepare without changing feed updatedAt.

`fuji/` is the authenticated reference-only Observatory, including Chainlink/Witnet/Pyth and optional CoinGecko reads. It is separate from the authoritative provider used in proof/signing; an Observatory observation alone cannot authorize a swap. LFJ faucet USDC remains unpriced and blocked.

Regression coverage: `tests/` controlled source contract; `backend/tests/control/test_chainlink_live.py` provenance, age, metadata and hash tampering; optional `backend/tests/execution/test_circle_fuji_fork.py` full Circle/Chainlink/LFJ workflow on Anvil with disposable wallets and no public writes.

See [live Fuji runbook](../../../../../docs/demo/FUJI_LIVE_END_TO_END.md), [source policy](../../../../../packages/contracts-api/treasury_contracts/oracle.py), and [module boundaries](../../../../MODULES.md).
