# Workflow feature

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`index.js` exports `display` and renders stages, attempts, alignment/risk/proof decisions, signatures and receipt evidence. Update this folder for workflow visualization. Polling/submission stays in app.js. Distinguish protected rollback, submitted and confirmed outcomes; never infer confirmation from a successful POST alone.

The module uses native browser imports. Keep paths relative and preserve public exports consumed by app.js. Test syntax with `node tools/quality/check_frontend.mjs`, then exercise the affected UI flow through HTTP. See the [frontend guide](../../../README.md) for local startup, API URL configuration and deployment.
