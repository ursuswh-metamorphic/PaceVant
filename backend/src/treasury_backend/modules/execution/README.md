# Execution

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

Owns chain interaction, exact calldata, fork simulation, extraction and durable relay. It receives a signed approval; the execution module receives only relayer configuration. The unified process also holds the attestor key in the signing module; there is no process-level key isolation. The serving runtime never receives the owner key.

| Component | Responsibility | Entrypoint |
| --- | --- | --- |
| [chain](chain/README.md) | RPC, deployed contract/context reads | `Chain` |
| [dex](dex/README.md) | Exact LFJ token/route/quote identities | `LFJClient` and verified V1 route |
| [transaction](transaction/README.md) | Immutable nonce-bound calldata | `Builder` |
| [simulation](simulation/README.md) | Native Anvil fork, exact guarded execution | `Simulator` |
| [evidence](evidence/README.md) | Receipt/trace/token fact extraction | `token_facts`, `assess` |
| [relaying](relaying/README.md) | Approval checks, durable send/recovery/receipt | `Relayer` |

`service.py:ExecutionService` is the shared facade for direct module calls and HTTP handlers. It owns mutation idempotency/locking and simulation rate limiting, then delegates to the components below.

`storage.py` owns execution idempotency, artifacts and send journals; it is separate from the control database. `models.py` and `crypto.py` re-export the shared protocol for compatibility. `errors.py` defines `PlaneError`. HTTP composition is in `api/execution.py`; operator commands are in `operations/execution.py`.

Use `treasury_contracts` for wire models/hashes/evidence verification. Canonical workflow calls use `api/local_execution.py` without an HTTP connection; `/execution/...` routes are available on the same FastAPI app for authenticated external consumers. Control modules must not import these execution internals. Runtime key: relayer only. Owner deployment is an explicit operator command, outside this module.

```sh
uv run --locked python tools/contracts/foundry.py forge build
uv run --locked python -m pytest backend/tests/execution -q
```

Do not change signed schemas here alone. Review SDK/ABI, workflow and execution adapters, vectors and Solidity together. Keep write-ahead journaling before broadcast, exact retry identity, uncertain-send reconciliation and reorg handling intact. See [backend map](../../../../MODULES.md).
