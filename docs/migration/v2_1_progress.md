# V2.1 migration progress

## Latest backend packaging update — Python launcher / Render / VPS

Removed Node invocation from backend compile/startup: shared native Foundry resolver, `scripts/foundry.py`, direct Forge calls in operator/B CLI, native Anvil resolution and Python bootstrap of pinned/hash-verified OpenZeppelin 5.6.1 under `lib/`. Solidity contracts and browser JavaScript remain. npm/viem are optional developer compatibility/cross-language tooling; backend Docker contains neither Node nor npm.

Added multi-stage Dockerfile: Forge/solc compile artifacts during build; runtime carries Python environments, Anvil and artifacts, without compiler. One Python entrypoint runs public A on `$PORT` and private loopback B, handles process shutdown and places SQLite/evidence/journal under `/var/data`. Runtime can verify public owner from manifest without loading owner private key; owner transactions still explicitly require that key. Container preflight refuses known owner-key env variables and missing/duplicate service credentials.

Validation: native compile PASS; root Python **87 passed / 0 failed** (44.40 s), including a complete compile/deploy/proof/sign/receipt/local-renew workflow whose child PATH has no Node, plus new container configuration/owner-key tests. Forge suite PASS (49 existing tests, native `forge test -q` exit 0). B Python **46 passed / 1 opt-in skipped** (160.24 s). Control/scripts/tests lint PASS. No Fuji transaction or hosting service was created. Pinned Foundry container tag v1.7.1 was verified present for Linux amd64/arm64.

Docker Desktop Linux engine is not running on the workstation, so image build/runtime and actual Render deployment are **not yet verified**. A CI image build/check job was added but not executed remotely in this session. See [Render/VPS runbook](../deployment/PYTHON_BACKEND_RENDER_VPS.md) and [runtime env template](../../deploy/runtime.env.example). Render requires durable disk for existing SQLite/raw-journal design; only one instance is supported.

Recovery note: an incorrectly parsed lint CLI argument briefly applied automatic fixes across ignored local dependencies/reference snapshots. Stopped the command, restored reference/archived source from exact Git blobs, restored pinned dependency source and reinstalled the three local Python environments from locked dependencies. Final full Python/contract suites passed after recovery. No owner/attestor/relayer keys or env values were modified. Also corrected UTF-8 rendering in the environment-status document.

## Latest environment/documentation update — explicit user delegation

User explicitly authorized filling values that can be prepared locally without obtaining external accounts. Generated the missing dedicated test attestor locally, derived its public address, preserved existing owner/relayer keys and service tokens, and filled the six blank Fuji-demo parameters: relative loss 300 bps, fixed loss $0, oracle band 100 bps, tolerance 40 bps, session $10/global $20. `TREASURY_OWNER_POLICY_APPROVED=true` now records delegated demo selection; reverse cap remains 0. This later instruction supersedes the earlier missing-input checkpoint, rather than silently claiming the user had supplied values earlier.

Read-only doctor now returns **configuration_ready=true**, chain 43113, three distinct wallets, nonempty owner/relayer gas balances and historical state read PASS. No mandatory env values remain missing for the standard demo profile. **Fuji V2 remains NOT_DEPLOYED**; no live transaction was sent in this configuration/documentation update. If deployment later needs more gas or a more capable RPC, faucet/provider access is the external action. Do not equate ready config with successful deployment.

New [current system flow](../CURRENT_SYSTEM_FLOW.md) documents actual API routes, planner/evidence/proof/SDE/revalidation/signing/vault/monitor, two distinct signature layers, key boundaries and why Node.js is tooling while the APIs are Python. [Environment status](../demo/ENVIRONMENT_STATUS.md) and entrypoint docs were updated to the current state. Historical missing-input/approval-false statements below are retained as earlier checkpoints.

## Current completion checkpoint — 2026-11-19

Phases 0–5: **DONE for the declared local core**. Phase 6: **DONE for bounded local acceptance**, now including an isolated original-commit/full A/B protocol comparison and stage timings, alongside the four-mode guard ablation and liveness sweep. Fuji deployment/smoke remains **BLOCKED_EXTERNAL_DEPENDENCY**, not a claimed deployment. Broader adversary populations, full-protocol B/C performance and optional on-chain exposure are not claimed.

