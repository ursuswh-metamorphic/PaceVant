"""Run one Uvicorn process for all backend modules."""

import argparse
import os

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the modular treasury backend.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    args = parser.parse_args()
    if "PACEVANT_MODE" not in os.environ:
        from treasury_backend.operations import ROOT, Profile, services

        profile = Profile.load(ROOT, ROOT / ".env", "fuji")
        profile.a_port = args.port
        # Canonical launcher sets PACEVANT_MODE for its child, avoiding recursion.
        with services(profile, public_host=args.host) as children:
            import time

            while all(child.poll() is None for child in children):
                time.sleep(1)
        raise SystemExit("Backend stopped; inspect the profile log")
    uvicorn.run(
        "treasury_backend.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        access_log=False,
    )
