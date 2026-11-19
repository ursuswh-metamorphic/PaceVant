"""A's execution-plane HTTP client. Decisions and attestation remain A's responsibility."""

import re
import httpx
from .crypto import canonical, content_hash, keccak
from .models import (
    BuiltTransaction,
    SimulationEvidence,
    SignedPDR,
    TransactionProposal,
    ExecutionResult,
    ChainContext,
    OnchainSnapshot,
    ExecutionSubmission,
    ErrorDetail,
    ErrorEnvelope,
)


class ExecutionAPIError(httpx.HTTPStatusError):
    """Structured B error; compatible with existing httpx.HTTPStatusError handlers."""

    def __init__(self, response: httpx.Response):
        try:
            detail = ErrorEnvelope.model_validate(response.json()).error
        except ValueError:
            detail = ErrorDetail(
                code="HTTP_ERROR",
                message="Execution API request failed",
                retryable=False,
                correlation_id=response.headers.get("X-Request-ID", "unknown"),
            )
        self.code = detail.code
        self.retryable = detail.retryable
        self.correlation_id = detail.correlation_id
        self.status_code = response.status_code
        super().__init__(
            f"{detail.code}: {detail.message}",
            request=response.request,
            response=response,
        )


class ExecutionClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 90,
        request_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        headers = {"X-API-Key": api_key}
        if request_id:
            headers["X-Request-ID"] = request_id
        self.http = httpx.Client(
            base_url=base_url, timeout=timeout, headers=headers, transport=transport
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.http.close()

    def _request(self, method, path, **kwargs):
        response = self.http.request(method, path, **kwargs)
        if response.is_error:
            raise ExecutionAPIError(response)
        response.raise_for_status()
        return response

    def _post(self, path, body, idempotency_key):
        r = self._request(
            "POST", path, json=body, headers={"Idempotency-Key": idempotency_key}
        )
        return r.json()

    def context(self):
        return ChainContext.model_validate(
            self._request("GET", "/v1/chain/context").json()
        ).model_dump()

    def snapshot(self):
        return OnchainSnapshot.model_validate(
            self._request("GET", "/v1/portfolio/onchain-snapshot").json()
        ).model_dump()

    def build(
        self, proposal: TransactionProposal, idempotency_key: str
    ) -> BuiltTransaction:
        return BuiltTransaction.model_validate(
            self._post("/v1/build", proposal.model_dump(), idempotency_key)
        )

    def simulate(
        self, build: BuiltTransaction, idempotency_key: str
    ) -> SimulationEvidence:
        return SimulationEvidence.model_validate(
            self._post(
                "/v1/simulations",
                {"build_id": build.build_id, "expected_policy_hash": build.policy_hash},
                idempotency_key,
            )
        )

    def artifact(self, ref: str):
        # Do not forward backend credentials to arbitrary artifact URLs.
        match = re.fullmatch(r"/v1/artifacts/([0-9a-f]{64})", ref)
        if not match:
            raise ValueError("Untrusted artifact reference")
        r = self._request("GET", ref)
        if keccak(r.content) != "0x" + match[1]:
            raise ValueError("Artifact content hash mismatch")
        value = r.json()
        if canonical(value) != r.content:
            raise ValueError("Artifact is not RFC 8785 canonical JSON")
        return value

    def verify_evidence(self, build: BuiltTransaction, evidence: SimulationEvidence):
        for name in (
            "intent_id",
            "build_id",
            "chain_id",
            "vault_address",
            "policy_hash",
            "calldata_hash",
            "nonce",
            "deadline",
        ):
            if getattr(build, name) != getattr(evidence, name):
                raise ValueError(f"Evidence binding mismatch: {name}")
        manifest = self.artifact(evidence.evidence_manifest_ref)
        if manifest.get("effects_v2") != (evidence.effects_v2.model_dump(mode="json") if evidence.effects_v2 else None):
            raise ValueError("V2 effects differ from committed manifest")
        if content_hash(manifest) != evidence.evidence_root:
            raise ValueError("Evidence root mismatch")
        for name in (
            "build_id",
            "intent_id",
            "chain_id",
            "vault_address",
            "policy_hash",
            "calldata_hash",
            "nonce",
            "deadline",
            "bytecode_hash",
            "fork_block",
            "verification_status",
            "source",
            "simulation_mode",
            "parser_version",
        ):
            if manifest.get(name) != getattr(evidence, name):
                raise ValueError(f"Manifest binding mismatch: {name}")
        if manifest["baseline"] != evidence.baseline.model_dump() or manifest[
            "stress_tests"
        ] != [x.model_dump() for x in evidence.stress_tests]:
            raise ValueError("Report facts differ from committed manifest")
        if evidence.artifact_refs != [a["ref"] for a in manifest["scenario_artifacts"]]:
            raise ValueError("Artifact list mismatch")
        for artifact in manifest["scenario_artifacts"]:
            raw = self.artifact(artifact["ref"])
            if content_hash(raw) != artifact["content_hash"]:
                raise ValueError("Scenario content mismatch")
            if evidence.effects_v2 and raw["scenario"]["scenario_id"] == "baseline":
                e = evidence.effects_v2
                reads = {build.token_in.lower(): (raw["before"]["usdc_base_units"], raw["after"]["usdc_base_units"]),
                         build.token_out.lower(): (raw["before"]["wavax_base_units"], raw["after"]["wavax_base_units"])}
                if any((b.before, b.after) != reads[b.asset] for b in e.balances):
                    raise ValueError("Effects do not match authoritative balance reads")
                for a, before, after in zip(e.allowances, raw["allowances_before"], raw["allowances_after"], strict=True):
                    if (a.token, a.spender, a.before, a.after) != (before["token"], before["spender"], before["before"], after["after"]):
                        raise ValueError("Effects do not match allowance reads")
        return manifest

    def execute(self, build_id: str, signed_pdr: SignedPDR, idempotency_key: str):
        return ExecutionSubmission.model_validate(
            self._post(
                "/v1/executions",
                {"build_id": build_id, "signed_pdr": signed_pdr.model_dump()},
                idempotency_key,
            )
        ).model_dump()

    def result(self, tx_hash: str) -> ExecutionResult:
        r = self._request("GET", "/v1/executions/" + tx_hash)
        return ExecutionResult.model_validate(r.json())
