"""Recheck published SMT artifacts without .env, wallet keys or a network call."""

import argparse
import json
from pathlib import Path

import z3

from treasury_contracts import proof as encoder
from treasury_contracts import v2
from treasury_contracts.v2 import ProofArtifactV2, keccak

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "docs/integrations/fuji-live-validation.json")
    parser.add_argument("--queries", type=Path, default=ROOT / "docs/integrations/fuji-live-proof")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    proof = ProofArtifactV2.model_validate(report["proof"])
    expected = ["SAT", "UNSAT", "SAT", "UNSAT", "UNSAT"]
    if len(proof.query_hashes) != len(expected) or proof.fallback_tau_zero:
        raise ValueError("This reproduction command supports the published five-query proof")
    results = []
    for hash_, status in zip(proof.query_hashes, expected, strict=True):
        raw = (args.queries / (hash_[2:] + ".smt2")).read_bytes()
        if len(raw) > 1024 * 1024 or keccak(raw) != hash_:
            raise ValueError("SMT artifact hash/size mismatch")
        solver = z3.Solver()
        solver.set(timeout=3000)
        solver.from_string(raw.decode("utf-8"))
        actual = str(solver.check()).upper()
        results.append({"hash": hash_, "expected": status, "actual": actual, "passed": actual == status})
    source_hash = keccak(Path(encoder.__file__).read_bytes() + Path(v2.__file__).read_bytes())
    result = {
        "status": "PASS" if all(r["passed"] for r in results) else "FAIL",
        "query_results": results, "proof_context_hash": proof.context_hash,
        "encoder_hash_matches_current_sources": source_hash == proof.source_hash,
        "network_calls": False, "env_or_wallet_keys_loaded": False,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
