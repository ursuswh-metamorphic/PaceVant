# Treasury feature

`index.js` exports `loadTreasury`, which queries mandate/snapshot data through the shared API client and renders treasury, exposure and risk budget facts. Update this folder for treasury cards/owner policy visibility. Backend state remains authoritative; frontend must not compute an approval or alter policy limits to enable a button.

The module uses native browser imports. Keep paths relative and preserve public exports consumed by app.js. Test syntax with `node tools/quality/check_frontend.mjs`, then exercise the affected UI flow through HTTP. See the [frontend guide](../../../README.md) for local startup, API URL configuration and deployment.
