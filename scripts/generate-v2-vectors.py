"""Compatibility launcher; use tools/contracts/generate_v2_vectors.py."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1]/"tools/contracts/generate_v2_vectors.py"),run_name="__main__")
