"""Compatibility launcher; use tools/evaluation/protocol_server.py."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1]/"tools/evaluation/protocol_server.py"),run_name="__main__")
