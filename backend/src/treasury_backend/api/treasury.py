"""Operator-only V3 routes; demo credentials cannot execute or administer V3."""

import secrets
from typing import Literal

from fastapi import Depends, Request
from web3 import Web3

from treasury_backend.core.errors import ControlError
from treasury_contracts.v3 import ZERO, Addr, Hash, OperationIntent, RebalanceRequest, UInt, Wire


class AutonomyRequest(Wire):
    enabled: bool
    session_id: Hash


class AdminRequest(Wire):
    action: Literal[
        "PAUSE",
        "UNPAUSE",
        "REVOKE_SESSION",
        "REVOKE_POLICY",
        "SET_TOKEN",
        "SET_ADAPTER",
        "SET_PAYEE",
    ]
    session_id: Hash | None = None
    token: Addr | None = None
    recipient: Addr | None = None
    allowed: bool = False
    per_payment: UInt = "0"
    per_day: UInt = "0"


def install_treasury_routes(app, settings):
    if settings.serve_frontend:
        from fastapi.responses import FileResponse

        from treasury_backend.paths import ROOT

        @app.get("/treasury-v3.html", include_in_schema=False)
        def frontend():
            return FileResponse(
                ROOT / "frontend/treasury-v3.html",
                headers={
                    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    def operator(request: Request):
        expected = settings.operator_token
        if not expected or not secrets.compare_digest(
            request.headers.get("Authorization", "").encode(), ("Bearer " + expected).encode()
        ):
            raise ControlError("AUTH_REQUIRED", 401)

    def treasury(request: Request):
        service = getattr(request.app.state, "treasury_v3", None)
        if service is None:
            raise ControlError("V3_OWNER_MIGRATION_REQUIRED", 503)
        return service

    auth = [Depends(operator)]

    @app.get("/v3/capabilities")
    def capabilities(request: Request):
        active = getattr(request.app.state, "treasury_v3", None)
        return {
            "enabled": active is not None,
            "environment": active.execution.manifest.environment if active else None,
            "operations": [
                "TOKEN_SWAP",
                "TOKEN_PAYMENT",
                "VAULT_DEPOSIT",
                "VAULT_WITHDRAW",
                "TREASURY_REBALANCE",
            ]
            if active
            else [],
            "public_fuji_v3": False,
            "vault_label": "LOCAL DEMONSTRATION: no production yield",
            "default_session_id": active.execution.manifest.default_session_id if active else None,
            "reason": None
            if active
            else "V3 requires an explicit isolated deployment; existing Fuji V2 remains available",
        }

    @app.get("/v3/treasury/{session_id}", dependencies=auth)
    def dashboard(session_id: str, request: Request):
        service = treasury(request)
        from pydantic import TypeAdapter

        try:
            TypeAdapter(Hash).validate_python(session_id)
            context = service.execution.display_context(session_id)
        except ValueError:
            raise ControlError("V3_CONTEXT_UNAVAILABLE", 409) from None
        return {
            "context": context,
            "targets": service.execution.manifest.rebalance_policy.model_dump(mode="json"),
            "history": service.store.history(),
            "autonomy": request.app.state.treasury_autonomy.state(),
        }

    @app.post("/v3/workflows", dependencies=auth)
    def operation(payload: OperationIntent, request: Request):
        return treasury(request).run(payload, request.headers.get("Idempotency-Key"))

    @app.get("/v3/workflows/{id_}", dependencies=auth)
    def workflow(id_: str, request: Request):
        return treasury(request).reconcile(id_)

    @app.post("/v3/rebalance", dependencies=auth)
    def rebalance(payload: RebalanceRequest, request: Request):
        try:
            return treasury(request).rebalance(payload, request.headers.get("Idempotency-Key"))
        except ValueError as exc:
            raise ControlError(str(exc), 409) from None

    @app.post("/v3/autonomy", dependencies=auth)
    def autonomy(payload: AutonomyRequest, request: Request):
        treasury(request)
        try:
            return request.app.state.treasury_autonomy.configure(
                payload.enabled, payload.session_id
            )
        except ValueError as exc:
            raise ControlError(str(exc), 409) from None

    @app.post("/v3/admin/prepare", dependencies=auth)
    def admin(payload: AdminRequest, request: Request):
        chain = treasury(request).execution.chain
        chain.isolated()
        v, m = chain.vault.functions, chain.manifest
        if payload.action == "PAUSE":
            fn = v.pause()
        elif payload.action == "UNPAUSE":
            fn = v.unpause()
        elif payload.action == "REVOKE_POLICY":
            fn = v.revokePolicy()
        elif payload.action == "REVOKE_SESSION" and payload.session_id:
            fn = v.revokeSession(payload.session_id)
        elif payload.action == "SET_TOKEN" and payload.token in {m.usdc, m.wavax}:
            fn = v.setToken(Web3.to_checksum_address(payload.token), payload.allowed)
        elif payload.action == "SET_ADAPTER":
            fn = v.setRouter(Web3.to_checksum_address(m.adapter), payload.allowed)
        elif (
            payload.action == "SET_PAYEE"
            and payload.recipient
            and payload.token in {m.usdc, m.wavax, ZERO}
            and int(payload.per_day) >= int(payload.per_payment)
        ):
            fn = v.setPayee(
                Web3.to_checksum_address(payload.token),
                Web3.to_checksum_address(payload.recipient),
                int(payload.per_payment),
                int(payload.per_day),
            )
        else:
            raise ControlError("INVALID_ADMIN_REQUEST", 400)
        return {
            "owner_transaction": {
                "from": Web3.to_checksum_address(m.owner),
                "to": chain.vault.address,
                "chainId": hex(m.chain_id),
                "value": "0x0",
                "data": fn._encode_transaction_data(),
            },
            "broadcast": False,
            "requires_owner_wallet": True,
            "policy_invalidation": payload.action not in {"PAUSE", "UNPAUSE", "REVOKE_SESSION"},
        }

    @app.post("/v3/attack-lab/{case}", dependencies=auth)
    def attack(case: str, request: Request):
        treasury(request)
        return request.app.state.treasury_attack_lab.run(case)
