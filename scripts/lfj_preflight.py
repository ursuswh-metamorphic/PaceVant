"""Read LFJ and existing Chainlink adapters at the same Fuji block. Never broadcasts."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx
import rfc8785
from eth_utils import keccak

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/control-plane"))
from app.fuji_data import FujiReader  # noqa: E402
from app.fuji_oracles import CHAINLINK_FEEDS, chainlink  # noqa: E402
from app.fuji_rpc import FujiReadError, quantity  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/lfj-preflight.json")
    args = parser.parse_args()
    command = [
        "uv",
        "run",
        "--directory",
        str(ROOT / "apps/execution-plane"),
        "--locked",
        "python",
        "-m",
        "app.cli",
        "lfj-preflight",
        "--dry-run",
    ]
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
    if process.returncode:
        parser.exit(
            1, "LFJ_PREFLIGHT_UNAVAILABLE: inspect the separate LFJ preflight command locally\n"
        )
    out = json.loads(process.stdout)
    pinned = out["preflight"]
    with httpx.Client(trust_env=False, follow_redirects=False) as http:
        reader = FujiReader(http)
        if quantity(reader.rpc("eth_chainId", [])) != 43113:
            raise FujiReadError("FUJI_CHAIN_MISMATCH")
        header = reader.rpc("eth_getBlockByNumber", [hex(pinned["block_number"]), False])
        if (
            header["hash"] != pinned["block_hash"]
            or not 0 <= reader.now - quantity(header["timestamp"]) <= 120
        ):
            raise FujiReadError("FUJI_BLOCK_CHANGED_OR_STALE")
        reader.block = {
            "number": pinned["block_number"],
            "hash": pinned["block_hash"],
            "timestamp": pinned["block_timestamp"],
        }
        observations = [chainlink(reader, *feed) for feed in CHAINLINK_FEEDS]
        reader.verify_block()
    out["oracle_observations"] = observations
    out["oracle_binding"] = {
        "block_number": pinned["block_number"],
        "block_hash": pinned["block_hash"],
        "traded_token_usd_applicability": False,
        "decision_max_price_age_seconds": 60,
        "reason": "ORACLE_TOKEN_IDENTITY_MISMATCH",
        "used_for_sde_or_attestation": False,
    }
    out["observation_hash"] = "0x" + keccak(rfc8785.dumps(out)).hex()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "dex_status": pinned["status"],
                "risk_blockers": pinned["risk_blockers"],
                "broadcast": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
