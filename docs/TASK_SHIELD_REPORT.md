> Imported technical reference from `origin/main` at `08c35df`. Adapted paths below use the modular Python backend. Historical test counts/live metrics in this document belong to upstream; see [current merge verification](integrations/MAIN_SYNC_2026_11_20.md) for this checkout. The current `.env` explicitly sets Task Shield to `disabled`; `paper`/`wallet_hardened` are opt-in. The current Fuji Circle-USDC/Chainlink/PDR-V2 authorization path is supported; blanket Fuji valuation blockers below describe upstream faucet-USDC only.

# Task Shield implementation report

Baseline: `main` at `53180f7b1af3202bba24dfbfd871612cd4c4d786`. Implementation branch: `codex/task-shield-paper`. [Inspection before implementation](TASK_SHIELD_INSPECTION.md) · [Methodology, trust boundaries and configuration](TASK_SHIELD.md).

This is the original pre-provider report for commit `e082e95`. The user subsequently supplied an authorized Xingchi provider; see the [new setup and live-validation report](XINGCHI_TASK_SHIELD.md). Historical NOT_RUN entries below describe the original run, not the later provider setup.

**Verification boundary:** the user explicitly chose “Triển khai trước, ghi rõ chưa chạy đánh giá LLM thật”. No real LLM inference, AgentDojo benchmark, public Fuji transaction or new deployment was performed. The implementation uses a real configurable chat-completions adapter in production; test providers are isolated scripted fixtures. Their scores do not demonstrate semantic detection accuracy. No component is accepted as an empirically reproduced defense merely because a scripted provider test passes.

## A. Repository changes

| File | Purpose |
|---|---|
| `backend/src/treasury_backend/modules/alignment/__init__.py` | Retain explicitly labelled legacy guard; expose deterministic wallet constraints separately from LLM alignment |
| `backend/src/treasury_backend/modules/alignment/types.py` | Source/message/instruction/contribution/report/feedback/update schemas |
| `backend/src/treasury_backend/modules/alignment/prompts.py` | Attributed Figure 4–7 methodology adaptations, versioned independently |
| `backend/src/treasury_backend/modules/alignment/provider.py` | Provider/model/config, bounded HTTP, privacy serialization, usage/latency |
| `backend/src/treasury_backend/modules/alignment/state.py` | Persistent session/task revisions and immutable user/message/context/check/event audit |
| `backend/src/treasury_backend/modules/alignment/engine.py` | LLM extraction, strict score matrix, sum/epsilon Algorithm 1, feedback, proof validation |
| `backend/src/treasury_backend/modules/alignment/runtime.py` | Before-call and after-output enforcement, assistant checks, paper/hardened distinction |
| `backend/src/treasury_backend/modules/alignment/api.py` | Authenticated session/task/check/audit endpoints; no execution/permission endpoint |
| `backend/src/treasury_backend/api/control/__init__.py` | Route installation, active-shield authentication, legacy alignment endpoint delegation |
| `backend/src/treasury_backend/core/models.py` | Add shield implementation version to existing Alignment response enum |
| `backend/src/treasury_backend/config/control.py`, `.env.example` | Explicit modes and provider parameters; LOCAL/FUJI environment default fails closed without configured model |
| `backend/src/treasury_backend/modules/workflows/service.py` | Actual user extraction, assistant/tool/output gates, bounded feedback replanning, final execute check and immutable approval binding |
| `backend/src/treasury_backend/modules/workflows/client.py` | SDK evidence-artifact interception without bypassing hash verification |
| `backend/src/treasury_backend/modules/workflows/evidence.py` | Optional artifact gate at the existing evidence consumption boundary |
| `backend/src/treasury_backend/modules/planning/service.py` | Existing rules planner receives feedback and creates a fresh mandate-bound candidate |
| `backend/src/treasury_backend/modules/persistence/service.py` | Atomic task-revision check when ATTESTED starts SUBMITTING |
| `backend/tests/control/test_task_shield.py` | Algorithm, provider protocol, persistence, trust/auth, failures, wallet control-flow and attack fixtures |
| `backend/tests/execution/test_ab_integration.py` | Preserve five existing cases and add active-shield HTTP-provider protocol case |
| `backend/tests/integration/task_shield_provider_fixture.py` | Loopback provider fixture used by that A+B process test; explicitly not an LLM |
| `fixtures/task_shield/wallet_cases.json` | Labelled local benign/adversarial cases for future live evaluation |
| `tools/evaluation/evaluate_task_shield.py` | Opt-in real-provider local-case evaluation; no wallet keys or transactions; NOT_RUN without provider |
| `docs/TASK_SHIELD_INSPECTION.md`, `docs/TASK_SHIELD.md`, this report | Findings, plan, fidelity/extensions, operation, limits and verification |
| `README.md`, `docs/README.md` | Documentation entry points |
| `evidence/task-shield-validation.json` | Machine-readable test/evaluation boundaries and results |

