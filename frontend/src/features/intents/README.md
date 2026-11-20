# Intent binding for the operator dashboard

`workflowRequest(mandate, goal, scenario)` checks `/health`. If ITAG is required it obtains a validated proposal, creates an operator-authorized `ONE_SHOT_SWAP` with an exact base-unit amount, and returns the workflow payload with `spec_id`, revision and step. API credentials remain in the shared in-memory client; wallet keys never enter this module.

The current ITAG demo supports the mandate's USDC-to-WAVAX direction. It rejects reverse requests before intent creation; it does not silently change amount or direction. HTTP failure is surfaced to the operator. There is no automatic workflow POST retry, wallet signing, or broadcast here. Each intentional run creates a new spec; completed intents cannot be replayed for another signature.

Runtime/backend behavior, phase checks, configuration and demo limitations: [Fuji ITAG runbook](../../../../../docs/demo/FUJI_ITAG_LIVE.md). Syntax check: `node --check frontend/src/features/intents/index.js`; Node is only optional developer tooling, not a backend service dependency.
