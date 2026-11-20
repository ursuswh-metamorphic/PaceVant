# Fuji live proof queries

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](../../AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](../../README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

These five SMT-LIB artifacts belong to the query hashes in [the public Fuji report](../fuji-live-validation.json), in that report's exact order. They contain no credentials.

Expected solver outcomes: `SAT`, `UNSAT`, `SAT`, `UNSAT`, `UNSAT`. The SAT checks establish nonempty price assumptions and a feasible compiled region; the three UNSAT checks exclude a counterexample for Check, Compile and RiskBound within the encoded model. Hash each exact file with Ethereum keccak256 and compare it to the report before solving. A SAT/UNSAT result alone does not validate the model's oracle/trust assumptions or prove all smart-contract behavior.

Run with the repository's pinned Z3 using the reproduction tool described in the [live runbook](../../demo/FUJI_LIVE_END_TO_END.md). The signed proof context is immutable historical evidence; later source/config changes require new proofs for new trades.
