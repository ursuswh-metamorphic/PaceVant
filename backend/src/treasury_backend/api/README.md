# HTTP adapters

`app.py:create_app` is the canonical single FastAPI composition; `serve.py` is its runner. Control handlers live in `control/__init__.py`; `execution.py:create_router` registers `/execution/...` on the same application. `local_execution.py` injects direct execution module calls into workflow. Standalone control/execution factories and serve_control remain only for legacy consumers/tests. Handlers own authentication, input limits, response/error mapping and lifecycle; workflows/execution modules own behavior. No module-level execution app is constructed on import. CORS only enables configured browser origins; it does not replace bearer auth. Control can mount frontend assets locally; deployment can disable them.

See [backend setup](../../../README.md), [module boundaries](../../../MODULES.md) and [environment/deployment](../../../../deploy/README.md).

```sh
uv run --locked python -m pytest backend/tests/architecture backend/tests/control backend/tests/integration -q
```

Run from the repository root. Integration tests need native Foundry. Keep routes, config, deployment composition and feature behavior in their respective folders; add regression cases for any changed security boundary.
