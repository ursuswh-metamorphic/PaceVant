# Durable relaying

`Relayer` in `relayer.py`.

Consumes signed PDRs and exact stored builds. Verifies bindings/live state, final preflight and idempotency, journals signed bytes before sending, then reconciles receipts/reorgs. Only the relayer key pays gas. Never blindly rebroadcast after an uncertain send or report confirmation before required receipts.

Depends on execution storage/errors/settings and the shared protocol package as needed. It must not import control signing or operator commands. New subcomponent tests can live in `tests/` beside the implementation; retain end-to-end execution regressions.

```sh
uv run --locked python -m pytest backend/tests/execution -q
```

Run from the repository root with native Foundry/artifacts available. See [execution overview](../README.md) for storage, key boundaries and protocol-review requirements.
