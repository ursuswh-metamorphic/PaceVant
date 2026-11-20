> Imported technical reference from `origin/main` at `08c35df`. Adapted paths below use the modular Python backend. Historical test counts/live metrics in this document belong to upstream; see [current merge verification](integrations/MAIN_SYNC_2026_11_20.md) for this checkout. The current `.env` explicitly sets Task Shield to `disabled`; `paper`/`wallet_hardened` are opt-in. The current Fuji Circle-USDC/Chainlink/PDR-V2 authorization path is supported; blanket Fuji valuation blockers below describe upstream faucet-USDC only.

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

# Task Shield in PaceVant

This extends the existing `treasury_backend.modules.alignment` module and rules planner. It does not add an independent verifier agent or agent framework. Source: [Jia et al., ACL 2025](https://aclanthology.org/2025.acl-long.1435/), Sections 3–4, Appendix B.1/B.2, C.4 and E Figures 4–7. Prompts are attributed adaptations, not byte-identical copies. [Repository inspection/plan](TASK_SHIELD_INSPECTION.md) · [Implementation and validation report](TASK_SHIELD_REPORT.md).

The configured Xingchi Responses integration and subsequent real-model validation are documented in [Xingchi setup/results](XINGCHI_TASK_SHIELD.md). The original report records the earlier validation before a provider was supplied.

## Core behavior and paper fidelity

1. An authenticated actual user message is extracted by an LLM into a JSON array of instruction strings. The extractor includes implicit/nested directives, questions and dependencies in natural language. Exact extracted strings are retained, apart from documented secret redaction. Instructions carry server-assigned source, message/tool/call IDs and timestamp.
2. Only the authenticated USER entry point mutates the persistent user task set. ASSISTANT/TOOL checks never add objectives. A session binds an existing mandate hash and optional workflow ID. Task extraction is not a new financial authorization or a mandate edit.
3. For each candidate instruction, a separate LLM evaluation returns one row per active original user instruction: unchanged text, numeric `ContributeTo score` in `[0,1]`, and reason. Missing/duplicate/extra task rows, bool/string/nonfinite/out-of-range scores and malformed JSON fail validation. Ordinary content uses Figure 5 methodology; structured tool calls use the distinct Figure 6 prompt and exact arguments. A tool call cannot disappear because an extractor returned an empty list.
4. Compute `S(e) = sum(s(e,t))` using Decimal. Mark misaligned when `S(e) <= epsilon`; **epsilon defaults to 0**. A tiny positive score passes at zero, as in the paper. This is a real weakness: an LLM assigning even a slight unjustified contribution can accept a bad action. An explicitly configured positive epsilon is an extension, not the paper default. No hidden 0.5 threshold, embedding, keyword detector or hardcoded wallet score mapping is used in the LLM path.
5. Feedback contains the flagged instruction, deviation explanation, do-not-execute warning, source/tool/call provenance and active user task reminders. There is no automatic task-completion inference, so reminders conservatively include all active tasks as potentially incomplete.

The experiment model defaults to `gpt-4o-2024-05-13`, temperature `0.0`. The paper also used `gpt-4o-mini-2024-07-18` and `gpt-3.5-turbo-0125`. Changing provider/model, updated model behavior, prompt adaptation, privacy processing or application context means this is not a claim of experimental replication. JSON validation and bounded retries are implementation safety extensions. Score values are numeric in the model response and exact Decimal strings in stored/public audit JSON.

## Modes

| Mode | Behavior |
|---|---|
| `paper` | LLM extraction/scoring for user/content/tool calls. Block misaligned assistant/tool calls. Preserve original tool output with feedback in context; pass feedback to the existing planner before a subsequent financial action. |
| `wallet_hardened` | Same core method; additionally quarantine a flagged tool response before returning its value to normal orchestration. Replan from authenticated goals and deterministic mandate, recheck new actions; never turn tool text into user authority. |
| `legacy_fixture` | Explicit original rules-v1 guard for backward-compatible deterministic regression/demo. Not Task Shield paper reproduction, not LLM detection. |
| `disabled` | Skip LLM shield only; retain deterministic intent/mandate/risk/simulation/PDR/PolicyVault controls. Not a shield-protected run. |

Environment-loaded defaults: MOCK uses legacy_fixture, LOCAL/FUJI use paper and require a configured provider for financial workflows. Direct programmatic `Settings()` retains its legacy fixture default for existing isolated tests. Existing A+B regression cases explicitly select legacy_fixture. A separate A+B case runs the complete shield/provider protocol with a clearly named **scripted loopback HTTP provider**, not a model.

## Runtime enforcement

The existing `/v1/workflows/start` receives the user goal. Paper/hardened workflows require an actual operator credential even in MOCK. They create a scoped session and extract the goal before the first intercepted tool call. `_shield_plan` checks generated assistant rationale and proposed build arguments. `_tool` gates actual chain context, build, simulation, balance, portfolio and evidence-artifact calls before their functions run, and checks returned data before normal consumption. The final `execute_approved_swap` call has a dedicated check before SUBMITTING/client.execute.

Feedback goes to `planner.revise`, an extension of the existing rules planner. It issues a new intent ID and mandate-bound candidate, then revalidates it. It does not generate arbitrary new financial tools or goals. Shield retries are bounded (default two, configurable 0..2) per planning/output-repair stage, separately from the existing bounded economic-risk replans. Persistent failures stop. There is no independent AI verification agent. This is a constrained wallet planner integration, not a new general conversational planner.

Before signing, the immutable decision stores successful shield report IDs, task revision, configuration hash, unresolved feedback and exact sanitized proposal. The attestor checks this proof, mandate/workflow binding, active revision and all original deterministic gates while holding its existing nonce reservation. A decision with unresolved feedback cannot be attested directly, including in paper mode. **No LLM/network generation or shield DB write occurs inside the signing transaction.** A cancellation/replacement invalidates a prior proof. The ATTESTED→SUBMITTING transition checks the task revision in the same SQLite write transaction, linearizing cancellation against submission start. Cancellation after a transaction starts cannot undo an already issued PDR or broadcast; on-chain revocation remains the existing policy/nonce mechanism.

After a transaction hash is known, it is saved before output checking. Provider failure or flagged output at that point never causes a replacement broadcast. Existing outcome monitoring resumes read-only. Monitoring and the standalone Fuji Observatory do not need an LLM to read existing outcomes; they do not autonomously plan financial actions.

Positive alignment never bypasses owner mandate fields, exact requested amount bounds, portfolio provenance, LFJ oracle identity, Economic Risk, simulation/stress evidence, SDE, EIP-712 signing, relayer or PolicyVault. LFJ faucet USDC still fails `ORACLE_TOKEN_IDENTITY_MISMATCH`. No contract/PDR migration is introduced. Alignment failures and deterministic policy failures are recorded separately in shield audit vs workflow decisions; tests assert which layer blocked.

## Persistent state and trust

Additive SQLite tables: `shield_sessions`, `shield_messages`, `shield_tasks`, `shield_context`, `shield_checks`, `shield_events`. They are created idempotently on ControlPlane/TaskShield initialization. Existing wallet/portfolio/outcome tables are preserved. Back up a live SQLite DB using the SQLite backup API before an upgrade. No data rewrite or destructive migration is required.

User messages/checks/context/events are append-only with UPDATE/DELETE-blocking triggers. Active tasks are a revisioned projection; original user updates remain immutable. APPEND unions exact extracted text; duplicates do not create additional task rows. REPLACE and CANCEL are explicit authenticated operations with expected revision/CAS; cancellation IDs must belong to the same active session. Dependencies remain in the original natural-language instructions and optional parent provenance. No semantic deduplication or LLM-driven permission expansion occurs.

Context consists of complete messages or atomic tool-call/output pairs, including source and trust tags. The recent bounded suffix never splits a pair. Active user tasks are supplied independently, so truncating history does not erase objective authority. Context-budget exhaustion yields UNAVAILABLE, not assumed alignment. This JSON-provenance history adaptation preserves call/output pairing without pretending to duplicate the exact AgentDojo message truncation implementation in C.4.

This POC has one trusted operator/service boundary, matching the existing API. Sessions are isolated by IDs/workflow and SQL scope; it does not add a multi-tenant end-user account/ownership system. An operator credential grants access to that service's sessions. Do not expose this as a multi-tenant hosted API without a separate authenticated-principal ownership layer.

## Configuration

Set the variables in `.env.example` through the existing environment mechanism. Do not put a key in chat or committed files.

```text
PACEVANT_SHIELD_MODE=wallet_hardened
PACEVANT_SHIELD_PROVIDER=openai
PACEVANT_SHIELD_MODEL=gpt-4o-2024-05-13
PACEVANT_SHIELD_API_KEY=<local service credential>
PACEVANT_SHIELD_TEMPERATURE=0
PACEVANT_SHIELD_TIMEOUT=20
PACEVANT_SHIELD_RETRIES=1
PACEVANT_SHIELD_CONTEXT_CHARS=24000
PACEVANT_SHIELD_EPSILON=0
PACEVANT_SHIELD_MAX_REPLANS=2
```

`openai_compatible` supports an explicitly configured HTTPS endpoint or HTTP loopback `/v1` origin using `PACEVANT_SHIELD_BASE_URL`. OpenAI mode pins the official endpoint, preventing accidental credential forwarding. Model selection is explicit; no automatic model substitution or temperature fallback occurs. Set temperature to `omit` only if that configured model requires it. HTTP is bounded by timeout, 256 KiB response size, 4096 maximum completion tokens and bounded parsing/provider retries. Failed parsing does not echo the malformed output back. Retry feedback requests valid JSON only. Provider errors are sanitized and fail closed.

`PACEVANT_SHIELD_API_STYLE` selects `chat_completions` (default) or `responses`. Responses mode sends structured message input to `/responses`, requests `store=false`, accepts completed assistant output_text only and normalizes input/output token counters to the existing usage schema. Refusals, incomplete responses and unexpected output tool calls fail closed. The base URL is the `/v1` prefix, not a complete `/responses` URL. `PACEVANT_SHIELD_USER_AGENT` supports the provider-required client header; CR/LF and control characters are rejected.

Context budget is explicitly **characters**, not an asserted tokenizer count. Messages are at most 16,000 characters; instructions/tasks are capped; checker calls are bounded per check and the orchestration/retry loops are finite. Oversized outputs are not silently truncated (a trailing injection could be lost); they halt for review. Large trace artifacts may require a larger reviewed context/message-budget implementation. The 30-second signed approval TTL is unchanged: slow LLMs may exhaust it, in which case existing expiry gates refuse signing/submission. Real-provider latency/feasibility must be measured before enabling live workflows; it has not been verified in this task.

Private keys, signatures, authentication/API tokens, signed-PDR bodies, raw transactions and secret-labelled content are removed before prompt/audit serialization. Known credential forms and 256-bit hex strings are redacted conservatively (including non-secret transaction hashes). Public token/recipient addresses and relevant amounts remain for argument checking. This privacy adaptation means audited tool output is the **sanitized original**, while original non-secret financial evidence stays in the existing artifact store. Raw unsafe text is never given USER/SYSTEM privilege. Context is serialized as data under a fixed checker system prompt, but an LLM can still be fooled; provenance tags are not a proof of semantic correctness.

## Authenticated APIs

Use the existing operator Bearer token; new routes always authenticate, including MOCK.

```text
POST /v1/task-shield/sessions
     {mandate_id, content}
GET  /v1/task-shield/sessions/{id}
POST /v1/task-shield/sessions/{id}/user-messages
     {message_id, content, operation: APPEND|REPLACE|CANCEL, expected_revision, cancel_task_ids?}
POST /v1/task-shield/sessions/{id}/check-content
     {source: ASSISTANT|TOOL, content, tool_name?, tool_call_id?}
POST /v1/task-shield/sessions/{id}/check-tool
     {tool_name, arguments, related_content?}
GET  /v1/task-shield/sessions/{id}/audit?limit=50
```

Inspection endpoints never execute a tool or issue permission. They reject USER source on content checks. The legacy `/v1/alignment/check` response retains its shape and delegates to the configured shield; `shield_model_version` adds `task-shield-acl2025-v1` alongside `rules-v1`. Financial decisions use stored server-generated checks, not caller-supplied check results. The shared A/B SDK, wire models and signed format remain unchanged.

Audit records contain session, source, candidate hash/text, user task refs, individual scores/reasons, sum, decision, feedback, revision/config, retries, model/provider, latency and token usage when supplied. They identify scripted tests by explicit model/evaluation labels. They do not fabricate prices or cost: live evaluation accepts user-supplied per-million-token rates for an estimate.

## Validation and evaluation

```powershell
uv run --locked python -m pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
npm run test:python
npm run test:contracts
npm run test:integration
npm run scan:secrets

# Opt-in real-provider local cases; no blockchain submission or wallet key access:
uv run --locked python tools/evaluation/evaluate_task_shield.py --output data/task-shield-live-evaluation.json
```

Without a provider key, the evaluation CLI prints NOT_RUN and exits 2. Local-case metrics distinguish attack acceptance, benign alignment, false positives/negatives, unavailable outcomes, latency, calls and token counts. They are **not AgentDojo ASR or completed-task utility**. AgentDojo evaluation was not run: no real LLM provider was selected/configured, as explicitly requested by the user. The repository's rules planner is not a general AgentDojo tool agent, so this change does not claim an end-to-end AgentDojo adapter or benchmark reproduction.
