# Live Demo — Security Observability & Evidence UX Upgrade

## Baseline and scope

Verified 21 November 2026 (Asia/Saigon): `/opt/pacevant/current` points to
`16e4d68437e74fceb1fe41281e05d99490465837`. The deployment script fetches
`origin/develop`; `main` and `develop` currently share that commit. The VPS
source tree is clean. Implementation branch: `feat/live-demo-security-evidence`.
Existing local agent/skill directories are untracked and outside this change.

This work does not deploy, merge into production, broadcast public transactions,
change Solidity/security algorithms/PDR schemas, rotate authority, transfer funds,
or modify existing execution databases and journals.

## Implementation checklist before edits

| State | Existing capability / finding | Action |
|---|---|---|
| Already implemented | Twelve-step pipeline, input/processing/output drawers, real `timeline` and append-only `activity` | Reuse; keep module names and current transaction behavior |
| Already implemented | Four historical Fuji probes with successful controls and exact revert selectors | Reuse `attack_evidence`; show signature integrity scope precisely |
| Already implemented | Real ITAG graph, source trust, references, semantic verdict, SDE | Render actual nodes/edges without inventing history |
| Already implemented | Risk expected/observed checks, Z3 queries/compiled Phi, public signed operation fields, receipt gas ledger | Use these as the source for explanations |
| Implemented but poorly presented | Summary truncates actual AVAX expense to six decimals; evidence uses different precision | One exact formatter; missing and invalid remain unavailable |
| Implemented but poorly presented | Historical probe inherits public execution environment labels and generic policy verdict | Place execution/evidence scope before verdict; signature integrity is not semantic detection |
| Implemented but poorly presented | ITAG is a text list; binding matches are difficult to audit; verdict has no direct gate navigation | Add interactive provenance graph, explicit comparison states, gate links |
| Implemented but poorly presented | Risk and Z3 facts exist mainly deep inside drawers | Add concise, expandable evidence views using current checks |
| Missing presentation artifact | Small real-model purpose-conflict research is not available in the web UI | Export only verified, source-bound research observations and caveats |
| Missing presentation artifact | Long-horizon budget example exists in LOCAL Anvil evidence, not the current UI | Show recorded 10 + 10 USDC confirmations and the blocked third candidate under a 20 USDC task budget |
| Missing / conditional evidence | No self-contained, verified MEV comparison has yet been selected | Inspect artifacts; add only if baseline/stress/assumptions/verdict can be sourced |

## Validation and delivery

All P0 items and the evidence-backed P1 items are implemented. No backend evidence
changes were necessary. Research displays are separate from the active visitor
job and do not create execution requests. MEV comparison remains conditional:
no artifact with a complete baseline/stress/assumptions/outcome comparison was
selected, so no MEV performance figures are presented.

## Implemented behavior and evidence mapping

| UX | Actual source | Presentation / trust boundary |
|---|---|---|
| Actual gas in summary, facts and receipt | `outcome.system_gas_expense.actual_cost_wei` | One BigInt formatter preserves all 18 decimals; missing/malformed → unavailable; literal zero → zero. Simulation gas is never substituted. The recorded payment has a null expense; the recorded swap has `69722560` wei → `0.00000000006972256 AVAX`. |
| Scope before verdict | `execution_kind`, `attack_evidence.method`, `environment`, recorded workflow environment | Historical calls remain HISTORICAL FUJI ETH_CALL even when their source environment is public Fuji. Replay and research scope remain explicit. Unavailable history rows use warning color. |
| Contract probe details | `attack_evidence` + original workflow intent | Control, seed transaction, canonical receipt flag, source/control blocks, operation, mutation before/after, original-signature reuse, expected error and observed selector. A successful control and matching selector establish the expected contract rejection. BadSignature is signed-data integrity, not semantic or specialized slippage/router detection. |
| Verdict → real gate / receipt | Backend `active_stage`; confirmed outcome | Opens the existing stage drawer. Confirmed links to stage 12. Without a recorded gate, opens evidence instead of guessing a gate. |
| Interactive ITAG | Existing `ITAG.graph` / `ITAG_GRAPH` activity evidence | Actual nodes and edges only; authenticated, verified, model-inferred and unverified sources have distinct labels/colors. Current candidate uses its source identifier; shield observations are not mislabeled as the candidate. Node inspection, keyboard selection, zoom and fit are available. |
| Risk table | Latest RISK activity checks with both `expected` and `observed` | Expandable check/expected/observed/verdict table. No invented rows or recalculated limits. Payment principal, trading loss and gas remain separate. |
| Z3 and Φ | PROOF / PROOF_REJECTION, existing solver queries, assumptions, Φ and hashes | SAT establishes feasible assumptions; violation queries require UNSAT; UNKNOWN does not authorize. The guarantee is conditional on the bounded assumptions and compiled Φ. |
| Six-link evidence chain | Proof intent/evidence/Φ/proof hashes; attestation public signed fields; confirmed `VAULT_EFFECTS` observation | Intent → simulation → Z3/Φ → signed PDR → PolicyVault → receipt. Each link shows an identifier, explicit match/mismatch/missing state, and expandable public comparison fields. Missing fields never match. Hash equality is not represented as a new cryptographic verification. |
| Long-horizon sequence | `docs/evaluation/itag-final/ANVIL_BUDGET_ISOLATION.json` | Recorded LOCAL Anvil, chain 31337, scripted model, zero public broadcasts. 10 + 10 USDC confirm against a 20 USDC task budget; third 10 USDC candidate has Risk PASS / Proof VERIFIED but ITAG REJECT, SDE REJECT and `signed=false`. Step buttons only select records. |
| Purpose drift | `docs/evaluation/itag-semantic-reliability/FINAL_LIVE_RESULTS.json`, `lh002`, repetition 1 | Real-model research with synthetic history. Authenticated goal: acquire WAVAX exclusively for gas; candidate reason: training inventory. Deterministic PASS, semantic MISALIGNED, hybrid SDE REJECT. No public execution is claimed. |
| Research metrics | `EXPERIMENT_CATALOG.md` and semantic `FINAL_REPORT.md` | 95.67%/300 adapted Uniswap V2 cases, equal constraints-only baseline; scripted 8/12 interventions and 12/12 benign approvals; small real-model 7/8 purpose observations and 16/19 valid graph responses. No combined score, accuracy uplift, generalization or graph-versus-plain-history superiority claim. |

