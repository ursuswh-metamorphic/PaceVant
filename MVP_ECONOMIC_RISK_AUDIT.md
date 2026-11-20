# PACE / PGS economic risk audit

21 November 2026. Sources reviewed: [PACE paper](docs/paper/PACE_Policy_Attested_Contract_Execution.md), the read-only [PGS paper source](Proof-Gated-Signing/paper/main.tex), existing shared [V2 proof engine](packages/contracts-api/treasury_contracts/proof.py), [fixed-operation extension](packages/contracts-api/treasury_contracts/proof_v3.py), risk/decision/signing code and Solidity. The reference repository is ignored and unchanged.

## Value policy and payment credit

For token balance deltas in whole-token units, positive price vector `p`, and authorized measured payment credit `π`:

`L(Δ,p) = -Σ Δ[a] p[a] - Σ π[a] p[a]`

`V(Δ,p) = Σ max(-Δ[a],0) p[a] - Σ π[a] p[a]`

The solver rejects a counterexample to `L <= s*V + fixed_floor` or remaining cumulative risk. Certified risk debit is the upward-rounded nonnegative worst-case loss. The existing value-loss threshold is preserved; budgets never receive a refund from favorable price movement.

For swaps, payment credit is zero. Exact input, DEX output, slippage, independent Chainlink bands, impact, exposure and both spending/risk budgets apply. The official quoter must select the approved V1 pair/version, and its quote must agree with independently computed V1 reserve arithmetic and adapter output at the pinned block.

For an authorized 1 USDC payment with exact treasury debit and actual 1 USDC receipt, payment credit is 1 USDC, `L=0`, and payment spending still increases by 1 USDC. It is not a 100% trading loss. Credit is bounded by intended amount and measured receipt. The MVP is deliberately stricter than a fee-tolerant payment system: the compiled receipt and on-chain receiver delta must equal at least the full authorized amount. Any transfer fee or redirection shortfall reverts. Fee-on-transfer behavior is tested only with controlled local fixtures.

Payment principal does not consume swap notional. Economic loss does not include the separate Relayer AVAX expense. A payment-only session with zero swap budget is tested explicitly.

## Proof obligations and soundness boundary

| Obligation | Implementation |
|---|---|
| Non-vacuity | Price assumptions must be SAT; lower bounds must admit nonnegative balances and the measured result must fit the compiled constraints |
| CheckMode | Search actual measured effects for a violating price in the validated band; only UNSAT passes |
| CompileMode | Search the conservative lower corner for a value-policy violation; only UNSAT passes |
| Risk bound | Search for loss above certified debit; only UNSAT passes |
| Solver failures | SAT, UNKNOWN, timeout and exceptions never produce VERIFIED or a signature |
| Failed evidence | Real failed queries and SAT price witnesses are retained as `NOT_PROVEN` evidence |
| Units / rounding | USDC 6, WAVAX 18; exact rational arithmetic, outward oracle bands, downward output rounding and upward loss/notional rounding |
| Final binding | Attestor re-solves the proof, verifies decision bindings, revalidates economic/Shield/chain state, then signs once |

For positive prices and `0 <= s < 1`, `L-sV` is nonincreasing in each balance delta. Thus proving the lower corner covers the signed region `Δ >= c`. Solidity enforces that region atomically, exact input debit, measured payee receipt, zero residual allowances, the signed WAVAX balance cap and an exact pre-balance binding. State changes to a pool may improve execution or stay inside Phi; effects outside Phi revert and roll back spending, risk and nonce counters. Pre-sign simulation is not presented as a guarantee of unchanged future pool state.

The mathematical certificate is bounded off-chain SMT with explicit assumptions, not a ZK proof or a full formal verification of Solidity, LFJ, RPC infrastructure or oracle economics.

## PACE and structural checks

| Requirement | Result and limit |
|---|---|
| Typed intent / trusted provenance | Operator terms plus owner-signed registry and on-chain authority; model/tool content never changes those terms |
| Exact call and evidence | Deterministic selectors/targets, canonical ABI call hash, EIP-712 operation/evidence/proof/Phi commitments |
| Policy, chain, session, nonce, expiry | Enforced in contract; incompatible old entry points permanently revert on MVP |
| S1: approved EOA payments/caps | Exact USDC identity and recipient; per-payment, recipient/session/day and aggregate payment counters |
| S2: allowance structure | Fixed exact-input approvals only; cleanup and zero allowance checks for managed adapter edges |
| S3: ownership | No agent ownership selector or delegatecall; ownership/admin paths remain Owner-only |
| S4: priced/complete effects | Fixed approved USDC/WAVAX call surface, native no-outflow bound, measured tracked effects; unsupported financial primitives rejected |

S4 is not a claim that an ERC-20 vault can prevent unsolicited transfers of every unknown token. Security assumes trusted balance semantics for the fixed tokens and validated adapter code. Circle proxy implementation/governance remains a trust assumption beyond a proxy runtime hash. Attestor compromise, Owner compromise, arbitrary dishonest RPC consensus, token contracts lying about balances, and prices outside the assumed band are not covered by the SMT guarantee.

## Findings and fixes

* Payment credit is independently receipt-backed; no blind reuse of a swap-only loss model.
* Payment credit is subtracted from both unexplained loss and outgoing value, matching the PGS value definition.
* Independent USDC/share valuation issues found during V3 research are outside MVP scope. The reserved ABI slot is identically zero, not an investment asset.
* Stable query-local SMT serialization supports byte-for-byte proof revalidation. A shared solver lock protects the native Z3 context.
* System expense bounds and physical gas funding now apply to operator-funded execution, rather than depending on retired sponsor credits.
* Reorg/unknown/replaced executions retain reservations and never become fabricated success. Replacement ambiguity requires explicit operator review; no automatic gas-bumping or new signing is performed.
* Exact pre-balance binding is conservative and can cause denial of service after unsolicited balance changes; it never grants extra authority.

## Actual Fuji blockers

At [public snapshot block 61386636](docs/audit/mvp-public-state.json), the V1 pool held about **0.279989 USDC** and **3.725677 WAVAX**. Selling `10^15` WAVAX base units quoted **74 USDC base units**, versus a Chainlink fair-output floor of **6510**. Reference loss was **9886 bps**, above the unchanged **300 bps** limit.

The [fork evidence](docs/audit/mvp-fork-route-results.json) also records official-quoter selection per direction. A reverse best quote outside the allowed V1 route is rejected by `LFJ_UNSUPPORTED_ROUTE`; local route-compatibility experiments do not override that live authorization gate.

The deployed old proof policy additionally has `maxWavaxPerSwap = 0`. The unsigned migration explicitly proposes a reviewed nonzero reverse cap, without changing relative loss, fixed floor, oracle band, tolerance, or risk limits. None of these findings authorize increasing a loss threshold or adding a bin route to force a success.
