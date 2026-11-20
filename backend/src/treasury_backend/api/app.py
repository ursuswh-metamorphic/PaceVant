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


def create_app(settings=None, execution_settings=None, clock=utc_now, execution_service=None, demo_settings=None,
               treasury_execution=None, legacy_demo_tests=False, semantic_provider=None):
    settings = settings or Settings.from_env(require_execution_http=False)
    # Environment cannot resurrect the retired Demo User product flow.
    demo = demo_settings or DemoSettings()
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
    if demo.enabled and (not legacy_demo_tests or settings.mode!="LOCAL"):
        raise RuntimeError("Demo User is retired; legacy billing is available only to isolated LOCAL regression fixtures")

    def client_factory(request_id, config, store):
        return VerifiedExecutionClient(LocalExecutionSDK(runtime, request_id), config, store)

    if semantic_provider is not None and settings.mode!="LOCAL":
        raise RuntimeError("Explicit semantic fixtures are restricted to LOCAL tests")
    app = create_control_app(settings, clock, client_factory=client_factory if runtime else None,shield_provider=semantic_provider)
    app.title = "PaceVant Treasury Backend"
    app.state.execution = runtime
    app.state.treasury_v3 = None
    app.state.treasury_mvp = None
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
            autonomy = None
            mvp_runtime = treasury_execution
            if settings.v3_manifest_file is not None:
                raise RuntimeError("V3 investment-vault/native-payment rollout is disabled in the two-operation MVP")
            if mvp_runtime is None and settings.mvp_manifest_file is not None:
                from treasury_backend.modules.execution.mvp import MvpExecution
                from treasury_contracts.mvp import MvpManifest
                if runtime is None:
                    raise RuntimeError("MVP requires an explicit execution runtime")
                manifest = MvpManifest.model_validate_json(settings.mvp_manifest_file.read_bytes())
                mvp_runtime = MvpExecution(execution_settings, manifest, runtime.store,live_enabled=settings.mvp_live_enabled)
            if mvp_runtime is not None:
                from treasury_backend.modules.workflows.attack_lab import AttackLab
                from treasury_backend.modules.workflows.autonomy import AutonomousTreasury
                from treasury_backend.modules.workflows.treasury import TreasuryWorkflows
                if getattr(mvp_runtime,"protocol",None)!="PACEVANT_MVP" or not settings.require_itag:
                    raise RuntimeError("MVP permits only its two-operation execution port with required ITAG")
                mvp_runtime.chain.isolated()
                application.state.treasury_mvp = TreasuryWorkflows(application.state.control, mvp_runtime)
                autonomy = AutonomousTreasury(application.state.treasury_mvp)
                application.state.treasury_autonomy = autonomy
                application.state.treasury_attack_lab = AttackLab()
                autonomy.start()
            if demo.enabled:
                if not runtime.chain.w3.client_version.lower().startswith("anvil"):
                    raise RuntimeError("Legacy demo regression fixtures require Anvil")
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
                if autonomy:
                    autonomy.close()
                if worker:
                    worker[0].set()
                    worker[1].join(timeout=45)

    app.router.lifespan_context = lifespan
    install_demo_routes(app, demo)
    from treasury_backend.api.mvp import install_mvp_routes
    install_mvp_routes(app, settings)

    @app.middleware("http")
    async def mvp_mutation_boundary(request,call_next):
        if (getattr(app.state,"treasury_mvp",None) is not None and request.method not in {"GET","HEAD","OPTIONS"}
            and (request.url.path.startswith("/execution/") or request.url.path in {
                "/v1/workflows/start","/v1/agent/propose","/v1/approvals/attest"})):
            return JSONResponse(status_code=410,content={"error":{"code":"MVP_USE_TYPED_OPERATIONS"}})
        return await call_next(request)
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
    async def health():
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
