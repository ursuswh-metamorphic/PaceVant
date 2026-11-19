"""Run one Uvicorn process for all backend modules."""

import argparse

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the modular treasury backend.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    args = parser.parse_args()
    uvicorn.run(
        "treasury_backend.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        access_log=False,
    )
