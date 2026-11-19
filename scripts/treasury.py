"""Run from the repository root with uv; all command defaults are local-only."""

import argparse
import json
import sys
import time
from pathlib import Path

from treasury_ops import (
    ROOT,
    OpsError,
    Profile,
    compile_contracts,
    demo,
    deploy_v2,
    doctor,
    init_env,
    local_chain,
    prepare,
    renew,
    services,
)
from web3 import Web3


def main():
    parser = argparse.ArgumentParser(description="V2.1 A/B demo operator commands")
    parser.add_argument(
        "command",
        choices=[
            "init-env",
            "doctor",
            "deploy",
            "prepare",
            "serve",
            "demo",
            "local",
            "renew-session",
            "renew-policy",
        ],
    )
    parser.add_argument("--network", choices=["local", "fuji"], default="local")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--live", action="store_true", help="Read-only RPC/funding checks")
    parser.add_argument(
        "--generate-attestor",
        action="store_true",
        help="Create a dedicated test signer only if blank; private key written locally, never printed",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one complete workflow and stop the owned local services",
    )
    parser.add_argument("--goal", default="Buy WAVAX with 200 USDC")
    args = parser.parse_args()
    try:
        if args.command == "init-env":
            result = init_env(args.env_file, generate_attestor=args.generate_attestor)
        else:
            p = Profile.load(ROOT, args.env_file, args.network)
            if args.command == "doctor":
                result = doctor(p, live=args.live)
            elif args.command == "deploy":
                compile_contracts()
                result = deploy_v2(p)
            elif args.command == "prepare":
                result = prepare(p)
            elif args.command in {"renew-session", "renew-policy"}:
                result = renew(p, policy=args.command == "renew-policy")
            elif args.command == "demo":
                result = demo(p, args.goal)
            elif args.command in {"local", "serve"}:
                if args.command == "local" and args.network != "local":
                    raise OpsError(
                        "local command never deploys to Fuji; use explicit deploy --network fuji"
                    )
                with local_chain(p):
                    if args.command == "local":
                        compile_contracts()
                        if not p.deployment.exists() or not p.web3().eth.get_code(
                            Web3.to_checksum_address(
                                json.loads(p.deployment.read_text())["vault_address"]
                            )
                        ):
                            deploy_v2(p)
                    with services(p) as children:
                        print(
                            json.dumps(
                                {
                                    "status": "READY",
                                    "network": p.network,
                                    "dashboard": f"http://127.0.0.1:{p.a_port}",
                                    "credential_variable": "PACEVANT_OPERATOR_TOKEN",
                                    "logs": str(p.control_data),
                                },
                                indent=2,
                            ),
                            flush=True,
                        )
                        if args.once:
                            result = demo(p, args.goal)
                        else:
                            while True:
                                if any(c.poll() is not None for c in children):
                                    raise OpsError("A/B service exited; inspect profile logs")
                                time.sleep(1)
        print(json.dumps(result, indent=2), flush=True)
        if args.command == "demo" or args.once:
            return 0 if result.get("status") == "CONFIRMED" else 2
        return 0 if not (args.command == "doctor" and not result["configuration_ready"]) else 2
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": str(exc)
                    if isinstance(exc, OpsError)
                    else "Configuration, RPC or dependency error; run doctor and inspect private profile logs",
                    "error_type": type(exc).__name__,
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
