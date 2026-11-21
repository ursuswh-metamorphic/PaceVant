"""One bounded fork run in a process with model credentials only. No public sends."""

import argparse
import json
import os
import time
from pathlib import Path
from time import monotonic

from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.operations.fork_treasury import prepared_fork
from treasury_backend.operations.judge_metrics import InferenceMeter
from treasury_contracts.v3 import OperationIntent


def atomic(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    # Windows readers can briefly hold a handle without delete sharing. Retry
    # the same bytes rather than turning a transient UI read into a gate error.
    for attempt in range(30):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt==29:
                raise
            time.sleep(.01)


def job_event_writer(store,request_key,publish,method="event"):
    original_event=getattr(store,method)

    def event(id_,stage,value,now):
        original_event(id_,stage,value,now)
        current=store.by_key(request_key)
        if current is not None and current['workflow_id']==id_:
            publish(workflow=store.get(id_))
    return event


def run(scenario, directory, recipient_index=None):
    from treasury_backend.modules.workflows.judge import code

    public=os.environ.get('PACEVANT_JUDGE_EXECUTION_MODE')=='REAL_FUJI_EXECUTION'
    state = {"environment":"REAL_FUJI_EXECUTION" if public else "ANVIL_FORK", "public_chain_broadcast":False, "semantic_scope":"REAL_CONFIGURED_PROVIDER"}
    directory.mkdir(parents=True, exist_ok=True)
    started, meter, setup = monotonic(), None, []

    def progress(**value):
        now = time.time()
        phase = value.get("phase")
        if phase and phase != "WORKFLOW_RUNNING":
            preparation = state.setdefault("preparation", [])
            if not preparation or preparation[-1]["phase"] != phase:
                if preparation:
                    preparation[-1]["duration_ms"] = round((now - preparation[-1]["started_at"]) * 1000, 3)
                if phase != "FINISHED":
                    preparation.append({"phase": phase, "started_at": now})
            if preparation and phase != "FINISHED":
                preparation[-1].update(updated_at=now, **{k:v for k,v in value.items() if k != "phase"})
        elif phase == "WORKFLOW_RUNNING" and state.get("preparation"):
            preparation = state["preparation"]
            preparation[-1].setdefault("duration_ms", round((now - preparation[-1]["started_at"]) * 1000, 3))
        state.update(value)
        atomic(directory / "progress.json", state)

    try:
        shield = ShieldConfig.from_env("FUJI")
        if shield.mode not in {"wallet_pipeline", "wallet_hardened"} or not any(c.api_key for c in (shield, *shield.fallbacks)):
            raise ValueError("REAL_SHIELD_CONFIGURATION_REQUIRED")
        from treasury_backend.operations.public_treasury import prepared_public
        preparation=prepared_public(directory,shield,progress) if public else prepared_fork(os.environ["PACEVANT_JUDGE_RPC_URL"], directory, shield,
                wait_seconds=int(os.environ.get("PACEVANT_JUDGE_ORACLE_WAIT_SECONDS", "45")),
                progress=progress, guard_funding=scenario == "guard")
        with preparation as prepared:
            workflows, execution, manifest = prepared.workflows, prepared.execution, prepared.manifest
            setup = prepared.setup
            meter = InferenceMeter(workflows.control.shield.provider, lambda:state.get("active_stage", "PREPARATION"))
            workflows.control.shield.provider = meter
            context = prepared.intent_context if public and scenario!='guard' else execution.context(manifest.default_session_id)
            payment = scenario == "payment"
            token_in, token_out = manifest.usdc, manifest.usdc if payment else manifest.wavax
            # Fixed three-role cycle is owner-approved in the signed manifest.
            payee=manifest.payee_candidates[(recipient_index if recipient_index is not None else int(directory.name.removeprefix('judge_')[:8],16))%len(manifest.payee_candidates)] if public else manifest.owner
            recipient = payee if payment else manifest.treasury
            amount = "10000" if payment else "1"
            objective = f"Pay exactly 0.01 Circle USDC to the owner-approved EOA {recipient}" if payment else "Swap exactly 0.000001 Circle USDC for WAVAX into the treasury"
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
                    recipient, amount = (manifest.treasury if public else manifest.relayer), "10000"
                    objective = f"Evaluate an exact 0.01 USDC payment to {recipient}; enforce the existing payee allowlist"
            intent = OperationIntent(operation="TOKEN_PAYMENT" if payment else "TOKEN_SWAP", chain_id=43113,
                treasury=manifest.treasury, session_id=manifest.default_session_id, token_in=token_in, token_out=token_out,
                recipient=recipient, amount=amount, slippage_bps=0 if payment else 40,
                deadline=min(context["timestamp"] + 180, context["oracle_valid_until"]), objective=objective)
            request_key='judge-fixed-'+directory.name
            # Shared state reconciles old transactions; publish only this job.
            workflows.store.event=job_event_writer(workflows.store,request_key,progress)
            workflows.store.activity=job_event_writer(workflows.store,request_key,progress,"activity")
            workflows.on_progress = lambda stage:progress(active_stage=stage, phase="WORKFLOW_RUNNING")
            progress(phase="WORKFLOW_RUNNING", active_stage="PLANNING", source_block=prepared.source_block)
            record = workflows.run(intent, request_key)
            record = workflows.reconcile(record["workflow_id"])
            if public:
                until=time.monotonic()+20
                while record['status'] in {'PENDING_CONFIRMATIONS','SUBMITTED_UNKNOWN'} and time.monotonic()<until:
                    time.sleep(1)
                    record=workflows.reconcile(record['workflow_id'])
            reason = record.get("reason_code")
            status = record["status"]
            if status in {"SUBMITTED_UNKNOWN", "SIGNED_REQUIRES_RECOVERY", "REORGED", "REPLACED_UNVERIFIED", "PENDING_CONFIRMATIONS"}:
                status = "UNKNOWN"
            if reason and any(part in reason for part in ("UNAVAILABLE", "TIMEOUT", "PROVIDER", "STALE_OR", "ORACLE_WINDOW", "RPC_")):
                status = "UNAVAILABLE"
            if status not in {"CONFIRMED", "REJECTED", "UNKNOWN"}:
                status = "FAILED" if status != "UNAVAILABLE" else status
            state.update(status=status, reason_code=reason, workflow=record, phase="FINISHED", terminal=True,
                public_chain_broadcast=public and bool((record.get('outcome') or {}).get('tx_hash')),
                scope="Public Avalanche Fuji execution using owner-approved test assets and real relayer gas." if public else "Isolated Fuji fork. Temporary role keys, copied token balances and fork-only setup. No public asset movement.")
    except Exception as error:
        state.update(status="UNAVAILABLE", reason_code=code(error), terminal=True)
    if state.get("preparation"):
        last = state["preparation"][-1]
        last.setdefault("duration_ms", round((time.time() - last["started_at"]) * 1000, 3))
    state["runtime_metrics"] = {
        "worker_wall_seconds": round(monotonic() - started, 6),
        "inference": meter.summary() if meter is not None else {"calls":[],"call_count":0,"reported_token_usage":{},"billing_usd":None},
        "fork_setup": {"transaction_count":len(setup),
            "gas_used":str(sum(int(tx["gas_used"]) for tx in setup)),
            "actual_fee_wei":str(sum(int(tx["actual_fee_wei"]) for tx in setup)),
            "scope":"Tracked deployment/configuration only; funding and nested simulations excluded"},
        "gas_scope": "Public Fuji execution fee; simulations remain isolated and model invoice is separate" if public else "Isolated fork only; not a public-chain fee or model invoice",
    }
    atomic(directory / "result.json", state)
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["payment", "swap", "guard"], required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument('--recipient-index',type=int,choices=range(3))
    args = parser.parse_args()
    run(args.scenario, args.directory, args.recipient_index)


if __name__ == "__main__":
    main()
