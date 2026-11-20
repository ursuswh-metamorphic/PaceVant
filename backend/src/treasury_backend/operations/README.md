# Operator commands and composition

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`observe.py` / `observer.py` provide the optional key-free portfolio/outcome observer ported from main. Normal serving already runs `modules.monitoring.worker` inside the single backend. For the optional separate observer, `PACEVANT_B_URL` may point to `http://127.0.0.1:8000/execution`. `a_environment` explicitly forwards `PACEVANT_SHIELD_*`; execution/deployment environments exclude model credentials. See [main integration configuration](../../../../docs/integrations/MAIN_SYNC_2026_11_20.md).

`fuji-demo --setup` is the bounded owner bootstrap (deploy, up to 0.008 test AVAX token purchase and 0.002 gas transfer, gas additional). `fuji-demo` reuses deployment/funding, selects a tiny exposure-safe goal, starts one backend, runs the workflow and exports public receipt checks. It retries fresh evidence at most twice only before attestation/submission. `fuji-evidence --workflow-id ...` rechecks a confirmed receipt and three negative eth_calls without broadcasting. Owner deployment/setup steps journal signed bytes before send; preserve journals on timeout. Deployment journal names include the selected manifest path scope.

Live Chainlink profiles read feeds directly; the launcher does not compete with a periodic oracle writer during fork calls. Independent contract reads are batched at an explicit block, with hash/reorg and policy checks retained. On Windows, owned Popen subtrees are stopped together so a venv interpreter child cannot remain after launcher shutdown.

With `PACEVANT_REQUIRE_ITAG=1`, `services.demo` delegates to `itag_demo.py`: create one operator-authenticated exact-amount intent, start the workflow, poll only an existing submission and persist its result. It never substitutes scripted AI. Unknown signed/submitting outcomes are not retried as fresh intents. Provider/schema/artifact/RPC fixes and the owner-approved 300-second policy are documented in the [current Fuji runbook](../../../../docs/demo/FUJI_ITAG_LIVE.md). A renewal whose owner receipts succeeded but final read failed reports `OWNER_CONFIGURATION_CONFIRMED_PREPARE_REQUIRED`; use `prepare`, not another renewal, to complete the read-only step.

Live update 2026-11-20: [Circle / Chainlink / full Fuji demo](../../../../docs/demo/FUJI_LIVE_END_TO_END.md). Earlier faucet-USDC blockers and controlled/mock descriptions below belong to their historical profiles.


`cli.py` provides `uv run treasury` and `python -m treasury_backend`. `env.py` owns safe/idempotent env initialization; `profiles.py` owner policy/profile validation; `environments.py` builds the unified owner-free environment (attestor + relayer) and retains role-specific filters for legacy tools; `processes.py` native tools/child processes; `contracts.py` deploy/prepare/renew; `services.py` one-backend lifecycle, demo and doctor; `container.py` owner-free hosted startup. `execution.py` retains B-only legacy operator commands; configuration/vector/sample generators live here as well. Deployment and renewal are explicit transactions; serving never deploys contracts. Never log private keys, bearer tokens or authenticated RPC URLs. The launcher starts one Uvicorn child with the current interpreter (`sys.executable`), not two API servers or a second virtual environment. Logs are backend.log; the oracle heartbeat remains in the launcher.

See [backend setup](../../../README.md), [module boundaries](../../../MODULES.md) and [environment/deployment](../../../../deploy/README.md).

```sh
uv run --locked python -m pytest backend/tests/architecture backend/tests/control backend/tests/integration -q
```

Run from the repository root. Integration tests need native Foundry. Keep routes, config, deployment composition and feature behavior in their respective folders; add regression cases for any changed security boundary.

`owner_transactions.py` journals renew-policy/session transactions before broadcast, verifies sender/hash and serializes writes. Session IDs are stable while resuming an operation from the previous manifest; after confirmation the manifest advances. Preserve private journals on timeout and resume with the same config; do not share raw signed bytes. The current operator profile uses a 24h session and 200-block drift, with 300s approval/snapshot limits. Direct Chainlink signing does not use the optional startup price cache: a failed refresh is reported UNAVAILABLE without stamping old data; source/scope mismatches still abort. `doctor` checks Shield/ITAG configuration and key presence, not actual model uptime.
