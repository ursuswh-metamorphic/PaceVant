# Inspect an ITAG decision

Open `/itag` in the Control Plane dashboard origin. Enter an assessment hash and the operator bearer token. The graph shows typed outgoing edges and distinguishes authenticated records, verified outcomes, model inferences and untrusted observations. Select a highlighted node to inspect its provenance, Task Shield checks, violations and recovery. The viewer sends the token in the request header and holds it in the form for the current page.

| Endpoint | Evidence |
| --- | --- |
| `GET /v1/itag/intents/{spec_id}` | Current structured objective and superseded revisions |
| `GET /v1/itag/intents/{spec_id}/history` | Scoped receipt ledger, history version and assessment hashes |
| `GET /v1/itag/assessments/{hash}` | Immutable graph, semantic and deterministic findings, hybrid verdict, recovery, SDE decision and current outcome projection |
| `GET /v1/itag/assessments/{hash}/nodes/{node_id}` | Node, directly related edges, original Task Shield reports and localized violations |

Data endpoints require the existing operator token. The graph records evidence available at assessment time. The current candidate's SDE decision and later outcome are separate response fields. When another workflow is assessed under the same intent, its graph can include prior decisions, their assessment hashes and relevant outcomes. An older explanation stays unchanged after reconciliation invalidates an outcome. The latest outcome shown by the API is a separate projection.

## Edge validity

| Edge | Evidence and meaning |
| --- | --- |
| `AUTHORIZES` | Authenticated mandate/intent binding, passing deterministic candidate scope and budget, or a prior signed decision under that intent |
| `DERIVED_FROM` | Stored user message/task extraction, bound simulation or actual snapshot input |
| `EVALUATED_BY` | Persisted Task Shield check records or a prior SDE decision |
| `CONTRIBUTES_TO` | Model inference with a positive Task Shield score, original task ID, extracted instruction ID and check ID |
| `DEPENDS_ON` | An authenticated input used by the workflow or a verified prerequisite identified in the current intent |
| `PRECEDES` | Ledger evaluation order |
| `EXECUTED_AS` | Transaction hash recorded in receipt evidence for the prior action |
| `PRODUCED_OUTCOME` | Explicit decision/outcome binding or recorded tool call/output ID |
| `UPDATED_STATE` | Post-execution snapshot named in the outcome |
| `SUPERSEDES` | Immutable intent revisions with a stable ID |

Interpret provenance and trust together. Temporal order alone establishes no causal link. Tool observations and model-inferred contribution carry no spending authority. Each Shield report preserves source identifiers, prompt version, model, scores and explanations. The trajectory report carries separate provider metadata and explicit graph references.

For example, a candidate repeating a completed one-shot step points to the active IntentSpec and a matching earlier successful receipt through `ITAG_STEP_ALREADY_COMPLETE`. The model can still rate the repeat as aligned. The deterministic verdict is sufficient for the SDE to reject it. If the earlier receipt becomes uncertain because of a reorg, the explanation identifies the outcome that needs reconciliation.

Structural grounding checks confirm that cited node, task and evidence IDs exist and that evidence references belong to cited nodes. A model can still draw an incorrect semantic conclusion from valid references. The persisted graph and complete reports allow a reviewer to check that conclusion.
