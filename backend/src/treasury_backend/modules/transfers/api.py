"""Operator-only LOCAL transfer endpoints."""

import secrets
from typing import Annotated

from fastapi import Depends, Request

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.transfers.service import TransferService
from treasury_contracts.transfer import TransferRequest, TransferTask


def install_transfer_routes(app, settings):
    def service(request: Request):
        token = request.headers.get("Authorization", "")
        if not settings.operator_token or not secrets.compare_digest(
            token, "Bearer " + settings.operator_token
        ):
            raise ControlError("AUTH_REQUIRED", 401)
        execution = request.app.state.transfer_execution
        control = request.app.state.control
        if not hasattr(control, "transfers"):
            control.transfers = TransferService(control, execution)
        return control.transfers

    Service = Annotated[TransferService, Depends(service)]

    @app.post("/v1/transfers/tasks")
    def authorize(payload: TransferTask, transfers: Service):
        return transfers.authorize(payload)

    @app.post("/v1/transfers/tasks/{task_id}/cancel")
    def cancel(task_id: str, transfers: Service):
        return transfers.cancel(task_id)

    @app.post("/v1/transfers")
    def transfer(payload: TransferRequest, transfers: Service):
        return transfers.run(payload)

    @app.get("/v1/transfers/{request_id}")
    def get(request_id: str, transfers: Service):
        transfers.local()
        return transfers.read(request_id)

    @app.post("/v1/transfers/{request_id}/reconcile")
    def reconcile(request_id: str, transfers: Service):
        return transfers.reconcile(request_id)