The research export includes source paths, immutable source-commit links and
SHA-256 fingerprints of the Git blobs (UTF-8/LF). The exporter verifies local
source content against the linked commit, including Windows newline
normalization. `--check` verifies reproducibility. Invalid/missing showcase data
does not render the fixed research narrative. Raw views recursively exclude
signatures, signed transactions, private keys and credential fields.

## Changed files

| Files | Purpose |
|---|---|
| `frontend/src/app/App.tsx` | Lazy research tab and navigation to existing gate dialogs |
| `frontend/src/app/components/attack-select.tsx` | Accurate historical signature-integrity / replay wording; still exactly two presets per operation |
| `frontend/src/app/components/evidence-facts.tsx`, `evidence.tsx` | Unified gas, sanitized raw evidence, scope, receipt/risk/formal/binding views |
| `frontend/src/app/components/execution-panels.tsx` | Scope before verdict, actual gate action, exact gas, probe detail, risk comparisons, warning status |
| `frontend/src/app/components/module-detail.tsx`, `module-process.tsx` | Preserve inputs/processing/outputs and activity; integrate graph, formal scope, risk and bindings |
| `frontend/src/app/components/pipeline.tsx`, `run-session.tsx` | Open the actual selected stage; label historical session scope before its status |
| `frontend/src/app/components/site-chrome.tsx`, `frontend/src/app/styles.css` | Four-tab indicator and readable mobile navigation |
| `frontend/src/app/workflow-detail.css` | Wrap long reason codes without hiding them or overflowing mobile drawers |
| `frontend/src/app/components/itag-graph.tsx` | Existing React Flow dependency reused for provenance graph and accessible record selection |
| `frontend/src/app/components/security-evidence.tsx`, `security-evidence.css` | Shared evidence views, source scope, risk/formal/receipt and six-link binding chain |
| `frontend/src/app/components/security-research.tsx` | Read-only recorded budget/purpose cases, metrics and source links |
| `frontend/src/app/lib/format.ts`, `security-evidence.ts` | Exact gas, source/graph projection, comparison states, redaction and showcase version validation |
| `frontend/src/app/lib/security-evidence.test.ts`, `security-components.test.ts` | Precision, missing data, actual probe/receipt rendering, bindings and research trust regressions |
| `frontend/public/evidence/security-research.json` | Reproducible selected-source research artifact; no signing capability |
| `tools/quality/export_security_research.py` | Source-bound offline export; no RPC/model/signing/execution |
| `tools/quality/check_security_evidence_ux.py` | Local browser QA using recorded responses; rejects non-GET judge requests |
| This report and `docs/audit/security-ux-upgrade-20261121/` | Review evidence, screenshots and QA results |

No dependencies, API routes, authority, sessions, security algorithms, PDR
schemas, Solidity or existing historical artifacts/journals were changed.

## QA results

- TypeScript and production Vite build: PASS.
- Frontend: **72 tests passed / 7 files**, including all 34 pre-existing tests.
- Existing backend judge/API/public-mode/adversarial/local/metrics regressions:
  **23 passed**, with two dependency deprecation warnings. No backend files changed.
- Export reproduction and source-commit verification: PASS.
- Ruff on both new Python quality tools: PASS.
- Configured-secret scan: [PASS](security-ux-upgrade-20261121/secret-scan.json);
  no leaked files; secret paths remain ignored. The scanner's generated report
  was copied here and its pre-existing historical output restored unchanged.
- Browser: Chromium against the production build on localhost; six saved cases,
  VI/EN, 1440×1080 desktop, 390×844 mobile and 768px research tablet checks.
  Keyboard Enter/Escape, actual gate, scope, evidence drawer, history, reload,
  recovery by original request key, missing history and long reason codes are
  covered. Research graphs preserve exactly the source nodes and edges.
