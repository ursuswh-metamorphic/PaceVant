# API client

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`client.js` exports `api(path, options)`. It resolves the public API base from `window.TREASURY_CONFIG`, applies the tab-memory bearer token, refuses redirects and maps the backend error code to an Error. Keep all API calls here so features share credential handling. No keys, tokens or private RPC URLs belong in config.js. Changes to a route also require the backend/shared contract review.

The module uses native browser imports. Keep paths relative and preserve public exports consumed by app.js. Test syntax with `node tools/quality/check_frontend.mjs`, then exercise the affected UI flow through HTTP. See the [frontend guide](../../README.md) for local startup, API URL configuration and deployment.
