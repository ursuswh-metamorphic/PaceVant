# HTTP adapters

`demo.py` adds one scoped `/v1/demo/*` adapter with a separate demo access credential. It authenticates exact one-shot intent terms and calls the existing ControlPlane pipeline; it does not grant operator/internal/execution privileges. `app.py` injects the gas ledger into the relayer and existing outcome monitor. See [API/flow/billing design](../../../../docs/demo/DEMO_USER_GAS_CREDIT.md). Demo wallet private keys are not needed or forwarded.

`app.py:create_app` is the canonical single FastAPI composition; `serve.py` is its runner. Control handlers live in `control/__init__.py`; `execution.py:create_router` registers `/execution/...` on the same application. `local_execution.py` injects direct execution module calls into workflow. Standalone control/execution factories and serve_control remain only for legacy consumers/tests. Handlers own authentication, input limits, response/error mapping and lifecycle; workflows/execution modules own behavior. No module-level execution app is constructed on import. CORS only enables configured browser origins; it does not replace bearer auth. Control can mount frontend assets locally; deployment can disable them.

See [backend setup](../../../README.md), [module boundaries](../../../MODULES.md) and [environment/deployment](../../../../deploy/README.md).

```sh
uv run --locked python -m pytest backend/tests/architecture backend/tests/control backend/tests/integration -q
```

Run from the repository root. Integration tests need native Foundry. Keep routes, config, deployment composition and feature behavior in their respective folders; add regression cases for any changed security boundary.
