# Live Fuji ITAG proof queries

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](../../AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](../../README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

These exact SMT-LIB files match query_hashes in [the DeepSeek/Fuji report](../fuji-itag-live-validation.json), in its declared order. Ethereum keccak256 hashes and solver results were independently rechecked. Expected results: SAT, UNSAT, SAT, UNSAT, UNSAT. SAT establishes feasible assumptions/compiled region; UNSAT excludes counterexamples within the bounded proof model. These queries do not establish mainnet profitability or replace an audit.
