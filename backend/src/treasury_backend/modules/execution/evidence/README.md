# Execution evidence extraction

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`token_facts` and `assess` in `extractor.py`.

Combines receipts, traces, token transfers and before/after balances into deterministic execution facts. Protected rollback is different from actual asset loss. Missing/mismatched facts must not be promoted to success. New adapters require trace and token-delta cases here.

Depends on execution storage/errors/settings and the shared protocol package as needed. It must not import control signing or operator commands. New subcomponent tests can live in `tests/` beside the implementation; retain end-to-end execution regressions.

```sh
uv run --locked python -m pytest backend/tests/execution -q
```

Run from the repository root with native Foundry/artifacts available. See [execution overview](../README.md) for storage, key boundaries and protocol-review requirements.
