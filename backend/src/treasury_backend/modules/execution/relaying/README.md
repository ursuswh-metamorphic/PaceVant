# Durable relaying

Canonical demo composition injects an optional `gas_credit` port. Only builds bound to accepted demo requests use it: reserve `gasLimit*gasPrice` in the same SQLite transaction as the send journal, check the actual relayer pending balance and refuse before broadcast on insufficient credit or fee cap. Demo gas limit is estimated +10% +5000; operator behavior is unchanged. A journaled demo retry only monitors its existing hash; it never automatically rebroadcasts. Settlement is handled by the existing outcome monitor using verified receipt gas, including reverts. [Detailed accounting/reorg/runbook](../../../../../../docs/demo/DEMO_USER_GAS_CREDIT.md).

`Relayer` in `relayer.py`.

Consumes signed PDRs and exact stored builds. Verifies bindings/live state, final preflight and idempotency, journals signed bytes before sending, then reconciles receipts/reorgs. Only the relayer key pays gas. Never blindly rebroadcast after an uncertain send or report confirmation before required receipts.

Depends on execution storage/errors/settings and the shared protocol package as needed. It must not import control signing or operator commands. New subcomponent tests can live in `tests/` beside the implementation; retain end-to-end execution regressions.

```sh
uv run --locked python -m pytest backend/tests/execution -q
```

Run from the repository root with native Foundry/artifacts available. See [execution overview](../README.md) for storage, key boundaries and protocol-review requirements.
