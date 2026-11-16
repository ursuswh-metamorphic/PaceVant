import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import StringConstraints
from starlette.exceptions import HTTPException

from app.alignment import check
from app.domain import EconomicRiskAssessment, Id, SecurityDecision
from app.errors import ControlError
from app.models import Alignment, Goal, WorkflowRequest
from app.orchestration.service import ControlPlane, utc_now
from app.settings import DASHBOARD, Settings
from treasury_contracts.models import Hash, SignedPDR, SimulationEvidence, TransactionProposal, Wire


class AttestRequest(Wire):
    decision_id: Id


class AlignmentRequest(Wire):
    proposal: TransactionProposal
    goal: Goal
    tool_output: Annotated[str, StringConstraints(max_length=4000)] = ""


class RiskRequest(Wire):
    evidence: SimulationEvidence
    snapshot_id: Id


class DecisionRequest(Wire):
    intent_id: Id
    build_id: Id | None = None
    snapshot_id: Id | None = None
    simulation_evidence_root: Hash | None = None
    alignment: Alignment


MESSAGES = {
    "AUTH_REQUIRED": "A valid service credential is required",
    "INVALID_REQUEST": "The request does not match the expected schema",
    "INTERNAL_ERROR": "The control plane could not complete the request",
    "STALE_REQUIRES_REEVALUATION": "Live state no longer matches the approval",
}


def error_response(request, code, status, retryable=False):
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": MESSAGES.get(code, code.replace("_", " ").capitalize()),
                "retryable": retryable,
                "correlation_id": getattr(request.state, "request_id", "unassigned"),
            }
        },
        status_code=status,
    )


def create_app(settings=None, clock=utc_now):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.control = ControlPlane(settings, clock)
        try:
            yield
        finally:
            app.state.control.close()

    app = FastAPI(title="PaceVant Treasury Control Plane", version="1.1", lifespan=lifespan)

    @app.middleware("http")
    async def correlation(request, call_next):
        incoming = request.headers.get("X-Request-Id", "")
        safe_id = (
            len(incoming) <= 100
            and incoming.isascii()
            and all(char.isalnum() or char in "_-" for char in incoming)
        )
        request.state.request_id = incoming if incoming and safe_id else f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ControlError)
    async def control_error(request, exc):
        return error_response(request, exc.code, exc.status, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return error_response(request, "INVALID_REQUEST", 400)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return error_response(request, code, exc.status_code)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return error_response(request, "INTERNAL_ERROR", 500)

    def control(request: Request):
        return request.app.state.control

    Service = Annotated[ControlPlane, Depends(control)]

    def auth(request: Request, token: str | None):
        actual = request.headers.get("Authorization", "")
        if token is None or not secrets.compare_digest(actual.encode(), f"Bearer {token}".encode()):
            raise ControlError("AUTH_REQUIRED", 401)

    def operator(request: Request):
        if settings.mode != "MOCK" or settings.operator_token is not None:
            auth(request, settings.operator_token)

    def internal(request: Request):
        auth(request, settings.internal_token)

    def json_post(request: Request):
        if request.headers.get("Content-Type", "").split(";")[0].lower() != "application/json":
            raise ControlError("INVALID_REQUEST", 400)

    @app.get("/healthz")
    def health():
        return {"status": "ok", "mode": settings.mode}

    @app.post("/v1/workflows/start", dependencies=[Depends(operator), Depends(json_post)])
    def workflow_start(payload: WorkflowRequest, service: Service):
        return service.run(payload)

    @app.post(
        "/v1/agent/propose", dependencies=[Depends(operator)], response_model=TransactionProposal
    )
    def propose(payload: WorkflowRequest, service: Service):
        if payload.scenario is not None:
            raise ControlError("INVALID_REQUEST", 400)
        return service.standalone_proposal(payload.goal, payload.mandate_id)

    @app.post("/v1/alignment/check", dependencies=[Depends(operator)], response_model=Alignment)
    def align(payload: AlignmentRequest, service: Service):
        return check(
            service.mandate(payload.proposal.mandate_id),
            payload.proposal,
            payload.goal,
            payload.tool_output,
        )

    @app.post(
        "/v1/risk/evaluate", dependencies=[Depends(operator)], response_model=EconomicRiskAssessment
    )
    def evaluate_risk(payload: RiskRequest, service: Service):
        return service.saved_risk(payload.evidence, payload.snapshot_id)

    @app.post("/v1/decisions", dependencies=[Depends(operator)], response_model=SecurityDecision)
    def decision(payload: DecisionRequest, service: Service):
        return service.saved_decision(payload)

    @app.post("/v1/approvals/attest", dependencies=[Depends(internal)], response_model=SignedPDR)
    def attest(payload: AttestRequest, service: Service):
        return service.attest(payload.decision_id)

    @app.get("/v1/workflows/{id}", dependencies=[Depends(operator)])
    def workflow(id: Id, service: Service):
        return service.workflow(id)

    @app.get("/v1/treasury", dependencies=[Depends(operator)])
    def treasury(request: Request, service: Service):
        return service.treasury(request.state.request_id)

    if settings.mode == "MOCK":
        app.mount("/assets", StaticFiles(directory=DASHBOARD), name="assets")

        @app.get("/", include_in_schema=False)
        def dashboard():
            return FileResponse(
                DASHBOARD / "index.html",
                headers={
                    "Content-Security-Policy": (
                        "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
                    ),
                    "X-Content-Type-Options": "nosniff",
                },
            )

    return app
