> Technical reference imported from main@70bf6c7. Upstream metrics and 30-second TTL statements describe that branch. See [current modular integration and limitations](integrations/ITAG_MAIN_SYNC.md) for this checkout.

# ITAG gap analysis

Baseline is main at `08c35df`. Task Shield persists per-workflow user objectives, candidate contribution scores and sanitized context. Its sum rule permits positive contributions unrelated to actual execution, as recorded in the Xingchi wrong-chain case. A report with no extracted instructions also lacks a candidate row. ITAG needs explicit source metadata even for these reports and a separate objective-consistency judgment.

The current SDE checks alignment, evidence and economic risk. Each workflow can independently request a valid swap, so the existing per-swap and daily Vault rules do not enforce completion or total spending for a particular user intent shared across workflows. SQLite already serializes nonce reservations, and the Outcome Monitor already maintains canonical outcome projections and versioned portfolio observations. ITAG will reuse these sources and the same signing transaction to enforce intent budgets, outcomes, dependencies and revisions.

The planner currently supports one swap shape. An authenticated intent API will authorize a fixed swap or a sequence of independently checked swaps. An ordered step can depend on another verified swap outcome. User revisions require an explicit authenticated request. Task Shield and the trajectory evaluator will use the same provider. Model output may veto or explain decisions. Authorization edges will come from verified intent and candidate bindings.

Implementation order is intent lifecycle and SQLite history, deterministic graph and verification, semantic evidence and fusion, signing integration, then authenticated graph inspection and benchmark replay.
