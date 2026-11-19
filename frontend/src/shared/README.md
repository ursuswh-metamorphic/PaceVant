# Shared browser primitives

`state.js` contains tab-only connection/mandate/mode state. `dom.js` contains element lookup and error display. `format.js` contains escaping and integer/unit display helpers. Keep these helpers independent of business features to prevent circular imports. Use textContent/escaping for untrusted data and avoid floating-point money calculations in authorization; browser values are display only.

The module uses native browser imports. Keep paths relative and preserve public exports consumed by app.js. Test syntax with `node tools/quality/check_frontend.mjs`, then exercise the affected UI flow through HTTP. See the [frontend guide](../../README.md) for local startup, API URL configuration and deployment.
