# V2.1 local use and explicit Fuji cutover

**Current operator entrypoint:** [complete local/Fuji demo runbook](../demo/AVALANCHE_FUJI_DEMO.md). The `treasury:*` commands automate the deployment-derived mandate, controlled oracle heartbeat, separated service environments and real A/B workflow described below. See [environment status](../demo/ENVIRONMENT_STATUS.md) for missing owner inputs. Manual commands below remain useful for low-level integration; use isolated manifests/data directories.

Install existing pinned dependencies and run checks:

```powershell
npm ci --ignore-scripts
npm run setup
uv sync --locked
npm run check
uv run --locked python -m pytest -q
```

For a new **local-only** V2 deployment, start Anvil with `npm run anvil`, then use an isolated `.env` profile/deployment path to preserve any existing V1 test deployment:

```powershell
uv run --directory apps/execution-plane python -m app.cli deploy-local --v2-config ../../fixtures/v2_1/TEST_ONLY_policy.json
```

The explicit file is mandatory to activate V2; normal V1 commands retain V1 behavior. The CLI creates a new ordinary immutable vault, configures proof policy, creates an owner-bound session and records actual session transaction/block in the deployment manifest. Local ephemeral keys remain under ignored execution data, and no secret is printed. For a different config path, it is resolved relative to the command's working directory (`apps/execution-plane` when using the above uv command).

Read `/v1/chain/context` from B, then update A's owner mandate with the actual new chain/vault/policy fields plus `proof_policy`, `registry` and `session_id`. All three must match independently verified chain state; missing or partial V2 config yields NO SIGN. Preserve existing owner exposure, daily spend, gas, TTL, stress and replan settings. Configure A's controlled oracle file with `TRUSTED_TEST_ORACLE`, the actual chain/vault, positive USD-e8 prices and a fresh timestamp. Follow the existing A/B credential runbook; owner, attestor and relayer must differ.

Open A's `/` dashboard. MOCK needs no credential; LOCAL/FUJI require the existing operator API credential, held only in tab memory. No key or token is embedded in assets or localStorage. Goals support `Buy WAVAX with 200 USDC` and, when the owner enables the reverse cap, `Sell 1 WAVAX for USDC`. Static assets reveal no treasury data; APIs retain auth and the signer endpoint requires its separate internal credential. Proof introspection and chain-authoritative session reads are authenticated:

```
GET /v2/proofs/{proof_context_hash}
GET /v2/treasury/sessions/{owner_session_id}
```

The final-Phi simulation endpoint on B is service-authenticated and rate-limited. It only executes an isolated fork with a labelled ephemeral test attestor; it cannot issue a production signature. B's existing execution endpoint accepts a versioned ApprovalV2/Phi object and rejects a PDR version incompatible with the deployed vault.

Monitor receipts with canonical block hash and `B_REQUIRED_CONFIRMATIONS` (default 1 for this test system; set explicitly for Fuji). Unknown receipts remain pending. The workflow revalidates terminal receipts on reads and holds an in-flight reservation during reorg reconciliation. Two consecutive protected reverts under the same policy quarantine further local attestation; owner review and a new policy commitment are required to clear that policy's quarantine. Do not blindly rebroadcast a newly signed trade when the old outcome is unknown; the existing raw-transaction journal rebroadcasts identical bytes only.

Database migration is idempotent and additive: existing workflows/decisions/attestations are retained; immutable `proof_artifacts` and `compiled_postconditions` tables are created. Query bodies live in hashed `.smt2` files beside the database. Session accounting is read from chain, not maintained as a competing SQL balance. To roll back application code, restore the prior application build against its **V1 deployment/profile** and keep the additive tables/files for audit. V2 activation cannot be rolled back on-chain; an old V1 executor cannot be re-enabled. No historical data or policy/session counters are cleared by migration.

Current Fuji status: **CONFIGURATION_READY / NOT_DEPLOYED**. The user subsequently delegated local preparation of demo settings; the dedicated attestor and six risk values are now filled, and the read-only doctor passes. See [current environment status](../demo/ENVIRONMENT_STATUS.md) for the exact demo values and external actions only if gas/RPC later proves insufficient. No V2 deployment/smoke transaction was sent during this preparation. `TEST_ONLY` configurations remain rejected both in proof generation for chain 43113 and by vault configuration on that chain.

The prepared operator path is `npm run treasury:deploy:fuji`, followed by `npm run treasury:fuji` and `npm run treasury:demo:fuji` in another terminal. It creates an OWNER_APPROVED config from the delegated env values and uses a separate V2 manifest. These are actual fee-paying testnet transactions, unlike doctor or env initialization. Verify resulting addresses/config/session and retain actual receipts before claiming Fuji success. Low-level integration can still use `deploy-fuji --v2-config <owner-config.json>` with an explicit isolated profile. Do not reuse a V1 immutable address or migrate real funds.
