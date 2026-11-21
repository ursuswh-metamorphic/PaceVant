"""Anonymous fixed-scenario demo API, separate from authenticated treasury operations."""

import hashlib
import json
import secrets
import time
from contextlib import asynccontextmanager
from threading import Lock
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from treasury_backend.config.judge import JudgeSettings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.workflows.judge import SCENARIOS, JudgeController
from treasury_backend.paths import ROOT
from treasury_contracts.http_limits import RequestSizeLimit

COOKIE = "pacevant_judge"


def create_app(settings=None, *, controller=None):
    settings = settings or JudgeSettings.from_env()
    controller = controller or JudgeController(settings)

    @asynccontextmanager
    async def lifespan(app):
        controller.start()
        try:
            yield
        finally:
            controller.close()

    app = FastAPI(title="PaceVant Judge Demo", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestSizeLimit, max_bytes=4096)
    app.state.judge = controller

    @app.middleware("http")
    async def visitor(request, call_next):
        value = request.cookies.get(COOKIE, "")
        new_cookie = not value or len(value) > 100
        if new_cookie:
            value = secrets.token_urlsafe(32)
        request.state.visitor = hashlib.sha256(value.encode()).hexdigest()
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return JSONResponse({"error":{"code":"ORIGIN_NOT_ALLOWED"}}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/judge/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/judge/"):
            response.set_cookie(COOKIE, value, max_age=settings.visitor_session_seconds, httponly=True, secure=settings.secure_cookie, samesite="strict", path="/")
        return response

    @app.exception_handler(ControlError)
    async def error(request, exc):
        return JSONResponse({"error":{"code":exc.code}}, status_code=exc.status,
                            headers={"Retry-After":"5"} if exc.status == 429 else None)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"error":{"code":"INVALID_REQUEST"}}, status_code=400)

    @app.get("/healthz")
    async def health():
        return {"status":"ok", "service":"judge", "public_chain_spending":settings.execution_mode=='REAL_FUJI_EXECUTION'}

    @app.get("/readyz")
    def ready():
        configured = controller.configured()
        return JSONResponse({"ready":configured, "mode":settings.execution_mode, "busy":controller.busy(),
            "reason_code":None if configured else "DEMO_NOT_CONFIGURED"}, status_code=200 if configured else 503)

    def replays():
        path = ROOT / "fixtures/judge/manifest.json"
        return json.loads(path.read_text()) if path.exists() else {}

    @app.get("/judge/config")
    def config(request: Request):
        configured = controller.configured()
        scenarios=[dict(value) for value in SCENARIOS]
        if settings.execution_mode=='REAL_FUJI_EXECUTION':
            scenarios[0]['recipient_label']='One of the three owner-approved system EOAs'
            scenarios[1]['recipient_label']='Public Fuji PolicyVaultMVP'
        return {"enabled":settings.enabled, "mode":settings.execution_mode, "configured":configured, "busy":controller.busy(),
            "reason_code":None if configured else "DEMO_NOT_CONFIGURED", "scenarios":scenarios,
            "quota":{"remaining_today":controller.remaining(request.state.visitor), "daily_limit":settings.daily_limit,
                     "global_daily_limit":settings.global_daily_limit},
            "limits":{"timeout_seconds":settings.timeout_seconds, "max_concurrent":1},
            "replay_available":list(replays()), "semantic_scope":"REAL_CONFIGURED_PROVIDER",
            "operator":{"enabled":False, "reason":"Public MVP deployment requires separate Owner acceptance; operator credentials are never embedded in judge mode"}}

    source_lock = Lock()
    source_cache = {}

    @app.get("/judge/source")
    def source():
        # A pinned source snapshot is honest historical context, not a readiness promise.
        # Active runs supply their own freshly verified context and source block.
        if not source_lock.acquire(blocking=False):
            return source_cache.get("value", {"status":"UNAVAILABLE", "reason_code":"SOURCE_REFRESHING"})
        try:
            if time.monotonic() < source_cache.get("until", 0):
                return source_cache["value"]
            try:
                from treasury_backend.operations.judge_source import observe

                value = observe(settings.rpc_url,settings.manifest_file) if settings.execution_mode=='REAL_FUJI_EXECUTION' else observe(settings.rpc_url)
                source_cache.update(value=value, until=time.monotonic()+60)
                return value
            except Exception:
                if settings.execution_mode=='REAL_FUJI_EXECUTION':
                    return {'status':'UNAVAILABLE','reason_code':'PUBLIC_SOURCE_READ_UNAVAILABLE'}
            path = ROOT / "docs/audit/mvp-readiness-public-state.json"
            if not path.exists():
                return {"status":"UNAVAILABLE", "reason_code":"SOURCE_SNAPSHOT_UNAVAILABLE"}
            saved = json.loads(path.read_text())
            vault = saved["accounts"]["policy_vault"]
            feeds = saved.get("oracle", {}).get("oracle_feeds", [])
            avax = next((feed for feed in feeds if feed.get("description") == "AVAX/USD"), {})
            value = dict(status="RECORDED_SNAPSHOT", observed_at=saved["observed_at"], block_number=saved["block_number"],
                chain_id=43113, balances={"usdc":vault["usdc_base_units"], "wavax":vault["wavax_base_units"]},
                policy={"paused":saved["policy"]["paused"], "active":saved["policy"]["policyActive"],
                    "expires_at":saved["policy"]["policyExpiresAt"], "max_relative_loss_bps":saved["proof_policy"]["max_relative_loss_bps"],
                    "oracle_band_bps":saved["proof_policy"]["oracle_band_bps"]},
                oracle={"status":"RECORDED_NOT_LIVE", "updated_at":avax.get("updated_at"), "source":"CHAINLINK_FUJI"},
                addresses={"treasury":vault["address"], **{k:saved["accounts"][k]["address"] for k in ("owner", "attestor", "relayer")}})
            source_cache.update(value=value, until=time.monotonic()+60)
            return value
        finally:
            source_lock.release()

    class Start(BaseModel):
        model_config = ConfigDict(extra="forbid")
        scenario: Literal["payment", "swap", "guard"]
        attack: Literal["payment-amount", "payment-replay", "swap-slippage", "swap-route"] | None = None

    @app.post("/judge/jobs", status_code=202)
    def start(payload: Start, request: Request):
        return controller.create(request.state.visitor, request.client.host if request.client else "unknown",
                                 payload.scenario, request.headers.get("Idempotency-Key"), attack=payload.attack)

    @app.get("/judge/jobs/{id_}")
    def job(id_: str, request: Request):
        return controller.get(request.state.visitor, id_=id_)

    @app.get("/judge/requests/{key}")
    def by_key(key: str, request: Request):
        return controller.get(request.state.visitor, key=key)

    @app.get("/judge/history")
    def history(request: Request):
        return {"jobs":controller.history(request.state.visitor)}

    @app.get("/judge/replays/{scenario}")
    def replay(scenario: Literal["payment", "swap", "guard"]):
        metadata = replays().get(scenario)
        if not metadata:
            raise ControlError("VERIFIED_REPLAY_UNAVAILABLE", 404)
        content = (ROOT / "fixtures/judge" / metadata["file"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
            raise ControlError("REPLAY_EVIDENCE_HASH_MISMATCH", 503)
        workflow = json.loads(content)
        return {"job_id":"replay_"+scenario, "scenario":scenario, "status":workflow["status"],
            "created_at":workflow["created_at"], "recorded_at":workflow["created_at"], "environment":"VERIFIED_REPLAY",
            "reason_code":workflow.get("reason_code"), "active_stage":metadata.get("active_stage"),
            "workflow":workflow, "public_chain_broadcast":False, "terminal":True,
            "semantic_scope":"RECORDED_REAL_PROVIDER_RUN", "scope":"Recorded evidence, not a new live transaction"}

    dist = ROOT / "frontend/dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="built-frontend-assets")

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def frontend():
        if not (dist / "index.html").is_file():
            return JSONResponse({"error":{"code":"FRONTEND_BUILD_REQUIRED"}}, status_code=503)
        return FileResponse(dist / "index.html", headers={"Cache-Control":"no-cache"})

    @app.get("/judge/documentation")
    def documentation():
        path = ROOT / "JUDGE_DEMO_GUIDE.md"
        return Response(path.read_text() if path.exists() else "Judge demo guide is not installed.", media_type="text/plain")

    return app
