# Transfer milestone report

The operator prioritized successful transfer execution and paused dataset selection/evaluation. No 300-row manifest or dataset model evaluation was created. The downloaded source remains ignored under .tools and was used only for schema/count inspection before the pause.

The LOCAL flow completed through the canonical API and configured DeepSeek Flash. A task authorized an exact 20 USDC payment to a registered recipient. The model produced TRANSFER_ERC20, Task Shield and graph semantics returned ALIGNED, temporal/risk checks passed, Z3 verified exact simulated deltas, SDE approved, the attestor signed, and PolicyVault confirmed the payment on Anvil.

The successful real-model receipt is transaction 0x72fb7a1e9a3f22c8e46c3857efbe6eb6d522fc6e364331afac852940b29d2154 in LOCAL Anvil block 18. Recipient delta was 20,000,000 base units. Gas used was 288,971, with actual cost 320,993,826,486,308 wei. This hash belongs to the disposable local chain and has no public explorer receipt.

The first real-model attempt failed closed because its ALIGNED semantic output omitted the operator scope citation. The catalog now exposes objective_aliases explicitly and the prompt explains which scope must be selected. Both attempts are retained. The successful run proves this single path with a real model; it does not establish a general semantic detection accuracy.

Scripted Anvil scenarios confirmed a 20 USDC transfer, rejected an unauthorized recipient without signing, and confirmed 30 USDC followed by a rejected second 30 USDC payment under a 50 USDC task budget. Same-request retries return the existing transaction, and replayed signed calldata reverts. Additional on-chain cases mutate recipient, amount, policy version, deadline, risk debit, session, task budget, token and signer. Exact results and default optional skips are recorded in TRANSFER_SECURITY_RESULTS.json.

The API milestone includes owner recipient policy, operator task authorization, a structured model planner, existing Shield/catalog semantics, transfer temporal accounting, isolated simulation, transfer-specific proof, transfer SDE, pre-sign and pre-submit checks, separate EIP-712 approval, exact on-chain transfer and canonical receipt/portfolio recording. Payment history is durable in the control SQLite store and is projected into subsequent payment graphs. The existing general swap history API and Dashboard have not yet been extended to present payments.

The owner must configure transfer recipients and a suitable LOCAL policy/session before using the endpoints. Existing deployed Fuji bytecode does not gain the new ABI automatically. Public transfer mode remains disabled. Transfer-capable contracts were deployed only to disposable Anvil instances by tests.

Reproduction uses the locked Python environment, installed Node dependencies and Foundry v1.7.1.

```sh
uv run --locked python tools/contracts/foundry.py forge build
uv run --locked python -m pytest backend/tests/execution/test_transfer_pipeline.py -q
uv run --locked python -m pytest -q
uv run --locked python tools/contracts/foundry.py forge test -vv
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python tools/quality/scan_secrets.py
npm run test:integration
npm run check:frontend
```

The optional test test_real_model_local_transfer uses PACEVANT_TRANSFER_LIVE=1 and the configured primary provider, zero retries and no fallback providers. It reads .env only for model configuration; all contract writes remain on disposable LOCAL Anvil.

This completed milestone leaves transfer UI, arbitrary recipient alias resolution, a 60-case payment benchmark, broad token adversarial testing, hosted recovery and independent audit for later work. Dataset selection and benchmark evaluation await the operator's revised request.

The full isolated regression after architecture/ABI corrections passed 522 Python tests, with five optional skips and no failures. The final amount-binding refinement was subsequently verified in a focused transfer run with 13 passed and one optional real-provider skip. These counts overlap. Solidity passed 60 tests. Ruff, secret scanning, EIP-712 v1/v2 vectors and frontend syntax passed. Full-case and focused-case IDs are retained in TRANSFER_SECURITY_RESULTS.json.
