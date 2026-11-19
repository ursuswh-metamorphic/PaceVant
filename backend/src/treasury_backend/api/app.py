"""Canonical single-process FastAPI composition for the modular backend."""

from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse

from treasury_backend.api.control import create_app as create_control_app
from treasury_backend.api.execution import create_router
from treasury_backend.api.local_execution import LocalExecutionSDK
from treasury_backend.config.control import Settings
from treasury_backend.config.execution import Settings as ExecutionSettings
from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.execution.service import ExecutionService
from treasury_backend.modules.workflows.client import VerifiedExecutionClient
from treasury_backend.modules.workflows.service import utc_now


def create_app(settings=None, execution_settings=None, clock=utc_now, execution_service=None):
    settings = settings or Settings.from_env(require_execution_http=False)
    runtime = None
    if settings.mode != "MOCK":
        execution_settings = execution_settings or ExecutionSettings(_env_file=None)
        credentials = [
            execution_settings.api_key.get_secret_value(),
            settings.operator_token,
            settings.internal_token,
        ]
        if any(not value or len(value) < 24 for value in credentials) or len(set(credentials)) != 3:
            raise RuntimeError("Use three distinct service credentials of at least 24 characters")
        if (
            execution_settings.mode.upper() != settings.mode
            or execution_settings.rpc_url != settings.chain_rpc_url
        ):
            raise RuntimeError("Control/execution settings must use the same mode and chain RPC")
        runtime = execution_service or ExecutionService(execution_settings)

    def client_factory(request_id, config, store):
        return VerifiedExecutionClient(LocalExecutionSDK(runtime, request_id), config, store)

    app = create_control_app(settings, clock, client_factory=client_factory if runtime else None)
    app.title = "PaceVant Treasury Backend"
    app.state.execution = runtime
    control_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        if runtime is not None:
            runtime.start()
        async with control_lifespan(application):
            yield

    app.router.lifespan_context = lifespan
    if runtime is not None:
        app.include_router(
            create_router(runtime, execution_settings), prefix="/execution", tags=["execution"]
        )

    @app.exception_handler(PlaneError)
    async def execution_error(request, exc):
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    "correlation_id": getattr(request.state, "request_id", "unknown"),
                }
            },
        )

    @app.get("/health", include_in_schema=False)
    def health():
        return {
            "status": "ok",
            "mode": settings.mode,
            "execution_enabled": runtime is not None,
            "execution_transport": "in-process" if runtime is not None else "mock",
            "planner_provider": settings.planning.provider,
            "planner_model": settings.planning.model
            if settings.planning.provider == "groq"
            else None,
        }

    return app
