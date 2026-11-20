"""Single-tenant MVP routes. Public reads, two operator intents, owner-wallet administration."""

import secrets
import time
from threading import Lock
from typing import Literal

from fastapi import Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from filelock import Timeout

from treasury_backend.core.errors import ControlError
from treasury_backend.paths import ROOT
from treasury_contracts.mvp import MvpIntent
from treasury_contracts.v3 import Hash, RebalanceRequest, Wire


def install_mvp_routes(app, settings):
    readiness_lock = Lock()
    readiness_cache = {}

    def readiness(request):
        from treasury_backend.modules.workflows.readiness import inspect, reason

        if not readiness_lock.acquire(blocking=False):
            return {"ready": False, "checks": [{"code":"READINESS_REFRESHING", "ready":False,
                    "action":"Readiness refresh in progress; retry shortly"}], "operations":[], "recheck_seconds":5}
        try:
            if time.monotonic() < readiness_cache.get("until", 0):
                cached = readiness_cache["value"]
                if not cached["ready"] or cached.get("valid_until", 0) >= int(time.time()) + 90:
                    return cached
            active = getattr(request.app.state, "treasury_mvp", None)
            try:
                value = inspect(active) if active else {"ready": False, "checks": [{
                    "code": "MVP_OWNER_MIGRATION_REQUIRED", "ready": False,
                    "action": "Owner must deploy, fund and activate the signed MVP manifest"}], "operations": []}
            except Exception as error:
                value = {"ready": False, "checks": [{"code": reason(error), "ready": False,
                         "action": "Check chain/RPC identity and connectivity; no transaction was authorized"}], "operations": []}
            readiness_cache.update(value=value, until=time.monotonic() + 20)
            return value
        finally:
            readiness_lock.release()
    def operator(request: Request):
        token = settings.operator_token
        if not token or not secrets.compare_digest(
            request.headers.get("Authorization", "").encode(), ("Bearer " + token).encode()
        ):
            raise ControlError("AUTH_REQUIRED", 401)

    def service(request: Request):
        result = getattr(request.app.state, "treasury_mvp", None)
        if result is None:
            raise ControlError("MVP_OWNER_MIGRATION_REQUIRED", 503)
        return result

    protected = [Depends(operator)]

    @app.get("/mvp/readiness")
    def get_readiness(request: Request):
        return JSONResponse(readiness(request), headers={"Cache-Control": "no-store"})

    @app.get("/readyz", include_in_schema=False)
    def readyz(request: Request):
        value = readiness(request)
        return JSONResponse(value, status_code=200 if value["ready"] else 503,
                            headers={"Cache-Control": "no-store"})

    @app.get("/mvp/capabilities")
    def capabilities(request: Request):
        active = getattr(request.app.state, "treasury_mvp", None)
        return {
            "single_tenant": True,
            "financial_operations": ["SWAP_EXACT_IN", "USDC_PAYMENT"],
            "enabled": active is not None,
            "environment": active.execution.manifest.environment if active else None,
            "default_session_id": active.execution.manifest.default_session_id if active else None,
            "demo_user_enabled": False,
            "semantic_evaluation_scope": active.control.shield.provider.evaluation_scope
            if active
            else None,
            "public_execution": False,
            "disabled_operations": [
                "VAULT_DEPOSIT",
                "VAULT_WITHDRAW",
                "NATIVE_PAYMENT",
                "ARBITRARY_TOKEN_PAYMENT",
                "LENDING",
                "STAKING",
                "LP",
                "BRIDGE",
                "ARBITRARY_CALL",
            ],
            "reason": None
            if active
            else "Owner migration required for reverse swaps and receipt-checked payments. Existing Fuji deployment is preserved.",
        }

    @app.get("/mvp/status")
    def public_status(request: Request):
        active = getattr(request.app.state, "treasury_mvp", None)
        try:
            if active:
                c = active.execution.display_context(active.execution.manifest.default_session_id)
                return {
                    "source": c["environment"],
                    "chain_id": c["chain_id"],
                    "treasury": c["treasury"],
                    "balances": c["balances"][:2],
                    "relayer_avax_wei": c["relayer_avax_wei"],
                    "paused": c["paused"],
                    "session_active": c["session_active"],
                    "session_expires_at": c["session_expires_at"],
                    "spend_remaining": c["spend_remaining"],
                    "risk_remaining": c["risk_remaining"],
                    "history": [
                        {
                            "operation": r["intent"]["operation"],
                            "status": r["status"],
                            "outcome": r.get("outcome"),
                        }
                        for r in active.store.history()
                    ],
                }
            runtime = getattr(request.app.state, "execution", None)
            if runtime:
                c = runtime.chain.context()
                snap = runtime.chain.snapshot(c)
                return {
                    "source": "PUBLIC_FUJI_READ_ONLY" if c["chain_id"] == 43113 else "LOCAL_TEST",
                    "chain_id": c["chain_id"],
                    "treasury": c["vault_address"],
                    "balances": [snap["usdc_base_units"], snap["wavax_base_units"]],
                    "relayer_avax_wei": str(
                        runtime.chain.w3.eth.get_balance(runtime.chain.deployment["relayer"])
                    ),
                    "paused": c["paused"],
                    "migration_required": True,
                    "broadcast": False,
                }
        except Exception as exc:
            return {
                "source": "UNVERIFIED",
                "reason": getattr(exc, "code", "RPC_OR_POLICY_UNAVAILABLE"),
                "broadcast": False,
            }
        return {"source": "UNVERIFIED", "reason": "NO_CHAIN_RUNTIME", "broadcast": False}

    @app.get("/mvp/treasury/{session_id}", dependencies=protected)
    def treasury(session_id: str, request: Request):
        active = service(request)
        try:
            from pydantic import TypeAdapter

            TypeAdapter(Hash).validate_python(session_id)
            c = active.execution.display_context(session_id)
        except ValueError as exc:
            raise ControlError(str(exc) if str(exc).isupper() else "INVALID_SESSION", 409) from None
        from treasury_backend.modules.gas_credit.system import SystemGasLedger

        return {
            "context": c,
            "targets": active.execution.manifest.rebalance_policy.model_dump(mode="json"),
            "history": active.store.history(),
            "autonomy": request.app.state.treasury_autonomy.state(),
            "system_gas_expenses": SystemGasLedger(
                active.execution.store.db_path, active.execution.chain.settings
            ).history(),
        }

    @app.post("/mvp/workflows", dependencies=protected)
    def run(payload: MvpIntent, request: Request):
        active = service(request)
        try:
            # Never fill every HTTP worker with requests waiting on the same vault.
            with active.execution.exclusive().acquire(timeout=0):
                return active.run(payload.internal(), request.headers.get("Idempotency-Key"))
        except Timeout:
            raise ControlError("MVP_EXECUTION_BUSY_RESUME_REQUEST", 429) from None
        finally:
            readiness_cache["until"] = 0

    @app.get("/mvp/requests/{key}", dependencies=protected)
    def request_by_key(key: str, request: Request):
        active = service(request)
        if not 1 <= len(key) <= 128:
            raise ControlError("INVALID_REQUEST", 400)
        record = active.store.by_key(key)
        if record is None:
            raise ControlError("MVP_REQUEST_NOT_FOUND", 404)
        return active.reconcile(record["workflow_id"])

    @app.get("/mvp/workflows/{id_}", dependencies=protected)
    def workflow(id_: str, request: Request):
        return service(request).reconcile(id_)

    @app.post("/mvp/rebalance", dependencies=protected)
    def rebalance(payload: RebalanceRequest, request: Request):
        try:
            active = service(request)
            with active.execution.exclusive().acquire(timeout=0):
                return active.rebalance(payload, request.headers.get("Idempotency-Key"))
        except Timeout:
            raise ControlError("MVP_EXECUTION_BUSY_RESUME_REQUEST", 429) from None
        except ValueError as exc:
            raise ControlError(str(exc), 409) from None

    class Autonomy(Wire):
        enabled: bool
        session_id: Hash

    @app.post("/mvp/autonomy", dependencies=protected)
    def autonomy(payload: Autonomy, request: Request):
        service(request)
        try:
            return request.app.state.treasury_autonomy.configure(
                payload.enabled, payload.session_id
            )
        except ValueError as exc:
            raise ControlError(str(exc), 409) from None

    class Admin(Wire):
        action: Literal["PAUSE", "UNPAUSE", "REVOKE_SESSION", "REVOKE_POLICY"]
        session_id: Hash | None = None

    @app.post("/mvp/admin/prepare", dependencies=protected)
    def admin(payload: Admin, request: Request):
        # Operator can prepare a fixed request; ONLY the owner EOA can authorize it on-chain.
        active = service(request)
        v = active.execution.chain.vault
        from web3 import Web3

        if payload.action == "REVOKE_SESSION":
            if not payload.session_id:
                raise ControlError("SESSION_REQUIRED", 400)
            fn = v.functions.revokeSession(payload.session_id)
        else:
            fn = getattr(
                v.functions,
                {"PAUSE": "pause", "UNPAUSE": "unpause", "REVOKE_POLICY": "revokePolicy"}[
                    payload.action
                ],
            )()
        return {
            "broadcast": False,
            "requires_owner_wallet": True,
            "owner_transaction": {
                "from": Web3.to_checksum_address(active.execution.manifest.owner),
                "to": v.address,
                "value": "0x0",
                "chainId": hex(active.execution.manifest.chain_id),
                "data": fn._encode_transaction_data(),
            },
        }

    @app.post("/mvp/attack-lab/{case}", dependencies=protected)
    def attack(case: str, request: Request):
        service(request)
        return request.app.state.treasury_attack_lab.run(case)

    if settings.serve_frontend:

        @app.get("/treasury-mvp.html", include_in_schema=False)
        def frontend():
            return FileResponse(
                ROOT / "frontend/treasury-mvp.html",
                headers={
                    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'",
                    "X-Content-Type-Options": "nosniff",
                },
            )
