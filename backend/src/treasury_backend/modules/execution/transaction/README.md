# Transaction builder

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

Import `Builder` from `treasury_backend.modules.execution.transaction.builder`; implementation is in `builder.py`.

Consumes shared proposals and live policy context; produces an immutable `BuiltTransaction` binding router, token pair, amount, nonce and exact calldata. New supported transaction types need an explicit protocol extension, simulator/extractor and contract review. Do not allocate a new transaction for an idempotent retry.

Depends on execution storage/errors/settings and the shared protocol package as needed. It must not import control signing or operator commands. New subcomponent tests can live in `tests/` beside the implementation; retain end-to-end execution regressions.

```sh
uv run --locked python -m pytest backend/tests/execution -q
```

Run from the repository root with native Foundry/artifacts available. See [execution overview](../README.md) for storage, key boundaries and protocol-review requirements.
