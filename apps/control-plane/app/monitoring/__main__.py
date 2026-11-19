import argparse
import json
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import ControlError
from app.monitoring.api import install_history_routes
from app.monitoring.runtime import ObserverRuntime, ObserverSettings, start_monitor


def create_observer_app(settings=None):
    settings = settings or ObserverSettings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.observer = ObserverRuntime(settings)
        stop, thread = start_monitor(app.state.observer.monitor)
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=45)
            app.state.observer.close()

    app = FastAPI(title="PaceVant Read-only Portfolio Observer", version="2.0", lifespan=lifespan)

    def auth(request: Request):
        if not secrets.compare_digest(
            request.headers.get("Authorization", "").encode(),
            f"Bearer {settings.operator_token}".encode(),
        ):
            raise ControlError("AUTH_REQUIRED", 401)

    @app.exception_handler(ControlError)
    async def control_error(request, error):
        return JSONResponse({"error": {"code": error.code}}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, error):
        return JSONResponse({"error": {"code": "INVALID_REQUEST"}}, status_code=400)

    @app.exception_handler(Exception)
    async def internal(request, error):
        return JSONResponse({"error": {"code": "OBSERVER_UNAVAILABLE"}}, status_code=503)

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok", "mode": settings.mode, "capabilities": ["READ_ONLY"]}

    install_history_routes(
        app,
        [Depends(auth)],
        mode=settings.mode,
        store=lambda r: r.app.state.observer.store,
        refresh=lambda r, vault: r.app.state.observer.observe(vault),
    )
    return app


def main():
    parser = argparse.ArgumentParser(description="Key-free read-only portfolio and outcome monitor")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    settings = ObserverSettings.from_env()
    if args.once:
        runtime = ObserverRuntime(settings)
        try:
            values = runtime.monitor.tick(limit=5)
            print(
                json.dumps(
                    {
                        "read_only": True,
                        "processed": len(values),
                        "states": [v.get("state") for v in values],
                    }
                )
            )
        finally:
            runtime.close()
    else:
        import uvicorn

        uvicorn.run(create_observer_app(settings), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
