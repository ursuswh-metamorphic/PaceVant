"""Compatibility launcher; use tools/evaluation/benchmark_proof.py."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1]/"tools/evaluation/benchmark_proof.py"),run_name="__main__")
