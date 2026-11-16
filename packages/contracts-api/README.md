# Shared integration contract v1.1

Schema and EIP-712 follow `docs/03_SHARED_INTEGRATION_CONTRACT.md`. This directory is shared ownership: A and B must review changes before merging.

Install from A's Python project:

```powershell
uv add ../../packages/contracts-api
```

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
