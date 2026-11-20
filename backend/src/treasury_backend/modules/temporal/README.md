# temporal — Intent-Aware Temporal Action Graph (ITAG)

Owns authenticated per-intent terms, revision/cancellation, cross-workflow budgets and ordered dependencies. The deterministic verifier reads reservations and reconciled outcomes from SQLite; the semantic evaluator consumes the graph using the active Task Shield provider. Model output can veto or escalate, never create authorization.

Files: `models.py` graph/spec/assessment DTOs; `intent_spec.py` scope validation; `storage.py` additive immutable history and atomic approval checks; `graph_builder.py` provenance graph; `verifier.py` budget/order/outcome gates; `semantic_evaluator.py` bounded LLM assessment; `fusion.py` strongest verdict; `explainer.py` explanations; `service.py` feature orchestration; `api.py` operator-authenticated endpoints and viewer. Shared `IntentSelection` is defined in core to preserve dependency direction. Scripted replay infrastructure lives in `operations/itag_benchmark.py`, not in this runtime module.

Workflow evaluation saves an assessment hash. The attestor reservation and final SUBMITTING transaction revalidate its hashes, active revision, history/ledger, task revision and PRE snapshot links. Model calls occur outside SQLite write transactions. Economic risk, PGS proof and Solidity checks remain mandatory. Existing V2 proof hashes and contract ABI are unchanged.

`PACEVANT_REQUIRE_ITAG=0` preserves existing workflow compatibility; set `1` to require a structured intent on all workflows/signing paths. ITAG workflows also require active Task Shield and an actual operator credential even in MOCK. `/itag` provides the read-only graph viewer when frontend serving is enabled. Viewer assets live at `frontend/itag*`; token stays in tab memory.

Verify with `python -m pytest backend/tests/control/test_itag.py backend/tests/execution/test_itag_unified.py -q` inside the locked environment. Scripted semantic tests are not evidence of model accuracy. The V2 Anvil integration currently establishes fail-closed behavior for oversized simulation artifacts, not successful ITAG-protected live execution. See [current integration](../../../../../docs/integrations/ITAG_MAIN_SYNC.md).
