import secrets
import uuid
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException
from ..chain import Chain
from ..errors import PlaneError
from ..execution.relayer import Relayer
from ..models import (
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
from ..settings import Settings
from ..simulation.runner import Simulator
from ..store import Store
from ..transaction.builder import Builder


def create_app(settings=None, chain=None):
    settings = settings or Settings()
    store = Store(settings.data_dir)

    @asynccontextmanager
    async def lifespan(app):
        if not settings.api_key.get_secret_value():
            raise RuntimeError(
                "B_API_KEY must be configured; no unauthenticated execution service"
            )
        app.state.chain = chain or Chain(settings)
        app.state.builder = Builder(app.state.chain, store)
        app.state.simulator = Simulator(app.state.chain, store)
        app.state.relayer = Relayer(app.state.chain, store)
        yield

    app = FastAPI(
        title="Person B Execution Plane",
        version="1.1.0",
        lifespan=lifespan,
        responses={
            code: {"model": ErrorEnvelope} for code in (400, 401, 404, 409, 422, 503)
        },
    )
    app.state.store = store

    def auth(x_api_key: str | None = Header(default=None)):
        if not x_api_key or not secrets.compare_digest(
            x_api_key, settings.api_key.get_secret_value()
        ):
            raise PlaneError("UNAUTHORIZED", "Valid backend X-API-Key required", 401)

    @app.middleware("http")
    async def request_id(request, call_next):
        incoming = request.headers.get("X-Request-Id", "")
        request.state.request_id = (
            incoming
            if 1 <= len(incoming) <= 128 and incoming.isprintable()
            else str(uuid.uuid4())
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

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never echo submitted PDRs/secrets/unknown request fields in error envelopes.
        return error(
            request, 400, "INVALID_SCHEMA", "Request does not match integration schema"
        )

    @app.exception_handler(Exception)
    async def unavailable(request, exc):
        return error(
            request,
            503,
            "SERVICE_UNAVAILABLE",
            "RPC or execution subsystem unavailable",
            True,
        )

    def mutate(scope, key, body, fn):
        if key is None or not 1 <= len(key) <= 128:
            raise PlaneError(
                "INVALID_SCHEMA",
                "Idempotency-Key header (1..128 chars) is required",
                400,
            )
        with store.lock:
            return store.idempotent(scope, key, body, fn, refresh=scope == "execute")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "execution-plane", "version": "1.1"}

    @app.get(
        "/v1/chain/context", response_model=ChainContext, dependencies=[Depends(auth)]
    )
    def context():
        return app.state.chain.context()

    @app.get(
        "/v1/portfolio/onchain-snapshot",
        response_model=OnchainSnapshot,
        dependencies=[Depends(auth)],
    )
    def snapshot():
        return app.state.chain.snapshot()

    @app.post(
        "/v1/build", response_model=BuiltTransaction, dependencies=[Depends(auth)]
    )
    def build(
        p: TransactionProposal, idempotency_key: str | None = Header(default=None)
    ):
        return mutate(
            "build", idempotency_key, p.model_dump(), lambda: app.state.builder.build(p)
        )

    @app.post(
        "/v1/simulations",
        response_model=SimulationEvidence,
        dependencies=[Depends(auth)],
    )
    def simulate(
        p: SimulationRequest, idempotency_key: str | None = Header(default=None)
    ):
        return mutate(
            "simulate",
            idempotency_key,
            p.model_dump(),
            lambda: app.state.simulator.simulate(p.build_id, p.expected_policy_hash),
        )

    @app.post(
        "/v1/executions",
        response_model=ExecutionSubmission,
        dependencies=[Depends(auth)],
    )
    def execute(
        p: ExecutionRequest, idempotency_key: str | None = Header(default=None)
    ):
        return mutate(
            "execute",
            idempotency_key,
            p.model_dump(),
            lambda: app.state.relayer.execute(p),
        )

    @app.get(
        "/v1/executions/{tx_hash}",
        response_model=ExecutionResult,
        dependencies=[Depends(auth)],
    )
    def result(tx_hash: str):
        return app.state.relayer.monitor(tx_hash)

    @app.get("/v1/artifacts/{content_hash}", dependencies=[Depends(auth)])
    def get_artifact(content_hash: str):
        return Response(
            store.read_artifact(content_hash),
            media_type="application/json",
            headers={
                "ETag": f'"{content_hash}"',
                "Cache-Control": "private, immutable",
            },
        )

    return app


app = create_app()
