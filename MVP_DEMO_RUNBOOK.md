# PaceVant single-tenant MVP runbook

21 November 2026. All public-chain actions below require separate explicit authorization. Commands marked read-only/local do not deploy or transfer assets publicly.

Latest authorized funding update: Demo User has been fully drained to existing Owner/Relayer, with three confirmed public receipts. Owner now holds 40.000004 USDC and 0.047873064882675760 AVAX; Relayer holds 20 USDC and 0.031999999692398823 AVAX at block 61389438. See the [current review](docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md) and [transfer evidence](docs/audit/mvp-demo-funds-consolidation.json). Tables below remain their labeled earlier snapshots. Proposed Owner-to-new-vault funding remains unexecuted; after 5 USDC funding the Owner token reserve would be 35.000004 USDC.

## Verify current public state first — read-only

```powershell
uv run --locked python tools/operations/audit_mvp.py
```

The committed [inventory](docs/audit/mvp-public-state.json) is a timestamped observation, not a readiness promise. Re-run before funding or preparing owner transactions.

| Location at the recorded snapshot | Circle test USDC | AVAX |
|---|---:|---:|
| Owner | 20.000004 | 0.027873064882675760 |
| Attestor | 20 | 0.000499999924946240 |
| Relayer | 20 | 0.001999999706328263 |
| Existing PolicyVault | 0.001378 | 0 |

The vault also held `0.000066137381683518` WAVAX. There are about 60 USDC across these locations, not 20 USDC already in treasury. Attestor/Relayer token holdings are not automatically available to PolicyVault.

Proposed funding, pending approval: send **5 USDC from Owner to the newly verified vault**, leaving 15.000004 USDC with Owner. Leave Attestor/Relayer USDC untouched. Optionally recover the old paused vault's precisely rechecked token balances to the new vault. Keep Relayer's existing AVAX for a few bounded demos; add gas only if estimates and balance checks require it. Retain Owner AVAX for deployment/admin/kill-switch costs, re-estimate all 13 migration transactions before signing, and preserve an emergency reserve. No allocation has been executed.

## Run the complete disposable local demonstration

```powershell
npm run demo:mvp:local
```

Open the URL printed by the launcher, normally `http://127.0.0.1:18030`. Read the **local operator credential** from the printed private file path and enter it in the Operator field. This is not a wallet/private key. The session is selected from the verified manifest; there is no Demo User wallet selection or browser HMAC persona.

This npm command explicitly selects **LOCAL TEST with scripted semantic protocol responses**. EVM simulation/execution, Z3, EIP-712 and receipt/fee measurement are real locally. This is not an LLM-detection benchmark and never produces a public Fuji receipt. For a real model in local mode, run the module without `--protocol-fixture` after configuring the existing Shield provider environment; provider failures stop the workflow.

One complete real-provider local payment was also verified: [evidence](docs/audit/mvp-real-provider-results.json). To reproduce it after configuring only the model/Shield environment, run `uv run --locked python -m treasury_backend.operations.mvp_demo --once --output data/mvp-real-provider-new`. The launcher deliberately does not load root `.env`; do not pass public Owner/wallet keys into this local check. This remains local EVM execution with controlled test assets and prices.

```powershell
npm run demo:mvp:smoke
```

The smoke creates a disposable three-role treasury and pays exactly 1 local test USDC to its approved Owner EOA. It prints a safe summary and stores evidence under ignored `data/`. No public `.env`, deployment identity, balances, session or nonce is reset.

## Operator scenarios

1. **Forward swap:** choose `SWAP_EXACT_IN`, USDC → WAVAX, a bounded amount and an affirmative goal. Inspect planning, Shield, simulation, ITAG, risk, Z3, SDE, attestation, exact preflight and outcome.
2. **Reverse swap:** first obtain WAVAX in the local treasury, then choose WAVAX → USDC. On current real Fuji state, expect route/economic rejection; do not force an approval.
3. **Payment:** choose `USDC_PAYMENT`. Only owner-approved recipients appear. The repeated-demo preset is **0.01 USDC**; inspect exact treasury debit, actual payee receipt, zero economic risk debit, payment spending and system gas expense. The updated Owner draft permits at most 0.1 USDC per payment.
4. **Rebalance:** preview deterministic deviation, then request one bounded action or explicitly enable the scoped loop. It uses only swaps. Owner scope, expiry, cooldown, action count and all gates still apply.
5. **Security Center:** inspect the selected workflow's raw proof evidence and PDR metadata. Owner pause/revoke actions are prepared unsigned. Only the exact Owner wallet on the exact chain can sign and execute them.
6. **Attack Lab:** select a fixed unauthorized payment, injection proposal, drift/slippage, daily-cap, tampering, or revocation test. The runner uses isolated Foundry state, fixed case names, operator authentication, rate/concurrency limits and zero public gas.