Current operator workflow: [complete local/Fuji demo guide](../demo/AVALANCHE_FUJI_DEMO.md), [sanitized environment status](../demo/ENVIRONMENT_STATUS.md). The chronological checkpoints below retain earlier results; earlier PARTIAL evaluation and statements about an untouched `.env` are superseded by this checkpoint.

Files added/changed for completion: `scripts/treasury.py`, `treasury_ops.py`, `evaluate-protocol.py`, `protocol_server.py`, `.env.example`, locked root dependencies, package commands, A's configurable freshness-by-block/verification RPC, operator/security tests, CI and documentation. This is orchestration of the existing A/B/proof/signer/relayer, not another execution path.

Added behavior: idempotent env initialization without overwriting keys, separate V2 local/Fuji manifests and data profiles, chain/code/config/session validation, deployment-derived mandate, independent controlled oracle heartbeat, complete stack startup/shutdown, actual workflow/report generation, owner-only session/policy renewal preserving old sessions and day/global usage. Child A receives only its attestor key; child B API receives only its relayer key; owner key is passed only to explicit deployment/configuration operations. Service credentials are distinct and absent from output/assets. Anvil writes are limited to LOCAL; Fuji oracle refresh is read-only.

Freshness: A/B operator profiles use max block drift 3 local / 30 Fuji (bounded 1..120), with existing 60-second freshness, 30-second approval TTL, independent Fuji block/hash/code verification and final preflight preserved. More accepted blocks is an explicit operational tradeoff, not a removal of staleness checks. Tests cover expired evidence and a smaller block allowance still refusing.

Commands and final results:

- `npm run check`: **PASS**, 49 Forge tests, 46 execution Python passed / 1 opt-in ablation skipped (186.59 s); V1/V2 Python↔viem vectors and configured-secret scan PASS. No baseline test removed.
- `uv run --locked python -m pytest -q`: **84 passed**, 0 failed/skipped (38.71 s). Includes complete operator CLI through real A/B, proof/sign/relay/receipt, followed by real owner session renewal; old session usage, global usage and USDC daily spend remain unchanged after renewal.
- `npm run treasury:local:smoke`: **CONFIRMED** using the actual root environment's service credentials and isolated V2 LOCAL profile. Real Anvil tx/report written; owned services/Anvil stopped. No testnet key or Fuji transaction used.
- Full-protocol benchmark: **14 actual records** with expected outcomes and inclusion ordering validated. Original V1 source commit `1b09bd8dd04fd74868f30634abeec93276522d36`; normal gas 175,885 original / 242,683 V2.1. Harmful drift prevention 1/2 vs 2/2, benign 2/2 both; third cumulative V2 trade gets no signature after two $4.792 reservations. See [full report](../evaluation/full_protocol_results.md) for measured stage timings, denominators and limits. Final report metadata is derived from preserved immutable workflow/SQLite records.
- Ruff check of control plane, tests and all four operator/evaluation scripts: **PASS**. Dashboard JS syntax and Git diff whitespace: **PASS**.
- Read-only Fuji doctor: chain **43113**, RPC/historical reads successful and owner/relayer gas balances positive. Configuration readiness remains false for the explicit missing inputs below. No V2 Fuji manifest/address/tx hash is claimed.

During benchmark development, missing archive-local Anvil resolution, synthetic future/stale timestamps and cross-scenario SQL quarantine contamination were detected. Final harness supplies the pinned binary, synchronizes owned node time and isolates both chain/application state per scenario; security gates were not disabled. Initial failures are not represented as successful data.

Environment changes authorized by the user: existing wallet/RPC/API-key entries were preserved; missing `PACEVANT_*`/`TREASURY_*` entries were appended and missing service tokens generated locally. **Still blank:** `PACEVANT_ATTESTOR_KEY` and the six owner risk variables listed in the environment status doc. `TREASURY_OWNER_POLICY_APPROVED=false` remains; reverse cap stays 0. An optional explicit `treasury:init -- --generate-attestor` writes a fresh test-only signer locally and derives its public address. No owner risk appetite was inferred.

External next action: owner fills those variables, reviews policy/optional reverse cap, then runs `treasury:doctor`, explicit `treasury:deploy:fuji`, `treasury:fuji` and `treasury:demo:fuji`. Three distinct test wallets and sufficient Fuji C-Chain test AVAX are required. Implementation-plan principle 9 prevents silently promoting local TEST_ONLY parameters into Fuji owner approval.

