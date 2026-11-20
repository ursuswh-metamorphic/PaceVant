# Evaluation tools

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`benchmark_proof.py` measures the bounded shared proof engine. `evaluate_protocol.py` compares V1 and V2.1 local protocol behavior using isolated Anvil nodes, original V1 API processes and the current single-app V2.1 process. `protocol_server.py` loads either the archived V1 app layout or current package layout; role backend instruments both module groups in one app; retain this version-aware distinction for fair historical comparisons. `v1_gates.py` is a pre-sign gate helper.

```sh
uv run --locked python tools/evaluation/evaluate_protocol.py --help
# Rerun without overwriting historical checked-in measurements:
uv run --locked python tools/evaluation/evaluate_protocol.py --output .control-data-v2/protocol-results.json
uv run --locked python tools/evaluation/benchmark_proof.py
```

The proof sweep writes docs/evaluation/v2_1_proof_sweep.json; run it only when intentionally regenerating that evidence. The full protocol benchmark is opt-in, requires Git access to the fixed V1 commit, native Foundry/artifacts and local free ports. It must not read the user's Fuji secrets or send testnet transactions. Evidence/report locations and interpretation are documented in [evaluation](../../docs/evaluation/v1_vs_v2_1_ablation.md). Existing checked-in results predate the module refactor unless their metadata explicitly says otherwise; do not claim a rerun from path-only changes.

LOCAL four-mode ablation is opt-in: set RUN_V2_ABLATION=1, optionally V2_ABLATION_OUTPUT=.control-data-v2/ablation.json, then run `uv run python -m pytest backend/tests/execution/test_v2_ablation.py -q`. It never requires Fuji credentials. To preserve historical proof sweeps use `uv run python tools/evaluation/benchmark_proof.py --output .control-data-v2/proof-sweep.json`.
