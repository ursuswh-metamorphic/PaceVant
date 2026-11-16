from typing import Protocol
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.errors import ControlError
from app.models import ChainBalances, ChainContext
from app.orchestration.evidence import json_object
from treasury_contract.wire import (
    BuiltTransaction,
    ExecutionResult,
    ExecutionSubmission,
    SignedPDR,
    SimulationEvidence,
    TransactionProposal,
)

DOMAIN_ERRORS = {
    "TOKEN_NOT_ALLOWED",
    "ROUTER_NOT_ALLOWED",
    "BAD_RECIPIENT",
    "TRADE_SIZE_LIMIT",
    "BAD_PRICE_OR_SLIPPAGE",
    "POLICY_REVOKED",
    "HASH_MISMATCH",
    "SIMULATION_INCOMPLETE",
    "NONCE_REPLAY",
    "STALE_REQUIRES_REEVALUATION",
    "BAD_SIGNATURE",
    "REQUIRED_STRESS_NOT_SATISFIED",
}
MAX_RESPONSE_BYTES = 1_048_576


class ExecutionClient(Protocol):
    def context(
        self, *, nonce: str | None = None, fork_block: int | None = None
    ) -> ChainContext: ...
    def balances(self) -> ChainBalances: ...
    def build(self, proposal: TransactionProposal) -> BuiltTransaction: ...
    def simulate(self, built: BuiltTransaction) -> SimulationEvidence: ...
    def artifact(self, reference: str) -> bytes: ...
    def execute(self, built: BuiltTransaction, pdr: SignedPDR) -> ExecutionSubmission: ...
    def execution(self, tx_hash: str) -> ExecutionResult: ...


class RestExecutionClient:
    def __init__(self, http: httpx.Client, request_id: str):
        self.http = http
        self.request_id = request_id

    def _request(self, method, path, *, key=None, body=None, params=None, retry=True) -> bytes:
        headers = {"X-Request-Id": self.request_id}
        if key:
            headers["Idempotency-Key"] = key
        for attempt in range(2 if retry else 1):
            try:
                with self.http.stream(
                    method, path, json=body, params=params, headers=headers
                ) as response:
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ControlError("EXECUTION_PLANE_RESPONSE_TOO_LARGE", 503)
                        data.extend(chunk)
                    if response.is_success:
                        return bytes(data)
                    if response.status_code == 503 and retry and attempt == 0:
                        continue
                    if 400 <= response.status_code < 500:
                        error = json_object(data).get("error") if data else None
                        code = error.get("code") if isinstance(error, dict) else None
                        if isinstance(code, str) and code in DOMAIN_ERRORS:
                            raise ControlError(code, response.status_code)
                    raise ControlError("EXECUTION_PLANE_UNAVAILABLE", 503, retryable=True)
            except httpx.RequestError:
                if not retry or attempt == 1:
                    raise ControlError("EXECUTION_PLANE_UNAVAILABLE", 503, retryable=True) from None
            except (ValueError, RecursionError):
                raise ControlError("INVALID_EXECUTION_PLANE_RESPONSE", 503) from None
        raise ControlError("EXECUTION_PLANE_UNAVAILABLE", 503, retryable=True)

    def _model(self, model, method, path, **options):
        try:
            return model.model_validate(json_object(self._request(method, path, **options)))
        except (ValueError, ValidationError, RecursionError):
            raise ControlError("INVALID_EXECUTION_PLANE_RESPONSE", 503) from None

    def context(self, *, nonce=None, fork_block=None):
        params = {
            k: v for k, v in {"nonce": nonce, "fork_block": fork_block}.items() if v is not None
        }
        return self._model(ChainContext, "GET", "/v1/chain/context", params=params)

    def balances(self):
        return self._model(ChainBalances, "GET", "/v1/portfolio/onchain-snapshot")

    def build(self, proposal):
        return self._model(
            BuiltTransaction,
            "POST",
            "/v1/build",
            key=f"build-{proposal.intent_id}",
            body=proposal.model_dump(),
        )

    def simulate(self, built):
        return self._model(
            SimulationEvidence,
            "POST",
            "/v1/simulations",
            key=f"simulate-{built.build_id}",
            body={"build_id": built.build_id, "expected_policy_hash": built.policy_hash},
        )

    def artifact(self, reference):
        # Reference is a logical ID. B resolves it through a same-origin authenticated route.
        path = reference.removeprefix("artifact://").split("/")
        if any(part in {"", ".", ".."} for part in path):
            raise ControlError("HASH_MISMATCH")
        return self._request("GET", "/v1/artifacts/" + "/".join(quote(p, safe="") for p in path))

    def execute(self, built, pdr):
        return self._model(
            ExecutionSubmission,
            "POST",
            "/v1/executions",
            retry=False,
            key=f"execute-{pdr.decision_id}",
            body={"build_id": built.build_id, "signed_pdr": pdr.model_dump()},
        )

    def execution(self, tx_hash):
        return self._model(ExecutionResult, "GET", f"/v1/executions/{tx_hash}")