Git: no staging/commit/push, no PGS imports or tracked reference files, no runtime/secret files included. [Full changed-file list](v2_1_changed_files.md). Local generated audit/evaluation data remains ignored. Warnings are upstream websockets/Starlette deprecations and existing compiler lint, not failed checks.

## Phase 0 / DONE
Files: `.gitignore`, inventory and reference map.
V1 preserved: all runtime untouched during baseline.
Commands: `npm run check` (27 Forge, 38 B Python, golden PASS, secret scan PASS); `uv run --locked python -m pytest -q` (33 passed); Git root/status/branch and PGS commit/ignore/index checks.
Assumptions: existing unaudited controlled mock system; baseline latency/coverage not measured.
Deployment: none. Existing credentials were not displayed or used to submit Fuji transactions.

## Phase 0B / DONE
Read local PGS guard/chain/testbed/scenarios, license and commit. Independent implementation; no vendor copies. See source map.

## Initial implementation checkpoint (superseded by phase results below)
Shared exact-unit schemas and ABI, pure proof engine, permanent V2 vault activation and owner sessions under implementation. No Fuji signer activation; no owner risk settings inferred.


## Phase 1 / DONE (local core)
Files: shared `wire.py`, `v2.py`, `onchain_v2.py`, models/schema extensions, existing builder/simulator/evidence extractor integration, `app/proof`, economic risk and registry reads.
V1 preserved: existing units, hard caps, semantic alignment, fixed stress requirements, exact calldata and portfolio/gas checks. Existing V1 schemas remain accepted; V2 fields are additive and omitted from V1 payloads.
V2 added: canonical integer/rational USD-e8, fixed sorted registry, actual 6/18 decimal validation, complete before/after token and allowance reads, pinned context, controlled oracle provenance, explicit test-only policy fixtures. Reverse swaps have their own cap and remain disabled at zero.
Commands: dependency sync/lock updates; schema regeneration; proof tests; real guarded fork integrations.
Tests: included in final 73 root Python and 46 execution Python results below. No partial-evidence signing path.
Assumptions: two supported mock assets; controlled off-chain oracle file (valuation block context, not an on-chain feed claim). Exposure remains pre-sign only.

## Phase 2 / DONE (conditional proof core)
Files: single shared `treasury_contracts/proof.py`, V2 typed artifacts, pure formal/property tests and concurrent proof checks.
Added: independent SAT assumptions and Phi feasibility, Check/Compile/risk UNSAT obligations, one zero-tolerance fallback, source/query/encoder/version commitments, exact upward certified risk debit, sanitized SAT witness, UNKNOWN/error refusal. Z3 4.15.4.0 pinned in both locks. Native solver context serialized for thread safety.
Commands: `uv run --locked python -m pytest tests/integration/test_proof_v2.py -q` (21 passed); root suite includes two resource/concurrency tests and 17 SDE/attestor/database tests.
A real stability defect was found during integration: Z3 `to_smt2()` contains process-global AST IDs. Replaced by deterministic `sexpr()` query encoding; repeated/concurrent revalidation is now tested. No unsafe success from contradictory assumptions or unknown solver results.

## Phase 3 / DONE (local)
Files: existing PolicyVault, mock adapter, shared ABI/golden helpers, existing attestor/builder/simulator/relayer and operator CLI.
V1 preserved: owner/pause/revocation, domain, exact ABI, replay, limits, nonreentrancy, allowance cleanup, rollback and old signatures on legacy deployments.
Added: permanent V2 activation locks legacy entrypoint; EIP-712 version 2 and all 15 fields; exact two-asset Phi; one proof adapter; owner-only non-recyclable sessions; atomic session/global/day debit and directional hard caps; real final-Phi/debit replay on isolated guarded fork before attestation. Attestor checks call/session/proof bindings and re-runs trusted SDE verification, receives only immutable decision ID publicly. Relayer submits the stored signed call/Phi unchanged.
Commands: `npm run test:contracts` (49 passed, 0 failed, 0 skipped; both fuzz cases run 256 samples); `npm run test:integration` (V1 and V2 Python/viem PASS; Foundry consumes V2 golden ABI too).
Deployment: ephemeral private Anvil deployments only. New Fuji V2 address/transaction: NONE. See runbook for separate immutable-vault cutover.

