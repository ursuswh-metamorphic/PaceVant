# Quality checks

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`scan_secrets.py` compares tracked/unignored source against actual local env secrets without printing their values, checks ignore rules and writes a public summary under evidence/. It must scan newly added files too. `check_frontend.mjs` checks syntax of every browser JS module; Node is developer-only.

`check_documentation.py` validates the current documentation manifest, status banners, local current links/anchors, source fingerprints and artifact/catalog integrity. It makes no RPC/model calls and does not load private env or application lifespans. Historical missing evidence targets are reported separately; it does not invent replacement evidence. Refresh the source inventory/catalog/manifest deliberately after runtime changes; do not ignore a stale-fingerprint error.

```sh
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python tools/quality/scan_secrets.py
uv run --locked python tools/quality/check_documentation.py
node tools/quality/check_frontend.mjs
```

Ruff exclusions preserve existing execution/SDK style. Do not run broad formatters against ignored reference repositories, dependencies or virtual environments. Architecture boundaries are tested under backend/tests/architecture.