The shared SDK, EIP-712 format, Solidity contracts, mandate semantics, economic-risk policy and outcome monitor implementation are unchanged. There is no Temporal Action Graph implementation in this baseline, and none was added.

## B. Component coverage

“Implemented and integrated” below describes actual runtime wiring, not successful empirical reproduction on a real model. LLM-semantic validation remains explicitly partial/deferred across the LLM components.

| Component | Implementation status | Evidence and remaining validation |
|---|---|---|
| User instruction extraction | Implemented and integrated | Real provider adapter called by workflow start and authenticated user-message API; JSON/schema/retry/provenance tests. Semantic extraction by an actual LLM not run. |
| User Task Set | Implemented and integrated | SQLite persists/restarts, multiple tasks, exact dedup, dependencies preserved in text, explicit APPEND/REPLACE/CANCEL, expected revision and USER-only updates; sessions isolated |
| ContributesTo scoring | Implemented and integrated | Distinct content/tool prompts; complete per-task numeric matrix, Decimal sum, `<= epsilon`, default 0; zero/small-positive/indirect/malformed tests. Real scoring quality not evaluated. |
| Assistant content check | Implemented and integrated | Existing planner rationale checked before build; blocked content/calls receive feedback. No general conversational assistant has been added. |
| Tool call check | Implemented and integrated | Actual invocation helper gates build/simulate/reads; separate final execute check. Tests assert callbacks do not run when denied, including after SDE approval. |
| Tool output check | Implemented and integrated | Quote/build/simulation/portfolio/artifact response boundaries checked before consumption; paper preserves output+feedback, hardened quarantines; no objective mutation |
| Feedback generation | Implemented and integrated | Machine-readable warning, instructions, reasons, task reminders and tool provenance passed into planner and context |
| Replanning | Implemented and integrated for existing wallet planner | Fresh intent, revalidation, bounded planning/output retries separate from economic replans. General-purpose LLM planning is outside the existing architecture. |
| Config/logging | Implemented and integrated | Explicit modes, fixed original model default, temperature 0, timeout/retries/context/epsilon, sanitized audit and usage/latency; no estimated cost invented |
| Existing wallet gate compatibility | Implemented and integrated | Deterministic failures still stop positive scripted alignment; final proof blocks cancellation/config drift/pending feedback and direct-attest bypass |
| Real-model local-case evaluation | Partially implemented | Runnable CLI/cases, no configured provider per user choice; CLI verified to report NOT_RUN rather than metrics |
| AgentDojo evaluation | Not implemented | No adapter/full benchmark execution; this wallet rules planner is not an AgentDojo agent, and no inference credentials were configured |

No component is “implemented but not integrated” as an unused substitute shield. The two evaluation rows remain unfinished empirical work and are not included as reproduced security results.

## C. Fidelity and explicit extensions

Follows the paper: task extraction from USER/ASSISTANT/TOOL, original user objective set, LLM contribution reasoning against every user task, direct/indirect/no contribution, zero-threshold default, separate tool-call prompt, input/output shielding, original output plus feedback in reproduction mode, assistant feedback/replan and temperature 0.0. Core prompts preserve dependency extraction, original task text, source hierarchy and parameter checking.

Extensions: strict JSON/score identity validation and bounded retries; task revisions/cancellation/authentication; deterministic wallet gates and final signing proof; secret redaction/JSON-provenance context; wallet_hardened quarantine; finite retry/application budgets; SDK artifact interception; shared SQLite linearization. Prompts are adapted and omit the paper's inconsistent illustrative field alias/score example in favor of its stated scoring rules. There is no claim of byte-for-byte original implementation.

