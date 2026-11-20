import secrets
import uuid
from contextlib import asynccontextmanager
from fastapi import APIRouter, Depends, FastAPI, Header, Query
from treasury_contracts.models import ExecutionReconciliation
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException
from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.execution.models import (
    BuiltTransaction,
    ExecutionRequest,
    ExecutionResult,
    SimulationEvidence,
    SimulationRequest,
    TransactionProposal,
    ChainContext,
    OnchainSnapshot,
    ExecutionSubmission,
    ErrorEnvelope,
)
from treasury_backend.modules.execution.service import ExecutionService
from treasury_backend.config.execution import Settings
from treasury_backend.core.errors import ControlError
from treasury_contracts.v2 import PreflightV2Request
from treasury_contracts.http_limits import RequestSizeLimit


def create_app(settings=None, chain=None):
    settings = settings or Settings()
    runtime = ExecutionService(settings, chain)

    @asynccontextmanager
    async def lifespan(app):
        if not settings.api_key.get_secret_value():
            raise RuntimeError("B_API_KEY must be configured; no unauthenticated execution service")
        runtime.start()
        for name in ("chain", "builder", "simulator", "relayer"):
            setattr(app.state, name, getattr(runtime, name))
        yield

    app = FastAPI(
        title="Person B Execution Plane",
        version="1.1.0",
        lifespan=lifespan,
        responses={
            **{code: {"model": ErrorEnvelope} for code in (400, 401, 404, 409, 503)},
            422: {"model": ErrorEnvelope, "description": "Unprocessable Content"},
        },
    )
    app.state.store = runtime.store
    app.add_middleware(RequestSizeLimit)
    @app.middleware("http")
    async def request_id(request, call_next):
        incoming = request.headers.get("X-Request-Id", "")
        request.state.request_id = (
            incoming if 1 <= len(incoming) <= 128 and incoming.isprintable() else str(uuid.uuid4())
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def error(request, status, code, message, retryable=False):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": retryable,
                    "correlation_id": getattr(request.state, "request_id", "unknown"),
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(
            request,
            exc.status_code,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "Resource or method unavailable",
        )

    @app.exception_handler(PlaneError)
    async def plane_error(request, exc):
        return error(request, exc.status, exc.code, exc.message, exc.retryable)

    @app.exception_handler(ControlError)
    async def control_error(request, exc):
        return error(request, exc.status, exc.code, exc.code.replace("_", " "), exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never echo submitted PDRs/secrets/unknown request fields in error envelopes.
        return error(request, 400, "INVALID_SCHEMA", "Request does not match integration schema")

    @app.exception_handler(Exception)
    async def unavailable(request, exc):
        return error(
            request,
            503,
            "SERVICE_UNAVAILABLE",
            "RPC or execution subsystem unavailable",
            True,
        )

    app.include_router(create_router(runtime, settings))
    return app


def create_router(runtime, settings):
    app = APIRouter()
    def auth(x_api_key: str | None = Header(default=None)):
        if not x_api_key or not secrets.compare_digest(
            x_api_key, settings.api_key.get_secret_value()
        ):
            raise PlaneError("UNAUTHORIZED", "Valid backend X-API-Key required", 401)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "execution-plane", "version": "1.1"}

    @app.get("/v1/chain/context", response_model=ChainContext, dependencies=[Depends(auth)])
    def context():
        return runtime.chain.context()

    @app.get(
        "/v1/portfolio/onchain-snapshot",
        response_model=OnchainSnapshot,
        dependencies=[Depends(auth)],
    )
    def snapshot(block_number: int | None = Query(default=None, ge=0)):
        return runtime.chain.snapshot(block_number=block_number)

    @app.get("/v1/submissions/by-build/{build_id}", response_model=ExecutionSubmission, dependencies=[Depends(auth)])
    def submission(build_id: str):
        return runtime.relayer.submission_for_build(build_id)

    @app.get("/v1/executions/{tx_hash}/reconciliation", response_model=ExecutionReconciliation, dependencies=[Depends(auth)])
    def reconciliation(tx_hash: str):
        return runtime.relayer.reconciliation(tx_hash)

    @app.post("/v1/build", response_model=BuiltTransaction, dependencies=[Depends(auth)])
    def build(p: TransactionProposal, idempotency_key: str | None = Header(default=None)):
        return runtime.build(p, idempotency_key)

    @app.post(
        "/v1/simulations",
        response_model=SimulationEvidence,
        dependencies=[Depends(auth)],
    )
    def simulate(p: SimulationRequest, idempotency_key: str | None = Header(default=None)):
        return runtime.simulate(p, idempotency_key)

    @app.post(
        "/v1/executions",
        response_model=ExecutionSubmission,
        dependencies=[Depends(auth)],
    )
    def execute(p: ExecutionRequest, idempotency_key: str | None = Header(default=None)):
        return runtime.execute(p, idempotency_key)

    @app.post("/v2/simulations/preflight", dependencies=[Depends(auth)])
    def preflight(p: PreflightV2Request, idempotency_key: str | None = Header(default=None)):
        return runtime.preflight(p, idempotency_key)

    @app.get(
        "/v1/executions/{tx_hash}",
        response_model=ExecutionResult,
        dependencies=[Depends(auth)],
    )
    def result(tx_hash: str):
        return runtime.relayer.monitor(tx_hash)

    @app.get("/v1/artifacts/{content_hash}", dependencies=[Depends(auth)])
    def get_artifact(content_hash: str):
        return Response(
            runtime.store.read_artifact(content_hash),
            media_type="application/json",
            headers={
                "ETag": f'"{content_hash}"',
                "Cache-Control": "private, immutable",
            },
        )

    return app


