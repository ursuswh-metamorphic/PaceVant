# Treasury feature

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`index.js` exports `loadTreasury`, which queries mandate/snapshot data through the shared API client and renders treasury, exposure and risk budget facts. Update this folder for treasury cards/owner policy visibility. Backend state remains authoritative; frontend must not compute an approval or alter policy limits to enable a button.

The module uses native browser imports. Keep paths relative and preserve public exports consumed by app.js. Test syntax with `node tools/quality/check_frontend.mjs`, then exercise the affected UI flow through HTTP. See the [frontend guide](../../../README.md) for local startup, API URL configuration and deployment.
