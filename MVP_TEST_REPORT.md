# MVP verification report

## Latest judge/frontend checkpoint — 21/11/2026

| Check | Result | Scope |
|---|---|---|
| Full Python regression | **608 passed, 10 skipped** | [Report](docs/audit/judge-regression-results.json), before final focused additions |
| Final focused checks | **14 passed** | Judge schema/isolation/quotas/restart/timeout/source/replay plus existing route reason and readiness tools; overlaps full regression |
| React/TypeScript/Vite | Build passed; **10 client tests passed** | Exact request recovery, honest gates, asset decimals, escaped evidence and explorer attribution |
| Chromium | Passed desktop/mobile, 3 tabs, replay/evidence, reduced motion | [Latest UI](docs/audit/judge-frontend-check.json), [earlier live payment/reload](docs/audit/judge-browser-live-acceptance.json) |
| Foundry / EIP-712 vectors | **109 passed** / V1+V2+MVP passed | Core contract regression, no new public contract deployment |
| Real new Judge API | Payment CONFIRMED; guard REJECTED | Actual model/fork; [acceptance](docs/audit/judge-api-acceptance.json) |
| New live API swap | **Not confirmed** | PROOF VERIFIED + exact preflight succeeded; then UNKNOWN before RELAY. Root exception undetermined; later attempts lacked fresh Chainlink. Kept unresolved, never auto-resend |
| Native Linux | Local WSL Ubuntu 24.04 systemd/Nginx passed | Ubuntu 22.04 target VPS/TLS/soak pending; [report](docs/audit/judge-deployment-report.json) |

All three scenario recordings are genuine hash-pinned prior fork evidence. Recorded swap success does not certify the new API swap attempt. Public source read also verified at block 61393202, with oracle UNAVAILABLE at that observation. Vite warns that the main minified chunk exceeds 500 KB (169 KB gzip); this is a size warning, not a failed build. Two Python dependency deprecation warnings remain.

The older tables below describe earlier checkpoints. Focused counts overlap and must not be summed. Native Ubuntu/systemd/Nginx is the current deployment path; historical Docker results below are retained as history.


21 November 2026, Asia/Saigon. New public MVP contract deployment/AI-vault execution remains pending. After the original verification checkpoint, the user explicitly requested retirement-wallet consolidation; three public transfers confirmed, documented in [consolidation evidence](docs/audit/mvp-demo-funds-consolidation.json) and the [current review](docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md).

## Executed verification

