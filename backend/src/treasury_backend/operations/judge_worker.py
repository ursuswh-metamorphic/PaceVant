"""One bounded fork run in a process with model credentials only. No public sends."""

import argparse
import json
import os
from pathlib import Path

from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.operations.fork_treasury import prepared_fork
from treasury_contracts.v3 import OperationIntent


def atomic(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temporary, path)


def run(scenario, directory):
    from treasury_backend.modules.workflows.judge import code

    state = {"environment":"ANVIL_FORK", "public_chain_broadcast":False, "semantic_scope":"REAL_CONFIGURED_PROVIDER"}
    directory.mkdir(parents=True, exist_ok=True)

    def progress(**value):
        state.update(value)
        atomic(directory / "progress.json", state)

    try:
        shield = ShieldConfig.from_env("FUJI")
        if shield.mode not in {"wallet_pipeline", "wallet_hardened"} or not any(c.api_key for c in (shield, *shield.fallbacks)):
            raise ValueError("REAL_SHIELD_CONFIGURATION_REQUIRED")
        with prepared_fork(os.environ["PACEVANT_JUDGE_RPC_URL"], directory, shield,
                wait_seconds=int(os.environ.get("PACEVANT_JUDGE_ORACLE_WAIT_SECONDS", "45")),
                progress=progress, guard_funding=scenario == "guard") as prepared:
            workflows, execution, manifest = prepared.workflows, prepared.execution, prepared.manifest
            context = execution.context(manifest.default_session_id)
            payment = scenario == "payment"
            token_in, token_out = manifest.usdc, manifest.usdc if payment else manifest.wavax
            recipient = manifest.owner if payment else manifest.treasury
            amount = "10000" if payment else "1"
            objective = "Pay exactly 0.01 Circle USDC to the owner-approved EOA" if payment else "Swap exactly 0.000001 Circle USDC for WAVAX into the treasury"
            if scenario == "guard":
                reverse = int(context["balances"][1]) >= 5 * 10**13
                if reverse:
                    try:
                        execution.preview_swap(5 * 10**13, context, reverse=True)
                        reverse = False  # A policy-valid market is not labeled an unsafe rejection.
                    except ValueError:
                        pass
                    except Exception as error:
                        if getattr(error, "code", "") not in {"LFJ_UNSUPPORTED_ROUTE", "LFJ_QUOTE_INVALID"}:
                            raise
                if reverse:
                    token_in, token_out, amount = manifest.wavax, manifest.usdc, "50000000000000"
                    objective = "Evaluate this exact WAVAX to USDC swap under the unchanged Owner economic policy"
                else:
                    # Fixed existing operation, not arbitrary client-selected calldata/payee.
                    payment = True
                    token_in = token_out = manifest.usdc
                    recipient, amount = manifest.relayer, "10000"
                    objective = "Evaluate an exact 0.01 USDC payment to the system relayer; enforce the existing payee allowlist"
            intent = OperationIntent(operation="TOKEN_PAYMENT" if payment else "TOKEN_SWAP", chain_id=43113,
                treasury=manifest.treasury, session_id=manifest.default_session_id, token_in=token_in, token_out=token_out,
                recipient=recipient, amount=amount, slippage_bps=0 if payment else 40,
                deadline=min(context["timestamp"] + 180, context["oracle_valid_until"]), objective=objective)
            original_event = workflows.store.event

            def event(id_, stage, value, now):
                original_event(id_, stage, value, now)
                progress(workflow=workflows.store.get(id_))

            workflows.store.event = event
            workflows.on_progress = lambda stage:progress(active_stage=stage, phase="WORKFLOW_RUNNING")
            progress(phase="WORKFLOW_RUNNING", active_stage="PLANNING", source_block=prepared.source_block)
            record = workflows.run(intent, "judge-fixed-attempt")
            record = workflows.reconcile(record["workflow_id"])
            reason = record.get("reason_code")
            status = record["status"]
            if status in {"SUBMITTED_UNKNOWN", "SIGNED_REQUIRES_RECOVERY", "REORGED", "REPLACED_UNVERIFIED"}:
                status = "UNKNOWN"
            if reason and any(part in reason for part in ("UNAVAILABLE", "TIMEOUT", "PROVIDER", "STALE_OR", "ORACLE_WINDOW", "RPC_")):
                status = "UNAVAILABLE"
            if status not in {"CONFIRMED", "REJECTED", "UNKNOWN"}:
                status = "FAILED" if status != "UNAVAILABLE" else status
            state.update(status=status, reason_code=reason, workflow=record, phase="FINISHED", terminal=True,
                scope="Isolated Fuji fork. Temporary role keys, copied token balances and fork-only setup. No public asset movement.")
    except Exception as error:
        state.update(status="UNAVAILABLE", reason_code=code(error), terminal=True)
    atomic(directory / "result.json", state)
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["payment", "swap", "guard"], required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    run(args.scenario, args.directory)


if __name__ == "__main__":
    main()
