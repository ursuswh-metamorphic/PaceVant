"""Small reproducible TEST_ONLY liveness/latency sweep; no RPC or private config."""

import argparse
import itertools
import json
import math
import platform
import runpy
import statistics
import time
from pathlib import Path

from treasury_contracts.proof import PGSProofEngine

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description="Local exact-arithmetic proof liveness sweep")
parser.add_argument("--output", type=Path, default=ROOT / "docs/evaluation/v2_1_proof_sweep.json")
options = parser.parse_args()
case = runpy.run_path(str(ROOT / "backend/tests/integration/test_proof_v2.py"))["case"]
rows = []
for relative, band, tau, fixed in itertools.product(
    (0, 100, 250, 300), (0, 10, 100, 300), (0, 40, 100, 500), ("0", "100000000")
):
    args = case(relative=relative, band=band, tolerance=tau, fixed=fixed)
    start = time.perf_counter()
    p = PGSProofEngine().prove(*args)
    elapsed = (time.perf_counter() - start) * 1000
    rows.append(
        dict(
            relativeBps=relative,
            bandBps=band,
            toleranceBps=tau,
            fixedLossUsdE8=fixed,
            status=p.status,
            reason=p.reason,
            fallbackTauZero=p.fallback_tau_zero,
            riskDebitUsdE8=p.risk_debit_usd_e8,
            modeledRealizedLossUsdE8="0",
            latency_ms=elapsed,
        )
    )
lat = sorted(r["latency_ms"] for r in rows)
summary = dict(
    cases=len(rows),
    verified=sum(r["status"] == "VERIFIED" for r in rows),
    refusals=sum(r["status"] != "VERIFIED" for r in rows),
    unknown=sum(r["status"] == "INCONCLUSIVE" for r in rows),
    p50_ms=statistics.median(lat),
    p95_ms=lat[math.ceil(0.95 * len(lat)) - 1],
    p99_ms=lat[math.ceil(0.99 * len(lat)) - 1],
    worst_ms=max(lat),
)
output = options.output
output.parent.mkdir(exist_ok=True, parents=True)
output.write_text(
    json.dumps(
        dict(
            environment=dict(python=platform.python_version(), cpu=platform.processor()),
            summary=summary,
            records=rows,
        ),
        indent=2,
    )
    + "\n"
)
print(json.dumps(summary))