Tiny positive scores remain accepted with epsilon 0. This known weakness is tested and documented rather than silently replaced with a 0.5 policy. A configurable epsilon change is identified as an extension. No keyword/embedding classifier substitutes for the core LLM method. The old regex exists only in explicitly selected legacy_fixture mode and is not counted as paper reproduction.

## D. Tests and observations

| Command / environment | Result |
|---|---|
| `uv run --locked python -m pytest -q` (root A/shared) | 152 passed, 1 opt-in public Fuji read skipped |
| `uv run --locked python -m pytest backend/tests/control/test_task_shield.py -q` | 59 passed using scripted provider responses/protocol fixtures |
| `npm run test:python` (isolated WSL checkout / Anvil) | 67 passed, 2 opt-in Fuji fork tests skipped; includes six A+B cases |
| `npm run test:contracts` | 37 passed |
| `npm run test:integration` | Python ↔ TypeScript EIP-712/golden compatibility PASS |
| `uv run --locked ruff check .`, `ruff format --check .` | PASS |
| `npm run scan:secrets` | PASS |
| `python tools/evaluation/evaluate_task_shield.py` without provider | NOT_RUN, expected exit 2; no fabricated metrics |

On this Windows machine, the equivalent root command used the prepared environment's `python.exe -m pytest` because executable shims may be blocked by Application Control. WSL tests use a separate checkout and temporary Anvil deployments, not user wallet keys, the existing dashboard DB or public Fuji writes. Existing tests were retained; A+B baseline cases explicitly identify legacy-fixture mode, and the additional case tests the active shield adapter over HTTP.

Important observed behavior:

- A complete legitimate wallet task traverses active shield interception, the existing SDE/PDR path and real Anvil execution/reconciliation with a scripted HTTP provider. This verifies wallet integration, not actual GPT-4o extraction or detection accuracy.
- Seven adversarial message fixtures supplied explicit zero-score provider responses and were stopped by shield control flow while transaction fields remained within the mandate. They establish correct enforcement of the returned scores, **not that an LLM detected those attacks**.
- Positive scripted scores do not override deterministic recipient/mandate rejection. Reports distinguish that policy failure from a shield detection.
- A final execute denial prevents SUBMITTING and the callback, even after earlier SDE APPROVE/ATTESTED. A task cancellation after SDE invalidates the signing proof. Pending feedback in paper mode cannot be bypassed by directly attesting an older APPROVE record.
- Tool output misalignment reaches planner revision, creates a different intent and checks the replacement. Repeated failures stop at the configured bound. Provider/parser failure never becomes an ALIGNED result for sensitive actions.
- Original wallet PDR/nonce/TTL/risk/oracle constraints remain enforced. The LLM is not asked to grant permission and cannot mutate tool arguments or user authority through its response schema.

| Requested evaluation metric | Current evidence |
|---|---|
| Real attack success rate / AgentDojo ASR | Not measured |
| Legitimate real-model task utility | Not measured |
| Real-model false positive / false negative rates | Not measured |
| Real-model latency, calls, usage/cost | Not measured; instrumentation implemented |
| Scripted deterministic regression | 59 pass; not converted to model accuracy/ASR |

## E. Remaining work, in priority order

1. Configure the user's chosen provider/model and run the live local-case evaluation. Measure extraction misses, false scores, latency, token usage and unavailable outcomes. Do not infer results from these fixtures or the paper's published numbers.
2. Verify actual model latency against the existing 30-second transaction approval TTL and practical context/trace sizes. Current behavior fails closed on expiry/oversize; this work does not extend TTL to hide the issue.
3. If full benchmark reproduction is required, build/review an AgentDojo-specific adapter, pin benchmark/model versions and run comparable task/attack suites. The local-case CLI is not a substitute benchmark.

No public Fuji deployment/broadcast was needed or performed. This PR does not complete the live A→SDE→PDR→LFJ workflow: trusted USD valuation of LFJ faucet USDC remains unresolved upstream and the existing fail-closed identity check remains in place.
