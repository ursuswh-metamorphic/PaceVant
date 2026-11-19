# Frontend

Static HTML/CSS and browser ES modules. No Node.js server, bundler or wallet extension is required to use the dashboard. Node is optional for developer syntax/vector checks only.

| Folder | Owns |
| --- | --- |
| `src/app.js` | Startup, connect/run forms and workflow polling |
| [src/api](src/api/README.md) | Authenticated backend requests and error mapping |
| [src/shared](src/shared/README.md) | DOM, formatting and tab-local state |
| [src/features/treasury](src/features/treasury/README.md) | Mandate, portfolio and risk budget display |
| [src/features/workflows](src/features/workflows/README.md) | Attempt/timeline/decision/proof/receipt display |
| `assets/` | Styles and public `config.js` |

## Local development

`uv run --locked treasury local` serves this directory at http://127.0.0.1:8000 through the unified Python API. `uv run --locked python -m treasury_backend.api.serve` runs MOCK without chain access. Do not open index.html through file:// because ES module loading requires HTTP.

The operator token is entered in the connect form and kept only in tab memory, never config.js or browser persistence. LIVE/FUJI actions call authenticated backend endpoints. No owner/attestor/relayer keys belong in frontend code or hosting variables.

## Independent deployment

`frontend/Dockerfile` copies only this folder into Nginx and proxies `/healthz`, `/v1/`, `/v2/` to `$BACKEND_URL`, default `http://backend:10000`. Serve frontend and API at one browser origin with [compose](../compose.yaml); no CORS configuration is necessary.

For a static host without an API proxy, publish this directory and set the public value in `assets/config.js`:

```js
window.TREASURY_CONFIG = {apiBaseUrl: "https://your-backend.example"};
```

Set `PACEVANT_CORS_ORIGINS=https://your-frontend.example` on the backend. Origins are comma-separated exact HTTP(S) origins, with no path or wildcard. Use HTTPS for public hosts and `PACEVANT_SERVE_FRONTEND=false` on an independent backend. config.js contains only the public API URL and has no-store caching in the provided Nginx config.

## Extend and verify

Add a new capability under `src/features/<name>/` with a narrow exported renderer/loader and its README. Reuse `api/client.js`; avoid direct fetch calls or secrets in a feature. Render untrusted display values with textContent; do not insert server-provided HTML.

```sh
node tools/quality/check_frontend.mjs
uv run --locked python -m pytest backend/tests/integration/test_frontend_boundary.py -q
```

Browser checks should exercise MOCK scenarios and a local chain workflow. CORS and static asset tests do not alone prove browser rendering. See [deploy guide](../deploy/README.md).
