import argparse

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the PaceVant control plane on loopback.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    options = parser.parse_args()
    uvicorn.run(
        "treasury_backend.api.control:create_app",
        host=options.host,
        port=options.port,
        access_log=False,
        factory=True,
    )
