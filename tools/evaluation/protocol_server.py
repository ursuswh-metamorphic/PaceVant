"""Evaluation-only instrumentation of the unchanged A/B security path.

No decision, proof, payload, signature or execution is altered by these wrappers.
Original-commit and current code are selected through an isolated source path.
"""

import argparse
import json
import sys
import threading
import time
from importlib import import_module
from pathlib import Path

import uvicorn

parser = argparse.ArgumentParser()
parser.add_argument("role", choices=["control", "execution", "backend"])
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--metrics", type=Path, required=True)
parser.add_argument("--port", type=int, required=True)
options = parser.parse_args()
source = options.source.resolve()
legacy = not (source / "backend/src/treasury_backend").is_dir()
sys.path[:0] = [
    str(source / "apps" / ("control-plane" if options.role == "control" else "execution-plane"))
    if legacy
    else str(source / "backend/src"),
    str(source / "packages/contracts-api"),
]


def load_module(old, new):
    return import_module(old if legacy else new)


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


if options.role in {"control", "backend"}:
    alignment = load_module("app.alignment", "treasury_backend.modules.alignment")
    economic_risk = load_module("app.economic_risk", "treasury_backend.modules.risk")
    sde = load_module("app.sde", "treasury_backend.modules.decision")
    Attestor = load_module("app.attestor", "treasury_backend.modules.signing").Attestor
    ControlPlane = load_module(
        "app.orchestration.service", "treasury_backend.modules.workflows.service"
    ).ControlPlane

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
    create_app = load_module("app.api", "treasury_backend.api.control").create_app
    Settings = load_module("app.settings", "treasury_backend.config.control").Settings

    if options.role == "control":
        app = create_app(Settings.from_env())
if options.role in {"execution", "backend"}:
    Relayer = load_module(
        "app.execution.relayer", "treasury_backend.modules.execution.relaying.relayer"
    ).Relayer
    runner = load_module(
        "app.simulation.runner", "treasury_backend.modules.execution.simulation.runner"
    )
    Simulator = load_module(
        "app.simulation.runner", "treasury_backend.modules.execution.simulation.runner"
    ).Simulator
    Builder = load_module(
        "app.transaction.builder", "treasury_backend.modules.execution.transaction.builder"
    ).Builder

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
    create_app = load_module("app.api.main", "treasury_backend.api.execution").create_app

    Settings = load_module("app.settings", "treasury_backend.config.execution").Settings

    if options.role == "execution":
        app = create_app(Settings(_env_file=None))

if options.role == "backend":
    from treasury_backend.api.app import create_app

    app = create_app()

uvicorn.run(app, host="127.0.0.1", port=options.port, access_log=False)
