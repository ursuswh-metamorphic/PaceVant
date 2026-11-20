# Intent binding for the operator dashboard

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`workflowRequest(mandate, goal, scenario)` checks `/health`. If ITAG is required it obtains a validated proposal, creates an operator-authorized `ONE_SHOT_SWAP` with an exact base-unit amount, and returns the workflow payload with `spec_id`, revision and step. API credentials remain in the shared in-memory client; wallet keys never enter this module.

The current ITAG demo supports the mandate's USDC-to-WAVAX direction. It rejects reverse requests before intent creation; it does not silently change amount or direction. HTTP failure is surfaced to the operator. There is no automatic workflow POST retry, wallet signing, or broadcast here. Each intentional run creates a new spec; completed intents cannot be replayed for another signature.

Runtime/backend behavior, phase checks, configuration and limitations: [current system design](../../../../docs/AI_Treasury_Security_System_Design_v2.1.md). The [earlier Fuji ITAG runbook](../../../../docs/demo/FUJI_ITAG_LIVE.md) retains historical scope. Syntax check: `node --check frontend/src/features/intents/index.js`; Node is only optional developer tooling, not a backend service dependency.