## Phase 4 / DONE (local core)
Files: additive immutable proof/Phi SQL tables in existing Store, content-addressed query files, existing workflow/SDE/attestor/monitor, API read endpoints, A/B request limits, dashboard.
Added: proof introspection, chain-authoritative session reads, guarded final preflight artifact, canonical receipt block hash and confirmation policy, reorg reconciliation including terminal workflow reads, in-flight signer reservation, protected-revert reason codes and same-policy quarantine after two consecutive protected reverts. Gas aggregation deduplicates reconfirmed receipt identity. No competing SQL risk counters.
Rollback: additive DB tables can remain for audit under old application build; switch back only to a V1 deployment/profile. Permanent V2 vault activation cannot be undone. See runbook.
Dashboard: existing interface now supports authenticated LOCAL/FUJI as well as MOCK, displays Check/Compile/risk verdicts, readable signed Phi, certified reservation vs realized loss/gas, reverse cap/disabled label and PRE-SIGN ONLY exposure. Operator credential stays in tab memory. Pending workflow reads are polled without re-execution.
QA: `node --check apps/dashboard/app.js` PASS. Two headless Chrome journeys PASS: actual mock workflow to confirmation; LOCAL UI with replayed real V2 integration responses, proof/counters on desktop/mobile. Screenshots inspected in `.control-data-ui/` (ignored). In-app Browser runtime bootstrap failed (`node:process` import restriction); a fresh temporary headless browser profile was used, without user browser/session data.

## Phase 5 / DONE (implemented local security matrix)
49 Foundry tests include original 27 and 22 V2 tests: all 15 signed-field mutations, Phi/calldata/chain tamper, replay, owner access, pause/revoke/expiry, reverse enabled/disabled, duplicate/missing registry, allowance cap, exact deltas, malicious adapters/reentrancy, 700+200+200 day race, session/global exhaustion, no session recycling, UTC scope, atomic rollback and fuzzed budget invariant. Full before/after balances/counters/nonces are asserted.
Root Python: 73 passed, 0 failed; existing 33 preserved; proof math/corner enumeration, rational witnesses, tolerance fallback, hash/source/registry/oracle mutation, freshness, malformed calldata, UNKNOWN, resource bounds, concurrent deterministic proofs, SDE V1+V2 gates, attestor proof/session/call mutation and additive DB migration.
Execution Python full suite: 46 passed, 0 failed, 1 skipped (opt-in ablation, run separately below). Separate final targeted `uv run --directory apps/execution-plane python -m pytest tests/test_ab_integration.py tests/test_v2_execution.py -q`: 9 passed (includes real A/B processes, V1 normal/replan/stale/pending, V2 forward/reverse/stale, guarded proof -> relayer and actual local reorg rollback).
Remaining limitations: no general adversarial token semantics or formal proof of the Solidity implementation; unaudited scope. Two Python dependency deprecation warnings per environment; compiler warnings arise from OpenZeppelin future keyword/lint checks. No baseline tests were removed. Intermediate new-test failures (expectRevert helper ordering, timestamp caching, reverse checksum conversion and digest dispatch) were corrected and final replacements pass.
CI: existing workflow installs both locked environments, runs Forge/B Python/cross-language vectors/secret scan, root A/proof Python, lint and frontend syntax; no dependency on local PGS folder or Fuji credentials.

## Phase 6 initial checkpoint / PARTIAL (superseded by completion above)
Files: opt-in `test_v2_ablation.py`, complete deterministic V1 gate subprocess, `scripts/benchmark-v2-proof.py`, raw JSON and `docs/evaluation/v1_vs_v2_1_ablation.md`.
Commands: PowerShell `$env:RUN_V2_ABLATION='1'` then `uv run --directory apps/execution-plane python -m pytest tests/test_v2_ablation.py -q` - 1 passed, 0 failed (163.12 s). `uv run --locked python scripts/benchmark-v2-proof.py` - 128 fixtures, 80 verified, 48 conservative refusals, 0 unknown.
Observed: above-minOut/below-Phi output drift commits under V1 and reverts under upgraded guards; a third small in-policy trade is refused by certified reservation cap. Normal receipt gas 178596 / 202823 / 202835 / 242671 for V1 / Phi / PGS / PGS+budget. Proof sweep p50/p95/p99 = 9.55/17.72/19.62 ms on this machine/run. See denominators and raw results; do not infer population APR or throughput.
Limits: benchmark uses complete deterministic V1 gates + current V1-compatible vault entrypoint and private local test signatures, while application attestor/monitor correctness is tested separately. Original-bytecode gas isolation, full application-protocol ablation and fine-grained stage timings have NOT been measured. Simulation/extraction are combined. B and C have equal runtime outcomes in this small suite. These limits keep the full evaluation release gate PARTIAL, rather than claim an unjustified full paper reproduction.
Exact next evaluation action: expand the matched harness to full attestor/monitor timings and an isolated original-commit deployment; retain the same threat fixtures and V1 gates, then regenerate the report. Optional runtime exposure remains explicitly not implemented.

