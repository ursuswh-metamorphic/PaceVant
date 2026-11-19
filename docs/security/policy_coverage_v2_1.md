# V2.1 policy coverage

Scope: controlled mock USDC6/WAVAX18, one owner-selected exact-input adapter, chain 31337 locally or 43113 after explicit owner-approved configuration. This is unaudited research software.

| Rule | Before signing | Runtime | Formally proved? | Claim |
|---|---|---|---|---|
| Actor/domain/router/pair/recipient/selector/exact calldata | Existing alignment, builder, SDE, attestor and SDK | Vault canonical ABI, current attestor, chain/domain, allowlists | Deterministic | Hard runtime guard |
| USDC input/day and per-swap amount | Existing risk + chain reads | Atomic daily counter and amount cap | No SMT | Hard runtime guard |
| Reverse WAVAX amount | Explicit owner `max_wavax_per_swap`; zero disables | Separate reverse cap; no USDC daily debit for reverse | No SMT | Hard runtime guard |
| Value loss in price band | Shared exact arithmetic + SMT Check and Compile | Signed lower balance bounds for BOTH registered assets | Conditional, via monotonicity | Proof-gated within modeled prices |
| Input spending | Balance reads and exact-input evidence | Input delta equals `-amountIn` | Deterministic | Hard runtime guard |
| Residual allowances | Both registered tokens, exact adapter, before/after reads | Both allowances must equal zero; input temporary allowance cleaned | Deterministic | Hard runtime guard |
| Certified risk reservation | Independent rational upper corner, upward integer rounding, SMT risk query | Session + global UTC-day counters charged once and rolled back on revert | Bound proved; counter arithmetic deterministic | Conservative reservation, not actual PnL |
| Owner sessions | Current pinned chain state; no agent rotation | Owner-only create/revoke; immutable IDs, policy, dates; global cap spans sessions | No SMT | Hard runtime guard |
| WAVAX exposure | Existing projected portfolio calculation for both directions | **OFF**; no runtime oracle/exposure feature implemented | **Not implied by Phi** | **PRE-SIGN ONLY** |
| Oracle truth | Allowlisted controlled test source, positive bands, age and context validation | Vault trusts isolated attestor's certified debit | No oracle-honesty proof | Explicit trust assumption |
| Fees/retries | Existing execution cost gate, maximum two replans, in-flight reservation; quarantine after two consecutive protected reverts under same policy | No gas debit from treasury risk budget | No | Operational control |
| Reorg/finality | Confirmation count and canonical block checks; terminal workflow rereads receipt | Consensus | No | Pending/uncertain receipts hold signer reservation |

V2 activation is permanent on a deployment. `executeApprovedSwap` then always rejects, including after owner policy changes. Owner withdrawal is separately authorized, requires pause, invalidates policy, and emits its own event. There is no arbitrary call/delegatecall path.

No payment credit, native coin treasury movements, receipt credits, ownership checks, real DEX, rebasing/fee-on-transfer support, multisession portfolio exposure theorem, or multi-day loss budget is claimed. The fixed two-token registry makes missing tracked assets unrepresentable; arbitrary arrays/omissions are rejected by the vault. Gas paid on protected reverts remains a relayer cost.
