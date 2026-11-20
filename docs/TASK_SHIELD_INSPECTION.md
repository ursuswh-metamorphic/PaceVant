> Imported technical reference from `origin/main` at `08c35df`. Adapted paths below use the modular Python backend. Historical test counts/live metrics in this document belong to upstream; see [current merge verification](integrations/MAIN_SYNC_2026_11_20.md) for this checkout. The current `.env` explicitly sets Task Shield to `disabled`; `paper`/`wallet_hardened` are opt-in. The current Fuji Circle-USDC/Chainlink/PDR-V2 authorization path is supported; blanket Fuji valuation blockers below describe upstream faucet-USDC only.

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

# Task Shield inspection and implementation plan

Baseline: main `53180f7b1af3202bba24dfbfd871612cd4c4d786`. No repository AGENTS.md. Existing A is Python/FastAPI; B is Python/FastAPI/Web3; PolicyVault and adapters are Solidity. Shared SDK 1.3.0, EIP-712 and portfolio/outcome v2 must remain intact. No Temporal Action Graph implementation exists to preserve or extend.

## Actual interception points

| Event | Existing implementation | Planned extension |
|---|---|---|
| User message | Authenticated POST `/v1/workflows/start`, `WorkflowRequest.goal` | Extract actual goal into workflow-scoped persistent user task set; separately bind mandate |
| Assistant plan | `planner.propose`, rules-v1, no general LLM agent | Check generated proposal rationale/content, retain existing planner |
| Tool proposal/authorization | Direct `client.build/simulate` and `client.execute` calls from orchestration | Pre-call Task Shield check with exact sanitized arguments; write still requires all SDE/PDR checks |
| Tool execution/output | RestExecutionClient / MockExecutionClient, SDK artifacts, Fuji readers | Checked invocation helper in existing orchestration; output extraction before data consumption; preserve raw sanitized output for audit |
| Replanning | `_run_attempts`, bounded mandate replans for economic risk | Separate bounded shield retry, feedback passed into existing planner revision callback; every new candidate rechecked |
| Signing/submission | Immutable decision + transactional nonce reservation + live state verification | Bind successful shield evidence to task revision/config/proposal and check staleness before signing/submission; no LLM/network work inside SQLite reservation |

Existing `alignment.check()` combines mandate checks, exact goal amount and injection regex. It is a deterministic legacy guard, not the paper method. Extend this module with LLM extraction/scoring and preserve deterministic wallet validation separately. There is no existing LLM provider abstraction or generic tool registry to reuse. Add one small typed provider adapter and explicit invocation middleware, not a new agent/verification framework.

## Implementation order

1. Typed extraction/check/feedback models, versioned prompts based on Appendix E Figures 4–7; ContributesTo sum and `<= epsilon` with default zero. Bounded JSON retries, no keyword/embedding fallback.
2. SQLite session/user-message/task/check audit, source provenance, append/replace/cancel revisions, strict USER-only updates via authenticated entry points, isolated sessions and bounded context.
3. Existing orchestration integration: assistant check, pre-tool interception, input shield, feedback to planner retry, final decision proof binding. Paper mode retains original output with feedback; wallet_hardened additionally halts flagged output consumption.
4. Provider/config/limits/redaction, operational APIs, deterministic regression and agent-flow tests. Existing fixtures are explicitly labelled legacy or scripted-provider tests, never evidence of real LLM detection.
5. Optional live regression CLI/AgentDojo adapter only if feasible, paper-fidelity/limitations report with reproducible counts. User explicitly selected implementation first without live LLM evaluation. No public blockchain writes, no changes to oracle/risk/PDR/contracts.

Sources: Jia et al., ACL 2025, [paper](https://aclanthology.org/2025.acl-long.1435/), Sections 3–4, Appendix B/C.4/E. Exact experiment models: gpt-4o-2024-05-13 and gpt-4o-mini-2024-07-18; temperature 0.0. Application-specific modes, retry bound, privacy constraints and stricter parsing will be documented separately. No claimed reproduction of reported ASR/utility without the matching experiment.
