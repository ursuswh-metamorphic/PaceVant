"""Safe standalone Fuji wallet observation CLI (no keys, no transactions).

uv run --locked python scripts/fuji_wallet_read.py 0xYOUR_PUBLIC_ADDRESS
"""
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/control-plane"))

from app.fuji_data import FujiReadError, FujiReader  # noqa: E402


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: uv run --locked python scripts/fuji_wallet_read.py <PUBLIC_0x_ADDRESS>")
    try:
        with httpx.Client(timeout=httpx.Timeout(12, connect=3), trust_env=False) as http:
            result = FujiReader(http).snapshot(sys.argv[1])
        print(json.dumps(result, indent=2))
    except FujiReadError as error:
        raise SystemExit("Fuji read failed: " + error.code) from None


if __name__ == "__main__":
    main()
