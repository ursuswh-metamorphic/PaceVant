"""Compatibility launcher; use tools/quality/scan_secrets.py."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1]/"tools/quality/scan_secrets.py"),run_name="__main__")
