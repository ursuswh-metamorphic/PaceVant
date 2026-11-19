"""Evaluation-only instrumentation of the unchanged A/B security path.

No decision, proof, payload, signature or execution is altered by these wrappers.
Original-commit and current code are selected through an isolated source path.
"""

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import uvicorn

parser = argparse.ArgumentParser()
parser.add_argument("role", choices=["control", "execution"])
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--metrics", type=Path, required=True)
parser.add_argument("--port", type=int, required=True)
options = parser.parse_args()
source = options.source.resolve()
sys.path[:0] = [
    str(source / "apps" / ("control-plane" if options.role == "control" else "execution-plane")),
    str(source / "packages/contracts-api"),
]
lock = threading.Lock()


def emit(label, elapsed, **extra):
    with lock, options.metrics.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "role": options.role,
                    "stage": label,
                    "elapsed_ms": elapsed,
                    "time_ns": time.time_ns(),
                    **extra,
                }
            )
            + "\n"
        )


def timed(obj, name, label):
    original = getattr(obj, name)

    def wrapped(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            emit(label, (time.perf_counter() - start) * 1000)

    setattr(obj, name, wrapped)


if options.role == "control":
    from app import alignment, economic_risk, sde
    from app.attestor import Attestor
    from app.orchestration.service import ControlPlane

    for obj, name, label in (
        (alignment, "check", "alignment_ms"),
        (economic_risk, "evaluate", "economic_risk_ms"),
        (sde, "decide", "sde_ms"),
        (Attestor, "_sign_after_verification", "attest_ms"),
        (ControlPlane, "_verify_approval", "revalidate_ms"),
        (ControlPlane, "_reconcile", "confirm_ms"),
    ):
        timed(obj, name, label)
    if (source / "packages/contracts-api/treasury_contracts/proof.py").exists():
        from treasury_contracts.proof import PGSProofEngine

        original = PGSProofEngine.prove

        def prove(self, *args, **kwargs):
            factory = self.solver_factory
            durations = []

            class Solver:
                def __init__(self):
                    self.s = factory()

                def __getattr__(self, name):
                    return getattr(self.s, name)

                def check(self):
                    start = time.perf_counter()
                    result = self.s.check()
                    durations.append((time.perf_counter() - start) * 1000)
                    return result

            self.solver_factory = Solver
            start = time.perf_counter()
            try:
                result = original(self, *args, **kwargs)
                emit("proof_ms", (time.perf_counter() - start) * 1000, status=result.status)
                if len(durations) > 1:
                    emit("SMT_check_ms", durations[1])
                if result.status == "VERIFIED":
                    emit("SMT_compile_ms", sum(durations[2:-1]))
                    emit("riskbound_solver_ms", durations[-1])
                return result
            finally:
                self.solver_factory = factory

        PGSProofEngine.prove = prove
    from app.api import create_app
    from app.settings import Settings

    app = create_app(Settings.from_env())
else:
    from app.execution.relayer import Relayer
    from app.simulation import runner
    from app.simulation.runner import Simulator
    from app.transaction.builder import Builder

    for obj, name, label in (
        (Builder, "build", "build_ms"),
        (Simulator, "simulate", "sim_ms"),
        (runner, "token_facts", "extract_parse_ms"),
        (runner, "assess", "extract_assess_ms"),
        (Relayer, "execute", "relay_ms"),
        (Relayer, "monitor", "monitor_ms"),
    ):
        timed(obj, name, label)
    if hasattr(Simulator, "preflight_v2"):
        timed(Simulator, "preflight_v2", "final_preflight_ms")
    from app.api.main import create_app

    from app.settings import Settings

    app = create_app(Settings(_env_file=None))

uvicorn.run(app, host="127.0.0.1", port=options.port, access_log=False)
