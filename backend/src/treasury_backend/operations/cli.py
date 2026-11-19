"""Run from the repository root with uv; all command defaults are local-only."""

import argparse
import json
import sys
import time
from pathlib import Path

from web3 import Web3

from treasury_backend.operations import (
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


def main():
    parser = argparse.ArgumentParser(description="V2.1 modular backend operator commands")
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
            "serve-container",
            "lfj-preflight",
            "fuji-demo",
            "fuji-evidence",
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
    parser.add_argument("--adapter", choices=["mock", "lfj"], default="mock")
    parser.add_argument("--output", type=Path, help="Optional LFJ preflight report path")
    parser.add_argument("--setup", action="store_true", help="Deploy/fund the small real Fuji demo using the configured owner")
    parser.add_argument("--workflow-id", help="Workflow to verify/export with fuji-evidence")
    args = parser.parse_args()
    if args.command == "serve-container":
        from .container import main as container_main

        return container_main()
    try:
        if args.command == "lfj-preflight":
            from .env import atomic_json
            from .lfj import preflight

            result = preflight()
            if args.output:
                if args.output.exists():
                    raise OpsError("LFJ report output already exists")
                atomic_json(args.output, result)
        elif args.command == "init-env":
            result = init_env(args.env_file, generate_attestor=args.generate_attestor)
        else:
            if args.command in {"fuji-demo", "fuji-evidence"}:
                args.network = "fuji"
            p = Profile.load(ROOT, args.env_file, args.network)
            if args.command == "doctor":
                result = doctor(p, live=args.live)
            elif args.command == "deploy":
                if args.adapter == "lfj" and args.network != "fuji":
                    raise OpsError("LFJ deployment requires --network fuji")
                compile_contracts()
                result = deploy_v2(p, adapter=args.adapter)
            elif args.command == "prepare":
                result = prepare(p)
            elif args.command in {"renew-session", "renew-policy"}:
                result = renew(p, policy=args.command == "renew-policy")
            elif args.command == "demo":
                result = demo(p, args.goal)
            elif args.command == "fuji-demo":
                from .fuji_demo import bootstrap, select_goal

                if args.setup:
                    compile_contracts()
                    bootstrap(p)
                goal = select_goal(p)
                print(json.dumps({"network": "fuji", "goal": goal, "stage": "RUNNING_REAL_PIPELINE"}), flush=True)
                with services(p):
                    for attempt in range(3):
                        result = demo(p, goal)
                        if result["status"] == "CONFIRMED":
                            break
                        saved = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
                        # A new intent is safe only before a signature/submission.
                        if any(e["stage"] in {"ATTESTED", "SUBMITTING", "SUBMITTED"} for e in saved["timeline"]):
                            break
                        if not set(result["reason_codes"]) & {
                            "STALE_REQUIRES_REEVALUATION", "STALE_PRICE", "STALE_SNAPSHOT",
                            "STALE_OR_UNVERIFIED_CHAINLINK_PRICE", "FUJI_RPC_UNVERIFIED",
                        }:
                            break
                        print(json.dumps({"stage": "RETRY_WITH_FRESH_EVIDENCE", "attempt": attempt + 2}), flush=True)
                if result["status"] == "CONFIRMED":
                    from .fuji_evidence import collect
                    report, path = collect(p, result["workflow_id"])
                    result.update(evidence=str(path), all_checks_passed=report["all_checks_passed"])
            elif args.command == "fuji-evidence":
                from .fuji_evidence import collect
                if not args.workflow_id:
                    raise OpsError("Pass --workflow-id for the confirmed Fuji workflow")
                report, path = collect(p, args.workflow_id)
                if args.output:
                    from .env import atomic_json
                    atomic_json(args.output, report)
                result = {"evidence": str(args.output or path), "all_checks_passed": report["all_checks_passed"]}
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
                                    raise OpsError("Backend service exited; inspect profile logs")
                                time.sleep(1)
        print(json.dumps(result, indent=2), flush=True)
        if args.command in {"demo", "fuji-demo"} or args.once:
            return 0 if result.get("status") == "CONFIRMED" and result.get("all_checks_passed", True) else 2
        if args.command == "fuji-evidence":
            return 0 if result["all_checks_passed"] else 2
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