| Check | Actual result | Evidence / scope |
|---|---|---|
| Before-change Python regression | 542 passed, 5 skipped | Existing suite, before expansion/MVP implementation |
| Before-change Foundry regression | Passed | Existing contracts |
| Full post-MVP Python regression | **586 passed, 10 skipped, 0 failed**, 805.53 s | `data/mvp-final-pytest.xml`; [portable summary](docs/audit/mvp-python-results.json) |
| Final operator/startup and affected workflow regression | **40 passed, 0 failed**, 143.75 s | `data/mvp-final-focused.xml`; includes new route-rejection reason, retired-session startup, public Owner identity and legacy compatibility |
| Affected legacy execution regressions after fee-ledger fix | 23 passed | Integration, unified app and LFJ unit suites |
| Focused MVP workflow/API/safety regression | 26 passed | Real local EVM/proofs/signatures; scripted semantic provider |
| Bounded planner / manifest sealing | 6 passed | Model cannot alter exact authority; Owner signature verified locally |
| Planner plus expanded MVP workflows | 16 passed | Includes read-only observer with autonomy disabled |
| Foundry, all suites | **109 passed, 0 failed, 0 skipped** | [Machine-readable results](docs/audit/mvp-foundry-results.json); includes local fuzz runs |
| Python ↔ viem vectors | V1, V2 and MVP all passed | Exact call/Phi ABI, EIP-712 digest, recipient/amount/domain tampering |
| Frontend syntax | 14 JavaScript files passed | `node tools/quality/check_frontend.mjs` |
| Ruff | Passed | Backend, tests and tools |
| Configured-secret scan | Passed; no leaked files | No secret values printed; private/runtime paths remain ignored |
| Headless Chromium workflow | Passed | [Result](docs/audit/mvp-browser-check.json), [screenshot](docs/audit/mvp-browser-check.png) |
| Real configured model, complete local payment | **CONFIRMED** | [Evidence](docs/audit/mvp-real-provider-results.json); real semantic calls, local EVM/test assets, full 1 USDC receipt |
| Real configured model, full Fuji-state fork | **2/2 CONFIRMED** | [Evidence](docs/audit/mvp-full-fuji-fork.json); real Circle/LFJ/Chainlink, payment and forward swap, VERIFIED proofs, exact final preflight without storage overrides; no public writes |
| Readiness-tool safety checks | **5 passed** | Public/non-Anvil/wrong-chain isolation and model-only credential filtering |
| Authorized Demo User consolidation | **3/3 CONFIRMED on public Fuji** | [Evidence](docs/audit/mvp-demo-funds-consolidation.json); source known assets zero; not an AI PolicyVault execution |
| Focused frontend deadline fix | **4 cases passed** | `node tools/quality/check_mvp_deadline.mjs`; oracle/session bounds, expired window, missing evidence; index module syntax passed |
| Docker image / hosting smoke | **Not verified** | Docker CLI exists, but Docker Desktop's Linux-engine pipe is unavailable |
| Public Fuji inventory | Verified read-only | [Pinned snapshot](docs/audit/mvp-public-state.json) |
| Quoter-aware Fuji fork + LFJ unit run | **17 passed, 1 skipped** | Four fork cases passed plus thirteen unit cases; fresh-oracle economic case skipped |
| New MVP public deployment/payment | **Not performed / not verified** | Explicit Owner authorization required |

Counts from different focused runs overlap and must not be added to the full regression count.

The final real-provider check ran the disposable local launcher without `--protocol-fixture`, using only selected model/Shield settings. Its serving configuration received generated local Attestor/Relayer keys and no Owner signing capability. The workflow passed planning, Task Shield, ITAG, risk, Z3, SDE, attestation and exact signed preflight, then confirmed a measured treasury debit of `1000000` and payee receipt of `1000000` USDC base units. Economic risk debit was zero; actual system gas expense was recorded independently. Tokens, price fixtures, EVM and receipt were local; this does not establish real Fuji execution or broad model attack-detection accuracy.

## Anvil fork findings

The final [fork evidence](docs/audit/mvp-fork-route-results.json) pins source block **61387667** and records no public writes:

* USDC → WAVAX direct V1 adapter execution succeeded with exact measured input/output and allowance cleanup.
* WAVAX → USDC direct V1 adapter execution succeeded as a **route-only experiment**.
* Both directions rejected unsupported pair, unauthorized recipient and excessive minimum output.
* Forward official quoter selected the approved V1 pair. Reverse official quoter selected a different pair, version 3, and `verified_quote` rejected it with `LFJ_UNSUPPORTED_ROUTE`.
* The final economic-reference case returned `STALE_OR_UNVERIFIED_CHAINLINK_PRICE`, so it was **skipped**, with `NOT_VERIFIED` evidence. No fixture price replaced it.

An earlier direct-route fork run passed five cases while independent price evidence was available. Separately, the valid public snapshot at block **61386636** measured **9886 bps** reverse reference loss against the unchanged **300 bps** owner limit. That timestamped observation is not a claim that an old round remains fresh for signing now.

Direct adapter compatibility does not establish full live authorization. The production builder preserves the official quoter/approved-route check and the independent economic proof. No bin route or higher loss threshold was introduced to force reverse success.

## Covered boundaries

Swap tests cover both directions, exact input/output, registry identities, source reserve ordering, quote consistency, slippage, stricter Phi under drift, unsupported recipient/pair, signature/domain/amount/Phi binding, replay, expiry, revoked/paused/versioned authority and cumulative budgets.