## Reproduce tests and real-route fork observations

```powershell
uv run --locked python -m pytest backend/tests/execution/test_mvp_workflows.py backend/tests/execution/test_mvp_safety.py backend/tests/execution/test_mvp_api.py -q
uv run --locked python tools/quality/record_mvp_foundry.py
$env:PACEVANT_MVP_FORK='1'
uv run --locked python -m pytest backend/tests/execution/test_mvp_fuji_fork.py -q
Remove-Item Env:PACEVANT_MVP_FORK
```

The fork suite obtains real Circle/LFJ/Chainlink state and writes only to disposable local Anvil. Its direct-route tests intentionally isolate route compatibility from security approval; their output records quoter rejection separately. `ANVIL_FORK` hashes must never be pasted as public Fuji explorer links.

The full six earlier V3 research scenarios remain reproducible in `test_v3_workflows.py`, but deposits, redemptions and native payments from that research suite are **disabled in the MVP**.

## Prepare the public migration — no signing or broadcast

```powershell
uv run --locked python tools/operations/prepare_mvp_migration.py
```

Review [OWNER_REVIEW_REQUIRED.json](fixtures/mvp/OWNER_REVIEW_REQUIRED.json) and the generated [unsigned plan](docs/audit/mvp-unsigned-migration-plan.json). The plan preserves the existing three public roles, revokes the old session, pauses the old vault, deploys a two-operation vault and bidirectional adapter, configures separate scopes/budgets, approves Owner as payee and includes explicit 5 USDC funding. Optional old-vault token recovery is listed separately.

The reverse amount cap is an explicit proposed policy change from zero; economic thresholds are copied unchanged. The config is marked `owner_reviewed: false`. Predicted addresses depend on the observed Owner nonce. Regenerate after any Owner transaction, before expiry, or after changing configuration. **This tool cannot access an Owner key and contains no broadcast operation.**

After explicit authorization and external Owner execution of reviewed transactions:

```powershell
uv run --locked python tools/operations/seal_mvp_manifest.py
```

This read-only tool checks deployed code presence, roles, adapter and session, writes a draft, and prints the public manifest signing message. Sign that message with the Owner wallet outside the serving process, then supply the resulting public signature with `--owner-signature`. The tool verifies the signer and writes the manifest. It has no Owner private-key input.

Manually configure the signed manifest path and `PACEVANT_MVP_LIVE_ENABLED=1` only after those checks. Keep all three credentials distinct and reuse the existing role addresses. Start using the existing operator command:

```powershell
uv run --locked treasury serve --network fuji
```

Startup refuses an unsigned/tampered manifest or an unauthorized public execution configuration. Do not silently replace the old deployment file. Old mutation APIs are disabled when MVP is active; read/history/reconciliation remains.

The MVP serving command validates the new manifest without requiring the intentionally retired V2 session to remain active. Keep the old manifest and durable data for reconciliation. For a container, mount the signed new manifest read-only in addition to the old V2 manifest, and set `PACEVANT_MVP_MANIFEST_FILE` to that container path. The frontend image opens `treasury-mvp.html` and proxies `/mvp/` to the backend. Container/image hosting has not been smoke-tested in this environment.

**Public success is not yet verified.** Payment needs the new owner-authorized deployment/funding/session. Reverse swaps currently fail the quoter and economic gates. A failed gate is a valid rejection, not a successful Fuji demo.

## Safe shutdown and recovery

Stop a local launcher with Ctrl+C; it shuts down its owned Anvil process. Keep production SQLite, proof artifacts, execution journal and fee ledger across restarts. Never delete them to reset a cap.

After timeout, inspect the existing workflow ID with `GET /mvp/workflows/{id}`. Reuse the same idempotency key/body; do not create a second payment. The observer runs with autonomy off. Unknown/reorg/replacement states keep reservations. There is no automatic fee-bumping or fresh signing to hide a stuck transaction. Review a replacement or dropped transaction explicitly before releasing authority or spending again.

The browser now persists the exact key/body/deadline before POST. After a lost response or reload, log in again and use **Resume the same request**. It first queries the saved workflow/key and never creates a replacement payment or refreshes its deadline. Background polling is read-only. Credentials remain in memory. See the [VPS runbook](MVP_VPS_RUNBOOK.md) for HTTPS, restart, readiness and the seven-day Owner-reviewed configuration.

Owner pause/revoke requires an Owner-signed transaction and becomes effective when included on-chain. Previously signed prohibited execution then fails. Failed EVM execution still costs Relayer gas; that expense is recorded separately from trading loss.
