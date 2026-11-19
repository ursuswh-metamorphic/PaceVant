# Shared integration contract v1.1

Current SDK package version: **1.3.1**, pinned consistently by the root project. Added `ExecutionReconciliation`, `outcomes.py`/`outcomes_v2.py` (read-only V1/V2 receipt/build/PDR/proof verification), `readonly.py` (bounded read-only RPC) and `token_facts.py` (shared receipt parser). `ExecutionClient.snapshot(block_number)`, `.reconciliation(tx_hash)` and `.submission_for_build(build_id)` serve portfolio/outcome monitoring. V2 signed domain and existing proof-engine hashes are unchanged. The unified remote base URL is `http://127.0.0.1:8000/execution`; normal backend workflows use an in-process adapter. The v1.1/1.2 notes below describe the original wire/LFJ additions, not the current package version.

SDK 1.2.0 accepts `adapter_version=lfj-v1-fuji-v1` alongside `mock-swap-v1`. Existing approvals, EIP-712 domains and evidence schema retain their wire encoding. Consumers that validate the adapter enum need SDK 1.2.0 for LFJ builds.

Schema and EIP-712 follow `docs/03_SHARED_INTEGRATION_CONTRACT.md`. This directory is shared ownership: A and B must review changes before merging.

The monorepo backend installs this package automatically with root `uv sync --locked`. An independent consumer can install the package directory/wheel without importing backend internals. See [backend module boundaries](../../backend/MODULES.md).

`proof.py` is the single pure V2.1 proof engine; `v2.py` contains additive V2 models/hashes, `onchain_v2.py` read-only state helpers and `toolchain.py` native binary discovery. Keep this library independent of `treasury_backend`. The v1.1 package version is retained for wire compatibility; ApprovalV2 uses EIP-712 domain version 2.

```python
from treasury_contracts import TransactionProposal, SignedPDR
from treasury_contracts.client import ExecutionClient
from treasury_contracts.crypto import approval_for, domain_for, digest, message

client = ExecutionClient("http://127.0.0.1:8001", api_key=backend_api_key)
built = client.build(proposal, idempotency_key=f"{workflow_id}:build:0")
evidence = client.simulate(built, idempotency_key=f"{workflow_id}:simulate:0")
manifest = client.verify_evidence(built, evidence)
# A now checks alignment, risk, freshness, COMPLETE, source, etc. and stores its decision.
# ONLY A's attestor loads an immutable APPROVE decision and signs approval_for(built, evidence.evidence_root).
# Verification of hashes alone does not authorize execution.
```

`models.py` is the DTO source. `npm run b:schemas` regenerates the committed JSON Schemas. Solidity, Python and viem consume the golden vector in `fixtures/eip712_golden/`; `npm run b:check` checks their agreement.

`npm run schemas` also exports `openapi.json` and the packaged `treasury_contracts/abi/PolicyVault.json` after compiling. `ChainContext`, `OnchainSnapshot`, `ExecutionSubmission`, `ErrorEnvelope` describe the existing read/submission/error responses; `OnchainSnapshot` intentionally contains no USD prices/history.

Use `treasury_contracts.onchain.read_approval_state(rpc_url, built)` to read the exact Vault policy/nonce/attestor/bytecode state at one block before A attests. This helper never signs, submits, or decides APPROVE. The ABI is included when the SDK is installed as a wheel, so A does not need a backend `app` import or local Foundry output to perform these reads.

`ExecutionClient` is synchronous and supports a context manager. `context`, `snapshot`, `execute` return validated dictionaries; `build`, `simulate`, `result` return models. HTTP failures raise `ExecutionAPIError` (also `httpx.HTTPStatusError`) with `.code`, `.retryable`, `.status_code`, `.correlation_id`; transport failures remain httpx exceptions. Set `request_id=workflow_id` on the client to propagate correlation.

Build/simulation retries with the same key/body reuse immutable records. Execution retries use the same journaled signed bytes and hash while returning current status; a dropped RPC broadcast can be retried with the same key. Always poll `result(tx_hash)` instead of assuming POST success means CONFIRMED.

Read the complete [A/B handoff](../../docs/06_AB_INTEGRATION_HANDOFF.md), [AI merge prompt](../../docs/07_AI_MERGE_PLAYBOOK.md), and [compatibility audit](../../docs/08_AB_COMPATIBILITY_AUDIT.md). Run `npm run test:consumer` for a real HTTP test from a separate isolated consumer process. This test has a local ephemeral signer and does not implement or certify A's production SDE.

JSON token amounts/uint256 are decimal **strings**; timestamps are Unix seconds; hashes are lowercase; EIP-712 member names stay camelCase. Backend auth is `X-API-Key`; all POSTs require `Idempotency-Key`. Error responses contain `error.code`, `message`, `retryable`, `correlation_id`.

Artifact refs are relative authenticated `/v1/artifacts/<keccak>` paths. `verify_evidence` checks canonical bytes, evidence/build bindings, report facts and every artifact's content hash. It deliberately does not implement A's SDE, oracle or exposure policy.
