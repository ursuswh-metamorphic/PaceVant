"""Shared observer routes and a standalone app that needs only an operator token."""

import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from treasury_backend.config.control import DASHBOARD
from treasury_backend.modules.oracle.fuji.fuji_rpc import FujiReadError
from treasury_backend.modules.oracle.fuji.fuji_service import FujiService

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
)


def install_fuji_routes(app, dependencies, *, serve_frontend=True):
    @app.get("/v1/fuji/wallet/{address}", dependencies=dependencies)
    def wallet(
        address: str, request: Request, vault: str | None = None, tx_hash: str | None = None
    ):
        return request.app.state.fuji.snapshot(address, vault, tx_hash)

    def page():
        return FileResponse(
            DASHBOARD / "fuji-wallet.html",
            headers={
                "Content-Security-Policy": CSP,
                "X-Content-Type-Options": "nosniff",
            },
        )

    if serve_frontend:
        app.add_api_route("/fuji-wallet", page, include_in_schema=False)
        app.add_api_route("/fuji-wallet.html", page, include_in_schema=False)

    @app.exception_handler(FujiReadError)
    async def read_error(request, error):
        status = 503
        if error.code in {"INVALID_WALLET_ADDRESS", "INVALID_TRANSACTION_HASH"}:
            status = 400
        elif error.code == "AUTH_REQUIRED":
            status = 401
        elif error.code in {"FUJI_RATE_LIMITED", "FUJI_READER_BUSY"}:
            status = 429
        return JSONResponse(
            {
                "error": {
                    "code": error.code,
                    "message": error.code.replace("_", " ").capitalize(),
                    "retryable": status in {429, 503},
                    "correlation_id": getattr(request.state, "request_id", "fuji-readonly"),
                },
            },
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )


def create_readonly_app(operator_token=None, service=None):
    token = operator_token or os.environ.get("PACEVANT_OPERATOR_TOKEN")
    if not token or len(token) < 24:
        raise RuntimeError("Set PACEVANT_OPERATOR_TOKEN to a value of at least 24 characters")

    @asynccontextmanager
    async def lifespan(app):
        app.state.fuji = service or FujiService()
        try:
            yield
        finally:
            app.state.fuji.close()

    app = FastAPI(title="PaceVant Fuji Observatory", version="1.1", lifespan=lifespan)

    def operator(request: Request):
        actual = request.headers.get("Authorization", "").encode()
        if not secrets.compare_digest(actual, f"Bearer {token}".encode()):
            raise FujiReadError("AUTH_REQUIRED")

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok", "mode": "FUJI_READONLY", "chain_id": 43113}

    app.mount("/assets", StaticFiles(directory=DASHBOARD / "assets"), name="assets")
    install_fuji_routes(app, [Depends(operator)])
    return app
