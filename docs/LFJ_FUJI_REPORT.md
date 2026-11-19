# LFJ Fuji integration report — 19/11/2026

**Status: implemented and Fuji-fork verified; public Fuji end-to-end Definition of Done remains incomplete.** No user wallet was supplied or used. Public Fuji transaction count: **0**. This is a reviewable dry-run/fork implementation; live SDE approval stays blocked.

## Verified live inputs

- Official registry: https://developers.lfj.gg/deployment-addresses/fuji.md
- Router V2.2: `0x18556DA13313f3532c54711497A8FedAC273220E`; Quoter V2.2: `0x9A550a522BBaDFB69019b0432800Ed17855A51C3`.
- LFJ test USDC `0xB6076C93701D6a07266c31066B298AeC6dd65c2d`, decimals 6; WAVAX `0xd00ae08403B9bbb9124bB305C09058E32C39A48c`, decimals 18.
- Verified direct route: **V1 pool** `0x9371619C8E2A487D57FB9F8E36Bcb0317Bff0529` through the V1 factory returned by LBRouter V2.2. Quoter, registry, factory, pair identity, code and decimals were cross-checked, then execution verified on a fork.
- Preflight discovers nine LB pairs across V2/V2.1/V2.2 for this token pair, with actual token balances; those observations are not a claim that every LB bin is executable.
- LFJ + existing Chainlink reader pinned to block **61337012**, hash `0xb041ae2ae4422b935b62fc05b2a123b39da36ed1748cb330695c826efc17f412`, observed block time **2026-11-19T22:43:11+07:00**. See full JSON for feed timestamps, raw rounds and hashes.

## Fork execution evidence

- Public source block for the successful stress run: **61337202**.
- Actual swap on isolated Anvil: **0.1 LFJ test USDC → 0.012194140979091525 WAVAX**; quote, ERC-20 logs and balance deltas matched.
- Gas: **262169**; fork fee **262169001835183 wei**. Effective token-unit price is recorded as LFJ test USDC/WAVAX, not a USD oracle.
- Signed contract-test approval remained mandatory; nonce consumed, both allowance layers cleaned up, replay rejected.
- Production simulator replays the pinned state through actual LFJ code and records trace/logs/deltas. Mild ordered-swap stress: **SUCCESS_SAFE**; adverse: **PROTECTED_REVERT**. Smaller treasury unable to fund required stress: **INCONCLUSIVE**.
- Simulation evidence root: `0xde1bc41994e8699db4dad55d75b68605e3974efbedf0b82bff24ba153051642e`. Artifact bundle hashes and joint oracle report hash were independently recomputed successfully.
- The contract-test receipt used a clearly labelled fork-only sentinel approval root; the simulation root above is computed separately afterward. This is not an A/SDE-authorized public receipt. Root/PDR binding and relayer idempotency are exercised by existing A+B/local tests and enforced in production code.
- Vault/adapter deployments, faucet-owner impersonation/mint, role accounts, gas top-ups, setup-time block and simulation attestor override occurred **only on local fork copies**. Pool liquidity/storage was not fabricated or mutated directly. These addresses/hashes are not public Fuji deployments/receipts and must not be linked as such.

## Validation

| Check | Result |
|---|---|
| Solidity, including 10 new LFJ security tests | 37 passed |
| A tests on Windows and Linux | 59 passed |
| B tests, including A+B suite | 51 passed; 2 opt-in live-fork cases skipped by default |
| A+B re-run after final A changes | 4 passed |
| Opt-in real Fuji-state fork cases | 2 passed |
| EIP-712 Python/TypeScript/Solidity golden | PASS |
| Ruff/lint/format, secret scan | PASS |
| Artifact manifest/bundle/observation hashes | PASS |

