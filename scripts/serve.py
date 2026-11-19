import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps" / "control-plane"), str(ROOT / "packages" / "contracts-api")]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the PaceVant control plane on loopback.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--fuji-readonly", action="store_true")
    options = parser.parse_args()
    if options.fuji_readonly:
        from app.fuji_api import create_readonly_app

        uvicorn.run(create_readonly_app(), host="127.0.0.1", port=options.port, access_log=False)
    else:
        uvicorn.run("app.main:app", host="127.0.0.1", port=options.port, access_log=False)
