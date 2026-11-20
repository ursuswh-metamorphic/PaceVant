"""Native judge-only serving entrypoint. No .env load, public signer, or Node runtime."""

import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    for name in ("B_FUJI_OWNER_PRIVATE_KEY", "DEPLOYER_PRIVATE_KEY", "PACEVANT_ATTESTOR_KEY", "B_FUJI_RELAYER_PRIVATE_KEY", "B_RELAYER_PRIVATE_KEY"):
        if os.environ.get(name):
            raise SystemExit("Judge-only service must not receive public wallet signing keys")
    uvicorn.run("treasury_backend.api.judge:create_app", factory=True, host="127.0.0.1", port=args.port,
                workers=1, access_log=False, proxy_headers=True, forwarded_allow_ips="127.0.0.1", timeout_graceful_shutdown=20)


if __name__ == "__main__":
    main()