Commands for reproduction: `npm run compile`, `npm run test:contracts`, `npm run check`, `uv run --locked python -m pytest -q`, `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `npm run test:ab`, `npm run test:lfj:fork`, `npm run lfj:preflight`, `uv run --locked python scripts/lfj_preflight.py --output evidence/lfj-fuji-oracle-preflight.json`. The fork tests were executed directly with `PACEVANT_LFJ_FORK=1 uv run --directory apps/execution-plane --locked python -m pytest tests/test_lfj_fuji_fork.py -q -s --tb=short`, equivalent to the new npm wrapper. Preflight was invoked with the corresponding `python -m app.cli lfj-preflight --dry-run` and Python script in the locked environments. Full B/A+B and fork runs used Linux/WSL; A and Solidity also ran on Windows.

Tests retain wrong-chain/token/router/calldata/signature, expired PDR, replay, revoked policy, paused Vault, per-swap/daily limits, rollback and idempotent retries. New LFJ cases check route/recipient restrictions, output mismatch, exact allowance cleanup, malformed/no-liquidity quotes, token decimals, unauthorized downstream transfers and dry-run without broadcast or nonce/journal effects. The existing Fuji-evidence negative test now explicitly enables its local fixture's broadcast setting so it still reaches and tests the evidence-source guard; its rejection assertion is unchanged.

## Remaining blockers and mock components

1. **Pricing:** LFJ faucet USDC is not Circle USDC; no verified independent USD value/peg has been established. A refuses the old test-price file in FUJI mode, and risk returns `ORACLE_TOKEN_IDENTITY_MISMATCH`/INCONCLUSIVE even if a test-price snapshot is supplied. No PDR is issued. DEX quote is not substituted for an independent USD oracle.
2. **Operator setup:** owner, A attestor and relayer are not configured in preflight. Test AVAX and LFJ token funding remain to be checked when the operator sets up wallets locally. A read-only mint probe showed the LFJ token's `mint(address,uint256)` is owner-restricted; the fork test impersonation is not a live faucet workaround.
3. **Authorization/deployment:** public broadcast is disabled by default. Deploy commands produce a dry-run until separately authorized. No current PolicyVault/LFJ adapter deployment manifest or confirmed public receipt exists.
4. **Latency:** 30-second TTL and 3-block drift limits were not relaxed. Cold fork setup exposed stale-clock rejection; the isolated fixture mines a current setup block, as existing Anvil fixtures do. This does not validate wall-clock latency against continuously mining Fuji. Live acceptance requires measuring the complete pipeline within the original limits.
5. **Route scope:** only the verified direct V1 pool is supported. Quoter switching to a different/multi-hop route fails closed. Future router, token/proxy, pool or registry changes need revalidation; runtime hash checks are not a proof of decentralized oracle governance.
6. **Remaining mocks:** local regression tokens/MockSwapAdapter and ABI-compatible unit doubles remain deliberately. The FUJI execution profile rejects mock deployment manifests and uses actual LFJ token/router code. Fork-only signatures and funding are test setup, not real user funds or SDE approval.

## Delivery and next decision

See [setup and operation guide](LFJ_FUJI_INTEGRATION.md) and [machine-readable summary](../evidence/lfj-validation-summary.json). The branch is based on the latest integrated oracle branch and intended as a stacked draft PR; no merge is performed. Wallet information is not needed to review/run the read-only deliverables. Live deployment/execution is a later, separately authorized step after valuation and funding blockers are resolved.

## Changed files

- `.env.example`
- `.github/workflows/execution-plane.yml`
- `README.md`
- `apps/control-plane/app/economic_risk/__init__.py`
- `apps/control-plane/app/orchestration/client.py`
- `apps/control-plane/app/orchestration/service.py`
- `apps/control-plane/app/settings.py`
- `apps/control-plane/tests/test_workflows.py`
- `apps/execution-plane/app/chain/__init__.py`
- `apps/execution-plane/app/cli.py`
- `apps/execution-plane/app/dex/__init__.py`
- `apps/execution-plane/app/dex/deploy.py`
- `apps/execution-plane/app/dex/lfj.py`
- `apps/execution-plane/app/evidence/extractor.py`
- `apps/execution-plane/app/execution/relayer.py`
- `apps/execution-plane/app/settings.py`
- `apps/execution-plane/app/simulation/lfj_stress.py`
- `apps/execution-plane/app/simulation/runner.py`
- `apps/execution-plane/app/transaction/builder.py`
- `apps/execution-plane/pyproject.toml`
- `apps/execution-plane/tests/test_integration.py`
- `apps/execution-plane/tests/test_lfj.py`
- `apps/execution-plane/tests/test_lfj_fuji_fork.py`
- `apps/execution-plane/uv.lock`
- `contracts/script/Deploy.s.sol`
- `contracts/src/adapters/LFJSwapAdapter.sol`
- `contracts/src/interfaces/ILFJ.sol`
- `contracts/test/LFJSwapAdapter.t.sol`
- `docs/04_PERSON_B_RUNBOOK.md`
- `docs/B_HANDOFF.md`
- `docs/LFJ_FUJI_INTEGRATION.md`
- `docs/LFJ_FUJI_REPORT.md`
- `evidence/lfj-fuji-fork-validation-insufficient-stress-budget.json`
- `evidence/lfj-fuji-fork-validation.json`
- `evidence/lfj-fuji-oracle-preflight.json`
- `evidence/lfj-fuji-preflight.json`
- `evidence/lfj-secret-scan.json`
- `evidence/lfj-validation-summary.json`
- `package.json`
- `packages/contracts-api/BuiltTransaction.schema.json`
- `packages/contracts-api/README.md`
- `packages/contracts-api/openapi.json`
- `packages/contracts-api/pyproject.toml`
- `packages/contracts-api/treasury_contracts/__init__.py`
- `packages/contracts-api/treasury_contracts/models.py`
- `pyproject.toml`
- `scripts/lfj-fork-test.mjs`
- `scripts/lfj_preflight.py`
- `uv.lock`