Payment tests cover approved Owner payee, poisoned/unsupported recipients, exact Circle restriction, excessive amount, per-payee/session/day limits, payment-only sessions with zero swap room, actual full receipt, local transfer fees/redirection, concurrent distinct requests, idempotent retries, expiry/replay/pause/revoke and unsupported native/WAVAX payments.

Proof tests cover satisfiable assumptions, contradictory/invalid bands, SAT counterexamples, UNKNOWN, stable query serialization, receipt credit, disabled-asset movement, conservative rounding and cumulative risk. Failed obligations cannot produce an attestation. Local deterministic semantic fixtures are explicitly labeled; they do not establish live LLM attack-detection accuracy.

Gas/recovery tests cover insufficient AVAX, gas and fee ceilings, atomic daily reservation/journal rollback, actual fee settlement, canonical receipt checks, reorg hold restoration, unknown broadcast, unverified replacement, signing/claim concurrency and outcome observation with autonomy off. Legacy gas-credit security tests remain available as isolated compatibility tests, without enabling customer billing in canonical runtime.

Owner migration is tested locally: an unpaused or unauthorized withdrawal cannot move old-vault assets, while Owner can recover them after pause. Owner-only native emergency recovery is separately tested and never exposed as an agent financial operation.

## Regressions and tooling issues corrected

The first broad implementation run reported 570 passed and three failures: lazy fixture compatibility, environment-template/default mismatch, and a superseded Demo User credential-forwarding expectation. Those were corrected without disabling security assertions. Code review during another intermediate run found schema initialization nested under an open SQLite write transaction; initialization now occurs before the transaction, and the affected legacy suite passed.

Browser testing caught a zero-match Attack Lab selector and an asynchronous UI assertion race. The selector now matches the exact zero-argument Foundry test, and the UI check waits for the measured fee result. The runner never converts a zero-test run into PASS.

The in-app Browser tool failed with `Importing module "node:process" is not allowed in node_repl`. Local headless Chromium then verified the real local frontend workflow. CSP remained enforced; browser assertions were changed to DOM assertions rather than enabling unsafe eval.

An initial `forge build --sizes` diagnostic also flags the pre-existing `Deploy` script artifact above the deployment size limit. The actual new deployable runtime sizes are **21,152 bytes** for `PolicyVaultMVP` and **4,825 bytes** for its adapter, both below 24,576 bytes. Ordinary build and the complete Foundry suite pass.

Final deployment review removed a stale active-session dependency from MVP serving and updated the Nginx default page/proxy. Container packaging now includes the public existing-role manifest plus native Forge and its compiler cache for the fixed offline Attack Lab. The 40-test final focused run passed after the Python startup changes. Container build/start cannot be claimed: `docker info` reported the missing Docker Desktop Linux-engine pipe, so the image changes remain source-reviewed only.

## Remaining verification

Public MVP deployment, vault funding, owner-manifest activation and real-provider AI-vault end-to-end execution on public Fuji remain unverified. Both new operations have confirmed real-provider evidence on a fork using real Fuji token/DEX/oracle state. The user-authorized wallet consolidation has separate public receipts; it does not establish MVP contract acceptance. Current reverse quoter selection, severe V1 reference-price divergence and intermittent oracle freshness remain real constraints. Existing public deployment addresses and private configuration were not replaced.

The frontend retry limitation was subsequently fixed: key/body/deadline persist before POST; authenticated recovery by request key and read-only polling preserve uncertain requests across reload/login. The [new browser check](docs/audit/mvp-resilience-browser.json) deliberately loses a successful response and verifies exactly one payment/debit. The VPS/readiness changes passed **26 focused Python tests**, client recovery and four deadline cases, 16 JavaScript syntax checks, Ruff and Compose configuration validation. No full-suite or public money-spending run was repeated for these changes. Docker image/start and actual VPS/TLS acceptance remain unverified because the engine is unavailable here. See the [VPS runbook](MVP_VPS_RUNBOOK.md).
