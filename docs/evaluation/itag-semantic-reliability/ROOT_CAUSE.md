# Root cause investigation

Baseline 6f4137c7e7a3f002308a988e24d0358af0b096ca.

The historical recorder retained the raw verdict and validator reason codes, but discarded the rejected response. Therefore an exact offending ID or field cannot be recovered for those calls. Assigning a particular namespace error to each row would fabricate evidence. The graphs and successful factual claims remain inspectable in the original replication report.

| Case | Prevalidation | Failed rule | Available diagnosis |
|---|---|---|---|
| lh001 | ALIGNED | ITAG_UNBOUND_FINDING | At least one candidate/task/source/reference binding predicate failed |
| lh002 | MISALIGNED | ITAG_UNBOUND_FINDING | Same compound predicate, rejected IDs unavailable |
| lh003 | ALIGNED | ITAG_UNSUPPORTED_FACTUAL_CLAIM | Field/value, cited node or outcome trust failed; rejected claim unavailable |
| lh004 | MISALIGNED | ITAG_UNBOUND_FINDING | Same compound predicate, rejected IDs unavailable |
| lh009 | ALIGNED | ITAG_UNBOUND_FINDING | Same compound predicate, rejected IDs unavailable |
| lh010 | ALIGNED | ITAG_UNSUPPORTED_FACTUAL_CLAIM | Same factual predicate, rejected claim unavailable |

The evidence contract requires separate node, extracted-task and evidence-ref namespaces. An authenticated IntentSpec node has terms and revision, but active_task_ids contains model-extracted instructions with source USER and trust MODEL_JUDGMENT. Both have kind AUTHENTICATED_USER_INTENT. A provider can reasonably select the authoritative spec and still fail the extracted-task validator. USER attribution additionally requires one of those extracted instructions as a cited node. Receipt claims require VERIFIED_RECORD; a receipt-shaped payload with UNVERIFIED trust remains insufficient. Base-unit strings must match exactly.

The response JSON schema extends SemanticFinding with optional factual_claims, then removes that field before DTO validation. This is compatible but unnecessarily asks the model to repeat addresses and financial quantities. Known evidence refs with omitted source nodes qualify for one repair. Unknown identities and factual errors fail immediately. The replication's four logical calls per case show that no citation repair was performed.

Correction selected before source edits: a graph-bound alias catalog, a small semantic selection schema, deterministic canonical reference construction, exact quoted text anchors for the objective and candidate rationale, and typed optional claim validation. Preserve the legacy strict response validator for existing clients and fixture regressions. Model prose remains explicitly unverified semantic interpretation. New metadata records the exact grounding error code without retaining arbitrary rejected provider text.
# Root cause follow-up from retained diagnostic responses

The historical six responses cannot be reconstructed exactly. New v3.0 diagnostic calls retained sanitized parsed outputs on synthetic inputs and exposed the repeated cause. On lh001 the model selected its extracted task and the candidate, while omitting the operator IntentSpec. On lh002 it did the same across two task relationships. Both failed CATALOG_OBJECTIVE_UNSUPPORTED despite plausible semantic prose.

The v3.2 failures are now inspectable in FINAL_LIVE_RESULTS.json. On lh010 repetition 1 an extra supporting_aliases_note violated the schema. On lh003 repetition 2 and lh010 repetition 2 the model selected extracted tasks and omitted IntentSpec, causing CATALOG_OBJECTIVE_UNSUPPORTED. On lh004 repetition 2 Task Shield intervened upstream, so no graph inference occurred. All four retained interventions are excluded from validated semantic-only lift.
