# Configuration

`control.py` parses control settings, modes, credentials, storage, oracle paths and explicit CORS origins. `execution.py` parses B_* runtime/deployment profiles. Defaults remain fail-closed for live signing. Do not mix settings parsing with business behavior or read private `.env` files inside feature logic. Use backend_environment from operations: owner keys remain excluded; the unified process holds attestor and relayer keys. Legacy role-specific environment helpers remain for protocol tests. Settings.from_env(require_execution_http=False) does not require the old B URL/token.

See [backend setup](../../../README.md), [module boundaries](../../../MODULES.md) and [environment/deployment](../../../../deploy/README.md).

```sh
uv run --locked python -m pytest backend/tests/architecture backend/tests/control backend/tests/integration -q
```

Run from the repository root. Integration tests need native Foundry. Keep routes, config, deployment composition and feature behavior in their respective folders; add regression cases for any changed security boundary.