## Fuji / BLOCKED_EXTERNAL_DEPENDENCY
No owner-approved V2 risk/session/reverse parameters or explicit funded V2 cutover were supplied. Test-only values were never applied to Fuji; no deployment/smoke/address/transaction hash is claimed. Existing private environment values were not printed or used to sign Fuji transactions.
Next action: owner reviews explicit parameters, supplies a separate V2 profile via secure environment, funds test AVAX and authorizes new deployment; then follow `v2_1_runbook.md` and retain real guarded normal/revert/replay/budget receipts on verified chain 43113.

## Initial release gate status (superseded above)
A: local inventory/baseline/Git discipline PASS.
B: conditional formal model, exact arithmetic and cross-language bindings PASS under documented assumptions.
C: local signing/runtime/budget regression gate PASS.
D: local E2E and UI PASS; Fuji BLOCKED_EXTERNAL_DEPENDENCY.
E: measured small guard ablation/liveness sweep available; full original-commit/protocol performance gate PARTIAL as described above.
PGS reference remains present locally, root-ignored, and `git ls-files -- Proof-Gated-Signing` returns no entries. No commit, push, secret change or live Fuji migration was performed.


## Final regression additions
V2 exposure and directional-cap REPLAN now preserve the V1 journey: a rejected candidate does not need a proof to request a fresh intent, while every APPROVE still requires all proof obligations. Real two-process tests cover 500-USDC exposure reduction and 20-WAVAX reduction to the explicit 10-WAVAX test cap; both passed. No signature is issued for the first candidate.
The final signed Phi/debit is re-simulated through baseline AND the fixed mild/adverse stresses, using the owner-required stress outcomes. Its artifact commits those requirements and scenario receipts. A real fork test with zero tolerance verifies refusal when the final Phi fails a mandatory mild stress, with no writes to source-chain balances/nonces/counters. This closes the liveness difference between exploratory Phi and final compiled Phi.
Timeline records economic evaluation before proof results. Final follow-up commands: `uv run --directory apps/execution-plane python -m pytest tests/test_ab_integration.py -k v2 -q` (5 passed); `uv run --directory apps/execution-plane python -m pytest tests/test_v2_execution.py -q` (3 passed); root full suite (73 passed); shared/control lint, JS syntax, V1/V2 golden vectors and diff whitespace checks PASS.


## Earlier command results (before operator tooling)
- `npm run check`: PASS. Forge 49 passed / 0 failed / 0 skipped; execution Python 46 passed / 0 failed / 1 skipped in 217.61 s. The sole skipped quantitative ablation is opt-in and was executed separately with 1 pass. Both V1/V2 viem golden scripts PASS. Secret scan PASS, 181 files checked, no configured-secret leaks.
- `uv run --locked python -m pytest -q`: 73 passed / 0 failed / 0 skipped in 9.80 s.
- Explicit Ruff check of changed control code, proof/resource tests and all new shared modules: PASS. `node --check apps/dashboard/app.js`: PASS. `git diff --check`: PASS.
- Final mobile headless dashboard journey: PASS to CONFIRMED with no JS page errors. Earlier desktop/mobile V2 proof/counter screens were checked with recorded actual local integration responses.
- Git: PGS ignore rule resolves at root `.gitignore`; root index contains zero PGS files; local README still exists. User input plan remains unchanged. See `v2_1_changed_files.md` for the complete 72-file change list.
No runtime or security parameters were added to the user's existing `.env`. No Fuji transaction was sent. Local UI smoke server is stopped after verification.
