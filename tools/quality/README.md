# Quality checks

`scan_secrets.py` compares tracked/unignored source against actual local env secrets without printing their values, checks ignore rules and writes a public summary under evidence/. It must scan newly added files too. `check_frontend.mjs` checks syntax of every browser JS module; Node is developer-only.

```sh
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python tools/quality/scan_secrets.py
node tools/quality/check_frontend.mjs
```

Ruff exclusions preserve existing execution/SDK style. Do not run broad formatters against ignored reference repositories, dependencies or virtual environments. Architecture boundaries are tested under backend/tests/architecture.
