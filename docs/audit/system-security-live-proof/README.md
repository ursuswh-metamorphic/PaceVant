# Fuji audit proof evidence

Workflow `workflow_b813ce97ad0542e9b1b667e4e5e07788`, linked to [public validation](../system-security-live-validation.json). These five exact SMT-LIB files were exported from the private proof-query store, independently rehashed (Keccak-256) against the approved proof and re-solved with Z3. Results in order: SAT, UNSAT, SAT, UNSAT, UNSAT. [Verification metadata](verification.json) also records a read-only temporal-verifier check against the actual reconciled intent history: reusing the completed step is rejected. No second transaction was broadcast.

This is an off-chain bounded-model proof. The vault enforces signatures, bindings, Phi and caps; it does not execute this solver or verify a ZK proof. Fork stress remains hypothetical EVM execution, and testnet USD is a policy reference valuation.
