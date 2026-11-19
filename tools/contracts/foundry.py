"""Call pinned/native Foundry tools from Python, without Node.js."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/contracts-api"))

from treasury_contracts.toolchain import foundry_binary  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/foundry.py forge|anvil|cast [arguments]")
    try:
        binary = foundry_binary(sys.argv[1], ROOT)
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from None
    raise SystemExit(subprocess.call([binary, *sys.argv[2:]], cwd=ROOT))
