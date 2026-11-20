"""In-process SDK adapter. No sockets, loopback HTTP or second FastAPI app."""

import logging

import httpx
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.gas_credit import CreditError
from treasury_backend.modules.workflows.client import MAX_RESPONSE_BYTES
from treasury_contracts.client import ExecutionAPIError, ExecutionClient
from treasury_contracts.models import ExecutionRequest, SimulationRequest, TransactionProposal
from treasury_contracts.v2 import PreflightV2Request


class LocalExecutionSDK(ExecutionClient):
    """Reuse wire/evidence verification while dispatching directly to the module."""

    def __init__(self, service, request_id):
        self.service = service
        self.request_id = request_id

    def close(self):
        # The FastAPI lifespan owns the execution module; no HTTP pool is created.
        pass

    def _request(self, method, path, **options):
        request = httpx.Request(method, "http://execution.internal" + path)
        try:
            result, raw = self._dispatch(method, path, options)
            response = (
                httpx.Response(200, content=result, request=request)
                if raw
                else httpx.Response(200, json=jsonable_encoder(result), request=request)
            )
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise PlaneError(
                    "EXECUTION_PLANE_RESPONSE_TOO_LARGE", "Execution result too large", 503
                )
        except ValidationError:
            raise self._error(request, 400, "INVALID_SCHEMA", False) from None
        except CreditError as exc:
            raise self._error(request, 409, exc.code, False) from None
        except PlaneError as exc:
            logging.getLogger(__name__).warning("Execution operation %s failed: %s", path, exc.code)
            raise self._error(request, exc.status, exc.code, exc.retryable) from None
        except Exception as exc:
            logging.getLogger(__name__).error("Execution operation %s failed: %s", path, type(exc).__name__)
            raise self._error(request, 503, "SERVICE_UNAVAILABLE", True) from None
        return response

    def _error(self, request, status, code, retryable):
        return ExecutionAPIError(
            httpx.Response(
                status,
                request=request,
                json={
                    "error": {
                        "code": code,
                        "message": "Execution module request failed",
                        "retryable": retryable,
                        "correlation_id": self.request_id,
                    }
                },
            )
        )

    def _dispatch(self, method, path, options):
        service = self.service
        body = options.get("json")
        key = options.get("headers", {}).get("Idempotency-Key")
        if method == "GET":
            if path == "/v1/chain/context":
                return service.chain.context(), False
            if path == "/v1/portfolio/onchain-snapshot":
                return service.chain.snapshot(block_number=options.get("params", {}).get("block_number")), False
            if path.startswith("/v1/submissions/by-build/"):
                return service.relayer.submission_for_build(path.removeprefix("/v1/submissions/by-build/")), False
            if path.startswith("/v1/executions/") and path.endswith("/reconciliation"):
                return service.relayer.reconciliation(path.removeprefix("/v1/executions/").removesuffix("/reconciliation")), False
            if path.startswith("/v1/artifacts/"):
                return service.store.read_artifact(path.removeprefix("/v1/artifacts/")), True
            if path.startswith("/v1/executions/"):
                return service.relayer.monitor(path.removeprefix("/v1/executions/")), False
        if method == "POST":
            if path == "/v1/build":
                return service.build(TransactionProposal.model_validate(body), key, workflow_id=self.request_id), False
            if path == "/v1/simulations":
                return service.simulate(SimulationRequest.model_validate(body), key), False
            if path == "/v2/simulations/preflight":
                return service.preflight(PreflightV2Request.model_validate(body), key), False
            if path == "/v1/executions":
                return service.execute(ExecutionRequest.model_validate(body), key), False
        raise PlaneError("NOT_FOUND", "Unknown module operation", 404)
