"""Canonical single-process FastAPI composition for the modular backend."""

from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse

from treasury_backend.api.control import create_app as create_control_app
from treasury_backend.api.demo import install_demo_routes
from treasury_backend.api.execution import create_router
from treasury_backend.api.local_execution import LocalExecutionSDK
from treasury_backend.config.control import Settings
from treasury_backend.config.demo import DemoSettings
from treasury_backend.config.execution import Settings as ExecutionSettings
from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.execution.service import ExecutionService
from treasury_backend.modules.gas_credit import GasCreditLedger
from treasury_backend.modules.monitoring.worker import start_monitor
from treasury_backend.modules.workflows.client import VerifiedExecutionClient
from treasury_backend.modules.workflows.service import utc_now


def create_app(settings=None, execution_settings=None, clock=utc_now, execution_service=None, demo_settings=None):
    settings = settings or Settings.from_env(require_execution_http=False)
    demo = demo_settings or DemoSettings.from_env()
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
    if demo.enabled and (
        runtime is None or not settings.require_itag
        or settings.shield.mode not in {"wallet_pipeline", "wallet_hardened"}
        or demo.access_token in {settings.operator_token, settings.internal_token, execution_settings.api_key.get_secret_value()}
    ):
        raise RuntimeError("Demo requires live execution, required ITAG, hardened Shield and a separate access token")

    def client_factory(request_id, config, store):
        return VerifiedExecutionClient(LocalExecutionSDK(runtime, request_id), config, store)

    app = create_control_app(settings, clock, client_factory=client_factory if runtime else None)
    app.title = "PaceVant Treasury Backend"
    app.state.execution = runtime
    from treasury_backend.api.local_transfers import LocalTransferExecution
    app.state.transfer_execution = LocalTransferExecution(runtime)
    control_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        if runtime is not None:
            runtime.start()
            if settings.mode == "FUJI" and (
                runtime.chain.deployment.get("adapter_version") != "lfj-v1-fuji-v1"
                or runtime.chain.deployment.get("pdr_version") != "2"
            ):
                raise RuntimeError("FUJI serving requires the live LFJ V2 deployment; use LOCAL for mock contracts")
        async with control_lifespan(application):
            if demo.enabled:
                chain = runtime.chain
                gas = GasCreditLedger(runtime.store.db_path, demo, chain_id=chain.chain_id,
                                      vault=chain.deployment["vault_address"], relayer=chain.deployment["relayer"],
                                      confirmations=execution_settings.required_confirmations)
                application.state.gas_credit = gas
                runtime.gas_credit = runtime.relayer.gas_credit = gas
                application.state.control.monitor.fee_observer = gas.reconcile
            worker = start_monitor(application.state.control.monitor) if runtime is not None else None
            try:
                yield
            finally:
                if worker:
                    worker[0].set()
                    worker[1].join(timeout=45)

    app.router.lifespan_context = lifespan
    from treasury_backend.modules.transfers.api import install_transfer_routes
    install_transfer_routes(app,settings)
    install_demo_routes(app, demo)
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
            "task_shield_mode": settings.shield.mode,
            "require_itag": settings.require_itag,
            "shield_provider": settings.shield.provider,
            "shield_model": settings.shield.model,
            "shield_fallback_models": [c.model for c in settings.shield.fallbacks],
            "planner_model": settings.planning.model
            if settings.planning.provider == "groq"
            else None,
        }

    return app
