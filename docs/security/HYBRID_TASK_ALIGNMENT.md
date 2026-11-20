# Hybrid Task Alignment Shield

The previous `TaskShield.check()` authorized a candidate when the sum of nonnegative
ContributesTo scores exceeded epsilon. A positive deadline contribution could compensate
for a zero score on the requested token pair. This is unsuitable for mandatory financial
constraints. The sum algorithm is retained only for explicitly labelled scripted/offline
historical replay. Real providers cannot use it to authorize a wallet action.

## Decision and trust boundaries

The default algorithm is `hybrid-v1` for all enabled Shield modes. LLM extraction still
decomposes authenticated instructions into semantic tasks. `TaskState.user_update()` stores
the original authenticated message, canonical task IDs, revision and structured envelope
atomically. Structured constraints are anchored to original text, not to a model paraphrase.
The bounded source grammar is an interpretation ceiling: missing/ambiguous operation, asset,
amount, temporal or minimum-output requirements are unresolved rather than invented.
Unsupported wording and conditional/approximate authorization need clarification.

`IntentEnvelope` contains the raw source, authenticated task identities, revision, operation,
constraints and unresolved requirements. Each `Constraint` carries source span/reference,
operator, unit, normalized value, ambiguity and extraction method. AI task decomposition is
a proposed interpretation, not an independent grant of authority. The deterministic grammar
is intentionally narrower than unrestricted natural language; this can reduce coverage.

Assistant/tool content never calls `user_update()` or supplies protocol metadata. Only the
operator-authenticated entrypoints do so. Immutable events persist the interpretation.
Partial cancellation deactivates the whole original message scope until its full constraints
are reauthorized. REPLACE/CANCEL invalidate earlier check revisions.

The existing authenticated ITAG IntentSpec and TransferTask remain the structured authority
sources. Internal adapters intersect swap step limits with raw user constraints, and attach
the already authenticated transfer token/recipient/amount ceiling/task revision. A conflicting
exact user amount is not silently reduced to satisfy a different budget. The original raw
objective remains available to semantic evaluation. These adapters have no assistant/tool or
public context-update route. ITAG authorization refs are committed as evidence, not signed
through a new payload field.

## Candidate and binding contracts

Registered adapters normalize supported router calls and wallet proposals into operation,
chain, addresses, integer amounts, protective minimum, deadline, source vault and call type.
Candidate display symbols, human amounts and candidate-provided decimals are not authority.
All amounts use integers/Decimal with enlarged precision. Invalid ABI integers/addresses,
native wrapper direction and known router/chain incompatibilities produce typed failures.
Opaque financial calls cannot establish a fresh authorization.

For each active authenticated message scope the verifier computes its complete constraint
set. A unique compatible scope binds the candidate; unrelated tasks are not required to
contribute. Multiple plausible scopes yield UNCERTAIN. No compatible authorized scope yields
MISALIGNED. Explicit parent-task selection still has to identify a currently active scope.
`TaskBinding` commits the task/source/revision/action/catalog references and verdict.

`ConstraintResult` records constraint ID/type, USER_INTENT/TECHNICAL/METADATA boundary,
expected requirement, observed value, PASS/FAIL/UNKNOWN, violation code and evidence refs.
User requirements do not replace mandate, economic-risk or technical gates.

USD comparison requires declared authoritative price context. A one-cent tolerance is used
only when explicitly authorized in the authenticated text and supplied context. Quotes are
not inferred from candidate data. A larger minimum output satisfies a lower protective bound;
execution fillability remains a separate simulation/risk question. Missing required quotes
yield UNKNOWN. Production native transfer execution has no registered PolicyVault adapter;
it cannot receive approval through this component. The existing execution path remains ERC-20.

## Semantic evidence and fusion

One structured semantic call replaces contribution-scoring inference, rather than adding a
five-call agent. It receives the bound original objective, proposed decomposition, candidate,
deterministic results and evidence catalog. It checks objective relevance, unauthorized goal
substitution, injection, drift, contradictions and residual semantic conditions. It does not
redo financial arithmetic. Read-only prerequisites can indirectly support a bound objective.

`SemanticFinding` binds task ID, action alias, finding type, verdict, explanation and citations.
Task/action identities and every citation must exist in the supplied catalog. Source and
candidate citations are mandatory. Hashes use opaque aliases so credential redaction does
not erase model-facing IDs. Raw hashes remain in durable reports. Invalid schema, fabricated
citations, provider failure or uncertainty cannot become positive evidence.

Fusion is explicit:

1. Any mandatory FAIL or unauthorized binding gives MISALIGNED.
2. Ambiguous/unresolved binding or any critical UNKNOWN gives UNCERTAIN.
3. Validated semantic MISALIGNED gives MISALIGNED.
4. Missing/uncertain semantic evidence gives UNCERTAIN.
5. Only a valid binding, all required PASS and aligned semantic evidence give ALIGNED.

Proven deterministic failures short-circuit inference; inference availability cannot override
the veto. No positive contribution score grants authority. Extraction plus a non-vetoed
candidate normally requires two total model calls. Diagnostic legacy scores are not used
in hybrid authorization.

## Wallet integration and failure handling

Existing interception, task sessions/revisions, immutable reports, ITAG provenance/fusion,
SDE, simulation, risk, proof and PolicyVault remain enabled. `UNCERTAIN` is a new unsigned
report status; runtime maps it to unavailable/clarification feedback and the existing
Alignment UNCERTAIN/SDE escalation contract. Paper input feedback remains persisted; it is
never an approval. Hardened/pipeline modes block uncertain or misaligned tool output.

Attestor revalidation now additionally requires an aligned hybrid report with a valid binding,
all constraint results PASS and an exact hash of the approved proposal input. A benign content
check, empty check list, stale revision, old algorithm or report for another proposal cannot
form that proof. Rejected evaluations may still persist diagnostic proof bundles; only the
attestor consumes them as potential approvals. Execution rechecks current policy/proof/intent
after its final Shield interception. Transfer SDE/signing checks require ALIGNED too.

No EIP-712 fields, Solidity interfaces, PDR encoding or on-chain authorization were changed.
Direct execution still requires a valid action-bound signed approval and replay protection.

## Evidence limits

The frozen 300 Uniswap cases exercise read-only component inference with explicitly synthetic
quote context. They cannot execute on the LOCAL/Fuji wallet. Baseline and gold files are
unchanged. A/B/C/D comparisons, uncertainty, typed-family localization and root-cause analysis
are in `docs/evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md` and the adjacent error report.
This inspected corpus is a regression set, not an untouched generalization test.
LOCAL Anvil tests exercise supported swaps and ERC-20 transfers with explicitly scripted AI;
real-model component measurements and scripted end-to-end security tests are separate claims.