- Browser result: [qa.json](security-ux-upgrade-20261121/qa.json), zero page errors
  and zero judge write requests. The report records build/artifact fingerprints.
- `git diff --check`: PASS.

The browser harness supplies recorded `/judge` GET responses and explicitly
rejects writes. Normal CONFIRMED cases below are re-renders of existing public
receipts, not transactions executed by this task. UNAVAILABLE/UNKNOWN/RUNNING,
missing-history and interrupted-recovery fixtures are synthetic UI robustness
checks, not new security experiment results. The full backend/Solidity suites
were not rerun for this frontend-only change.

| Required regression | Evidence |
|---|---|
| Normal payment / swap confirmed | Both saved acceptance jobs rendered; receipt stage opened |
| Replay → NonceReplay | Saved payment-replay selector and successful control |
| Amount / minOutput / router → BadSignature | All three saved probes render exact before/after and revert evidence |
| Oracle unavailable is not attack detection | Warning state, explicit unavailable dependency result; no passed gates |
| Missing model response is not approval | UNKNOWN/partial-workflow fixtures and existing fail-closed tests |
| Missing proof is not MATCH | Unit/component tests require six missing states without source hashes |
| Small positive gas is not zero | Exact formatter cases and actual swap receipt in browser |
| Missing history does not create history | Exactly three supplied nodes / one edge; no outcome nodes invented |
| Partial workflow shows only recorded results | Empty timeline/activity stays unverified; no passed nodes synthesized |

## Screenshots and visual review

Before captures are the committed production baseline from the earlier acceptance
audit; they are not a new live run. After captures are local recorded-response
renders. Brand colors, logo, typography and the three-phase pipeline remain.

| Surface | Before | After |
|---|---|---|
| Payment desktop | [Baseline](live-adversarial-20261121/colors-vps-success/payment-desktop.png) | [Updated](security-ux-upgrade-20261121/payment-desktop-en.png) |
| Historical probe desktop | [Baseline](live-adversarial-20261121/colors-vps-success/payment-amount-desktop.png) | [Updated](security-ux-upgrade-20261121/payment-amount-desktop-en.png) |
| Historical gate detail | Existing activity/input/output drawer | [Source-scoped probe detail](security-ux-upgrade-20261121/payment-amount-gate-en.png) |
| Payment mobile | [Baseline](live-adversarial-20261121/colors-vps-success/payment-mobile.png) | [Updated VI](security-ux-upgrade-20261121/payment-mobile-vi.png) |
| Research desktop | New read-only surface | [VI](security-ux-upgrade-20261121/research-desktop-vi.png), [EN](security-ux-upgrade-20261121/research-desktop-en.png) |
| Research mobile | New read-only surface | [VI](security-ux-upgrade-20261121/research-mobile-vi.png), [EN](security-ux-upgrade-20261121/research-mobile-en.png) |

Visual QA found and fixed graph fitting from collapsed sections, multiple false
candidate highlights, long-code drawer overflow, and crowded four-tab mobile
navigation. Graphs mount when their recorded section opens and refit when their
container resizes. Detailed graph node text remains available through zoom and
the keyboard record list. Expanded comparison tables scroll within their own
container on small screens.

## Self-review, limitations and remaining work

The overview explanation and existing inputs/process/output flow remain intact.
The long-horizon examples demonstrate both cumulative accounting and purpose
alignment with their distinct evidence scopes. Every main claim links to recorded
source fields or a repository report; JSON is behind explicit inspection controls.
Hash equality displays compare recorded commitments; the browser does not issue a
new cryptographic attestation or grant authority.

The semantic results use a small synthetic-history research set, repeated wording
pairs and provisional labels, without independent human review. The seventh of
eight validated purpose observations is a report-level finding; one observation
was stopped upstream and earns no graph-model detection credit. Three of nineteen
graph responses were invalid. These are not general detection accuracy figures.
Deterministic interventions include replan/escalate and do not imply semantic
detection. Twelve workflow steps are not twelve independent security modules.

The long sequence is a replayable three-candidate LOCAL Anvil recording, not a
new batch execution feature or a public Fuji semantic attack demo. Public assets
were not moved and no funds needed resetting in this task. A public cumulative
sequence, new research trials, production session soak, external ablation and an
independently reproducible MEV comparison remain outside this authorized scope.
The UI cannot reconstruct a missing receipt expense or absent event commitment;
these remain unavailable. The static research artifact is loaded only on the
research tab and includes complete selected graphs; it is about 600 KB before
HTTP compression. The existing main JS bundle remains above Vite's 500 KB warning
threshold; the build also retains the dependency's `use no memo` directive warning.

## Production rollout checks (not performed here)

Review this feature branch and its source-bound artifact, verify the target
release/branch again, and serve `/evidence/security-research.json` as a static
asset with the new frontend bundle. Check caching/asset delivery, VI/EN navigation,
history/recovery and source-specific scopes against read-only production records.
If a later deployment is authorized, keep runtime `.env`, databases, journals,
authority and policy/session configuration intact and retain the current release
for rollback. This delivery contains no merge or deployment.
