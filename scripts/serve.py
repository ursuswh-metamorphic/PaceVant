import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps" / "control-plane"), str(ROOT / "packages" / "contracts-api")]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the PaceVant control plane on loopback.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    options = parser.parse_args()
    uvicorn.run("app.main:app", host=options.host, port=options.port, access_log=False)
