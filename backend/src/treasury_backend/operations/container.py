"""Single-instance Fuji backend: one FastAPI process, native Anvil, durable disk.

No compilation, deployment or owner transactions occur in this entrypoint.
"""

import json
import os
import signal
import time
from pathlib import Path

from treasury_backend.operations import ROOT, OpsError, Profile, services


def container_profile(root=ROOT):
    owner_names = ("DEPLOYER_PRIVATE_KEY", "B_FUJI_OWNER_PRIVATE_KEY", "B_OWNER_PRIVATE_KEY")
    if any(os.environ.get(name) for name in owner_names):
        raise OpsError("Do not upload owner private keys to the serving container")
    # Process env supplies actual values; runtime intentionally ignores root .env.
    p = Profile.load(root, Path("/nonexistent/treasury-runtime.env"), "fuji")
    data = Path(os.environ.get("TREASURY_SERVER_DATA_DIR", "/var/data"))
    if not data.is_absolute():
        raise OpsError("TREASURY_SERVER_DATA_DIR must be an absolute persistent directory")
    p.control_data = data / "control/fuji"
    p.execution_data = data / "execution"
    try:
        p.a_port = int(os.environ.get("PORT", "10000"))
    except ValueError:
        raise OpsError("PORT must be an integer") from None
    if not 1 <= p.a_port <= 65535:
        raise OpsError("Public PORT must be valid")
    if not p.deployment.is_file():
        raise OpsError("Supply the public V2 Fuji deployment manifest before serving")
    for name in ("B_API_KEY", "PACEVANT_OPERATOR_TOKEN", "PACEVANT_INTERNAL_TOKEN"):
        if len(p.values.get(name, "")) < 24:
            raise OpsError("Missing/short service credential: " + name)
    if (
        len(
            {
                p.values[name]
                for name in ("B_API_KEY", "PACEVANT_OPERATOR_TOKEN", "PACEVANT_INTERNAL_TOKEN")
            }
        )
        != 3
    ):
        raise OpsError("Use three distinct service credentials")
    p.credentials()
    return p


def shutdown(signum, frame):
    raise KeyboardInterrupt


def main():
    signal.signal(signal.SIGTERM, shutdown)
    try:
        p = container_profile()
        with services(p, public_host="0.0.0.0") as children:
            print(
                json.dumps(
                    {
                        "status": "READY",
                        "network": "FUJI",
                        "port": p.a_port,
                        "owner_key_loaded": False,
                    }
                ),
                flush=True,
            )
            while True:
                if any(child.poll() is not None for child in children):
                    raise OpsError("Backend process exited; inspect persistent profile logs")
                time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        # RPC exceptions can contain authenticated URLs; never forward them.
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": str(exc)
                    if isinstance(exc, OpsError)
                    else "Startup failed; inspect private profile logs/configuration",
                    "error_type": type(exc).__name__,
                }
            ),
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
