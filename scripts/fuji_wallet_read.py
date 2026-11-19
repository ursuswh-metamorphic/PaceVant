"""Read public Fuji balances, oracle observations and optional Vault/receipt evidence."""

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/control-plane"))

from app.fuji_data import FujiReader  # noqa: E402
from app.fuji_rpc import FujiReadError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", help="Public EVM address on Fuji")
    parser.add_argument("--vault", help="Public PolicyVault address on Fuji")
    parser.add_argument("--tx-hash", help="Fuji execution transaction hash")
    parser.add_argument("--output", type=Path, help="Save the observation JSON")
    args = parser.parse_args()
    try:
        with httpx.Client(trust_env=False, follow_redirects=False) as http:
            result = FujiReader(http).snapshot(
                args.address,
                vault_address=args.vault,
                tx_hash=args.tx_hash,
            )
        encoded = json.dumps(result, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
    except FujiReadError as error:
        parser.exit(1, f"Fuji read failed: {error.code}\n")


if __name__ == "__main__":
    main()
