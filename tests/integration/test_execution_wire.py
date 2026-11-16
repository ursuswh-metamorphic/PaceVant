import json
from dataclasses import replace

import httpx
import pytest
import rfc8785

from app.attestor.typed import hash_bytes
from app.models import EvidenceReport, WorkflowRequest
from app.orchestration.mock import MockExecutionClient
from app.orchestration.service import ControlPlane
from app.settings import Settings
from treasury_contract.wire import SignedPDR, SimulationEvidence, TransactionProposal

NOW = 2_000_000_000
REQUEST = WorkflowRequest(goal="Buy WAVAX with 500 USDC", mandate_id="mandate_demo")
TEST_KEY = "00" * 31 + "02"


class WirePeer:
    """In-memory peer for A's HTTP client. This peer performs zero EVM simulation."""

    def __init__(self, service, *, deployment, source, pending=False, lose_ack=False):
        self.source = source
        self.deployment = deployment
        self.pending = pending
        self.lose_ack = lose_ack
        self.producer = MockExecutionClient(
            service.mandate(),
            service.attestor.address,
            service.fixture(None),
            lambda: NOW,
        )
        self.calls = []
        self.last_tx_hash = None

    def __call__(self, request):
        path = request.url.path
        method = request.method
        assert request.headers["X-Request-Id"].startswith("workflow_")
        assert request.headers["Authorization"] == "Bearer dummy-b"
        body = json.loads(request.content) if request.content else {}
        self.calls.append((method, path))
        if method == "POST":
            assert request.headers.get("Idempotency-Key")
        if path == "/v1/chain/context":
            fork = request.url.params.get("fork_block")
            value = self.producer.context(
                nonce=request.url.params.get("nonce"),
                fork_block=int(fork) if fork else None,
            ).model_copy(update={"deployment": self.deployment})
        elif path == "/v1/portfolio/onchain-snapshot":
            value = self.producer.balances()
        elif path == "/v1/build":
            value = self.producer.build(TransactionProposal.model_validate(body))
        elif path == "/v1/simulations":
            built = self.producer.builds[body["build_id"]]
            assert body["expected_policy_hash"] == built.policy_hash
            value = self.producer.simulate(built)
            data = value.model_dump()
            data["source"] = self.source
            data["simulation_mode"] = "LOCAL_TEST_ATTESTOR"
            ref = value.artifact_refs[0]
            report = EvidenceReport.model_validate_json(self.producer.artifacts[ref]).model_copy(
                update={"source": self.source, "simulation_mode": data["simulation_mode"]}
            )
            self.producer.artifacts[ref] = rfc8785.dumps(report.model_dump())
            manifest = json.loads(self.producer.artifacts[value.evidence_manifest_ref])
            manifest["artifact_hashes"][ref] = hash_bytes(self.producer.artifacts[ref])
            canonical_manifest = rfc8785.dumps(manifest)
            self.producer.artifacts[value.evidence_manifest_ref] = canonical_manifest
            value = SimulationEvidence.model_validate(
                {
                    **data,
                    "evidence_root": hash_bytes(canonical_manifest),
                }
            )
            self.producer.simulations[built.build_id] = value
        elif path.startswith("/v1/artifacts/"):
            ref = "artifact://" + path.removeprefix("/v1/artifacts/")
            return httpx.Response(200, content=self.producer.artifact(ref))
        elif path == "/v1/executions":
            signed = SignedPDR.model_validate(body["signed_pdr"])
            value = self.producer.execute(self.producer.builds[body["build_id"]], signed)
            self.last_tx_hash = value.tx_hash
            if self.lose_ack:
                raise httpx.ReadTimeout("submission acknowledged by B but response was lost")
        elif path == f"/v1/executions/{self.last_tx_hash}":
            value = self.producer.execution(self.last_tx_hash)
            if self.pending:
                value = value.model_copy(update={"status": "PENDING"})
        else:
            raise AssertionError(f"unknown path {path}")
        return httpx.Response(200, json=value.model_dump())


def connect(tmp_path, mode, *, deployment=None, source, pending=False, lose_ack=False):
    settings = replace(
        Settings(),
        mode=mode,
        db=tmp_path / "control.sqlite3",
        attestor_key=TEST_KEY,
        execution_url="http://localhost:8001",
        execution_token="dummy-b",
        oracle_file=tmp_path / "oracle.json",
    )
    control = ControlPlane(settings, lambda: NOW)
    peer = WirePeer(
        control, deployment=deployment or mode, source=source, pending=pending, lose_ack=lose_ack
    )
    settings.oracle_file.write_text(peer.producer.price().model_dump_json(), encoding="utf-8")
    control.http.close()
    control.http = httpx.Client(
        base_url=settings.execution_url,
        headers={"Authorization": "Bearer dummy-b"},
        transport=httpx.MockTransport(peer),
    )
    return control, peer


@pytest.mark.parametrize("source", ["MOCK_FIXTURE", "REAL_LOCAL_SIM"])
def test_a10_fuji_denies_mock_and_local_evidence(tmp_path, source):
    control, peer = connect(tmp_path, "FUJI", source=source)
    try:
        response = control.run(REQUEST)
        assert response["status"] == "ESCALATED"
        events = control.workflow(response["workflow_id"])["timeline"]
        assert "UNVERIFIED_SIMULATION_SOURCE" in events[-1]["decision"]["reason_codes"]
        assert all(event["stage"] != "ATTESTED" for event in events)
        assert ("POST", "/v1/executions") not in peer.calls
    finally:
        control.close()


def test_local_http_pipeline_and_pending_execution_reservation(tmp_path):
    control, peer = connect(tmp_path, "LOCAL", source="REAL_LOCAL_SIM", pending=True)
    try:
        first = control.run(REQUEST)
        assert first["status"] == "SUBMITTED"
        on_hold = control.run(REQUEST)
        assert on_hold["status"] == "ESCALATED"
        assert control.workflow(on_hold["workflow_id"])["timeline"][-1]["reason_codes"] == [
            "VAULT_APPROVAL_IN_FLIGHT",
        ]
        assert peer.calls.count(("POST", "/v1/executions")) == 1
        peer.pending = False
        final = control.workflow(first["workflow_id"])
        assert final["status"] == "CONFIRMED"
        assert control.run(REQUEST)["status"] == "CONFIRMED"
        assert peer.calls.count(("POST", "/v1/executions")) == 2
    finally:
        control.close()


def test_submission_timeout_holds_vault_reservation(tmp_path):
    control, peer = connect(tmp_path, "LOCAL", source="REAL_LOCAL_SIM", lose_ack=True)
    try:
        response = control.run(REQUEST)
        assert response["status"] == "SUBMITTING"
        on_hold = control.run(REQUEST)
        assert on_hold["status"] == "ESCALATED"
        assert control.workflow(on_hold["workflow_id"])["timeline"][-1]["reason_codes"] == [
            "VAULT_APPROVAL_IN_FLIGHT",
        ]
        assert peer.calls.count(("POST", "/v1/executions")) == 1
        recovered = control.recover_submission(response["workflow_id"], peer.last_tx_hash)
        assert recovered["status"] == "CONFIRMED"
        assert peer.calls.count(("POST", "/v1/executions")) == 1
    finally:
        control.close()
