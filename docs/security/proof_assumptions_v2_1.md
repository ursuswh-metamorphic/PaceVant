# Proof model and assumptions

`treasury_contracts/proof.py` is the only proof engine. `z3-solver==4.15.4.0` is pinned in the shared package and the single root uv.lock. Encoder: `pgs-treasury-2.1.0`. No upstream imports, generated SMT from users, floats in assertions, or signing keys in this library. A process lock serializes access to Z3's native default context.

For token `a`, signed integer delta is `after.balanceOf - before.balanceOf`. Normalize by `10**decimals`. Prices and monetary limits use integer USD-e8. With zero payment credit:

```
L = -sum(delta[a] * priceE8[a] / 10**decimals[a])
V =  sum(max(-delta[a], 0) * priceE8[a] / 10**decimals[a])
L <= (maxRelativeLossBps / 10000) * V + fixedLossUsdE8
```

The economic evaluator calls the same rational loss helper. No second floating risk formula exists.

For positive price and `0 <= s < 1`, each term of `L-sV` as a function of delta is `-(1-s)*delta*p` below zero and `-delta*p` above zero. Both slopes are nonpositive and the function is continuous at zero. Therefore increasing any tracked delta cannot increase the relative-policy residual. Absolute `L` is also nonincreasing. Checking the vector of signed lower bounds is sufficient for every higher accepted delta. This lemma does **not** constrain the post-trade portfolio exposure ratio.

Obligations, all with bounded solver timeout:

1. Validated price assumptions must be SAT; contradictory or unknown assumptions cannot authorize.
2. Check simulated deltas: query for a relative-policy or remaining-session-budget counterexample. Only UNSAT passes.
3. Compile negative deltas unchanged and positive inflows with integer floor tolerance, then strengthen output to at least policy minOut. Independently test the feasible bounded integer post-state region for SAT.
4. Compile query at the lower vector must be UNSAT. SAT retries once at zero tolerance. UNKNOWN never retries into an approval.
5. Maximize absolute loss at independent interval corners: high prices for negative deltas, low prices for positive deltas. Compute with `Fraction`, clamp at zero and round **up** to USD-e8. Independently ask Z3 for `L > debit`; require UNSAT. Check actual certified debit against session and global remaining headroom.

All five query contents are stored under their Keccak hash as `.smt2` files beside the control database. SMT serialization uses `sexpr()` with traversal-local symbols; Z3's `to_smt2()` includes process-global AST IDs and is deliberately avoided. Repeated proofs must produce identical query/context hashes. Query artifacts are cold files, not SQL trace blobs.

The proof artifact binds source hashes, encoder/solver versions, policy/config, exact call, registry, effect evidence, oracle, session snapshot, query hashes, Phi, debit, feasibility flags and verdicts. The sanitized counterexample is diagnostic and deliberately excluded from authorization: successful artifacts contain no witness. Source changes or any authoritative artifact mutation invalidate signer revalidation.

Effect evidence comes from the existing isolated, block-pinned guarded Anvil fork, before/after reads for both assets and both allowances; transfer logs and traces are supplemental consistency checks. An exploratory V2 execution uses a clearly labelled fork-only test attestor and zero-debit sentinel. Before live attestation, the final exact ApprovalV2/Phi/debit is replayed through the **same V2 vault entrypoint** on the isolated fork. Only attestor storage and ephemeral gas balances are overridden; source RPC receives no simulation writes. Final signed payloads are submitted without rebuilding calldata. Final Phi preflight replays the immutable build block and may use its cached artifact; fresh state checks and live estimateGas happen separately. The unified process contains both attestor and relayer keys; module separation is not process/HSM isolation.

Oracle scope is a **controlled off-chain test price file**. Its allowlisted source ID is `keccak256("TRUSTED_TEST_ORACLE")`. Oracle block/hash are the valuation snapshot context, not a claim of an on-chain feed read. Nominal prices, full configured independent bands, source, timestamp, chain and vault are encoded into the oracle ABI commitment. They can be reconstructed from the immutable stored snapshot + policy via `backend/src/treasury_backend/modules/proof/service.py`. Stale/future/zero/partial/inconsistent data fail closed. Honesty of the source and containment of actual inclusion prices in these bands are assumptions.

Trusted assumptions: supported non-rebasing mock ERC20 balances/decimals are truthful; registry is complete; owner configuration and the attestor module/runtime are uncompromised; RPC/fork returns consistent canonical state; compiled vault code enforces the signed bounds. Vault verifies a trusted attestor signature and debit, **not an SMT proof**. A compromised signer may lie about debit within owner hard limits. Arbitrary oracle compromise, token lies, gas grief, exposure drift, multisession daily resets across multiple days, and all possible MEV are outside the theorem.

`sum(certified debit) <= cap` bounds reserved worst-case loss under these assumptions. It is neither realized PnL nor a refund protocol: later profit never decreases usage. Daily global scope is `block.timestamp / 86400`; session usage persists across days and session IDs cannot be recycled.
