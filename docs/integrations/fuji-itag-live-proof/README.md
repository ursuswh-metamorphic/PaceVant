# Live Fuji ITAG proof queries

These exact SMT-LIB files match query_hashes in [the DeepSeek/Fuji report](../fuji-itag-live-validation.json), in its declared order. Ethereum keccak256 hashes and solver results were independently rechecked. Expected results: SAT, UNSAT, SAT, UNSAT, UNSAT. SAT establishes feasible assumptions/compiled region; UNSAT excludes counterexamples within the bounded proof model. These queries do not establish mainnet profitability or replace an audit.
