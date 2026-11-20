# Chain/RPC adapter

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`Chain`, `contract`, `artifact`, `plain` in `__init__.py`.

Loads compiled artifacts/deployment manifests, validates chain identity and reads vault policy, balances, nonce/session state. New chain readers belong here. Never silently change networks or trust a manifest without deployed-code validation.

Depends on execution storage/errors/settings and the shared protocol package as needed. It must not import control signing or operator commands. New subcomponent tests can live in `tests/` beside the implementation; retain end-to-end execution regressions.

```sh
uv run --locked python -m pytest backend/tests/execution -q
```

Run from the repository root with native Foundry/artifacts available. See [execution overview](../README.md) for storage, key boundaries and protocol-review requirements.
