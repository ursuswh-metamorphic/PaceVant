import json
import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.errors import ControlError
from app.orchestration.mock import MockExecutionClient
from app.settings import FIXTURES, Settings
from treasury_contracts.models import SimulationEvidence

NOW = 2_000_000_000
TOKEN = "mock-internal-credential-for-tests-only"


@pytest.fixture
def api(tmp_path):
    settings = replace(Settings(), db=tmp_path / "test.sqlite3", internal_token=TOKEN)
    with TestClient(create_app(settings, lambda: NOW)) as client:
        yield client


def run(api, scenario="normal_swap", goal="Buy WAVAX with 500 USDC"):
    result = api.post(
        "/v1/workflows/start",
        json={
            "scenario": scenario,
            "goal": goal,
            "mandate_id": "mandate_demo",
        },
    )
    assert result.status_code == 200, result.text
    workflow = api.get("/v1/workflows/" + result.json()["workflow_id"]).json()
    return workflow, workflow["timeline"]


def test_lfj_cannot_reuse_a_mock_usdc_price_to_obtain_sde_approval(api, monkeypatch):
    original = MockExecutionClient.build

    def lfj_version(self, proposal):
        return original(self, proposal).model_copy(update={"adapter_version": "lfj-v1-fuji-v1"})

    monkeypatch.setattr(MockExecutionClient, "build", lfj_version)
    _, events = run(api, "normal_swap")
    decision = events[-1]["decision"]
    assert decision["verdict"] == "ESCALATE"
    assert "ORACLE_TOKEN_IDENTITY_MISMATCH" in decision["reason_codes"]
    assert "ATTESTED" not in [event["stage"] for event in events]


def test_fuji_cannot_authorize_using_a_trusted_test_oracle_file(tmp_path):
    from types import SimpleNamespace

    from app.orchestration.service import ControlPlane

    # A missing file would raise UNVERIFIED_PRICE if the old file-based path ran.
    holder = SimpleNamespace(
        settings=SimpleNamespace(mode="FUJI", oracle_file=tmp_path / "oracle.json")
    )
    with pytest.raises(ControlError, match="ORACLE_TOKEN_IDENTITY_MISMATCH"):
        ControlPlane.price(holder, object())


def test_fuji_settings_do_not_require_a_placeholder_test_oracle_file(monkeypatch):
    import secrets

    config = {
        "MODE": "FUJI",
        "MANDATE_FILE": "mandate-lfj.json",
        "B_URL": "http://127.0.0.1:8001",
        "B_TOKEN": "b" * 24,
        "OPERATOR_TOKEN": "o" * 24,
        "INTERNAL_TOKEN": "i" * 24,
        "ATTESTOR_KEY": secrets.token_hex(32),
        "CHAIN_RPC_URL": "https://api.avax-test.network/ext/bc/C/rpc",
        "RELAYER_ADDRESS": "0x" + "12" * 20,
    }
    for name, value in config.items():
        monkeypatch.setenv("PACEVANT_" + name, value)
    monkeypatch.delenv("PACEVANT_ORACLE_FILE", raising=False)
    settings = Settings.from_env()
    assert settings.mode == "FUJI" and settings.oracle_file is None


@pytest.mark.parametrize("scenario", ["normal_swap", "exposure_limit", "stale_price", "injection"])
def test_scenario_acceptance(api, scenario):
    fixture = json.loads((FIXTURES / f"{scenario}.json").read_text("utf-8"))
    workflow, events = run(api, scenario, fixture["goal"])
    decisions = [event["decision"] for event in events if "decision" in event]
    assert [d["verdict"] for d in decisions] == fixture["expected_verdicts"]
    assert workflow["mode"] == "MOCK"
    signed = [event for event in events if event["stage"] == "ATTESTED"]
    assert all("signature" not in event for event in events)
    if "APPROVE" in fixture["expected_verdicts"]:
        assert [event["decision_id"] for event in signed] == [decisions[-1]["decision_id"]]
        assert events[-1]["stage"] == "CONFIRMED"
        receipt = events[-1]["receipt"]
        assert receipt["event_refs"] == ["SwapExecuted"]
    else:
        assert not signed
        assert all("receipt" not in event for event in events)


def test_a02_a07_exposure_rebuild_binds_every_attempt(api):
    _, events = run(api, "exposure_limit")
    first_risk, second_risk = [event["risk"] for event in events if "risk" in event]
    first, second = [event["decision"] for event in events if "decision" in event]
    assert first_risk["projected_wavax_exposure_bps"] == 2800
    assert first["reason_codes"] == ["TOKEN_EXPOSURE_LIMIT"]
    assert "ATTESTED" not in [event["stage"] for event in events[:8]]
    assert second_risk["projected_wavax_exposure_bps"] == 2500
    assert [
        event["proposal"]["amount_in_base_units"] for event in events if "proposal" in event
    ] == [
        "500000000",
        "200000000",
    ]
    for key in (
        "decision_id",
        "intent_id",
        "build_id",
        "snapshot_id",
        "calldata_hash",
        "simulation_evidence_root",
    ):
        assert first[key] != second[key]
    assert [event["decision_id"] for event in events if event["stage"] == "ATTESTED"] == [
        second["decision_id"],
    ]


def test_a03_injection_stops_before_builder(api, monkeypatch):
    def fail(*args):
        pytest.fail("injection reached builder")

    monkeypatch.setattr(MockExecutionClient, "build", fail)
    _, events = run(api, "injection")
    assert events[-1]["decision"]["reason_codes"] == ["TASK_MISALIGNED", "BAD_RECIPIENT"]


def test_a04_goal_uncertainty_escalates(api):
    _, events = run(api, goal="Move assets when it looks profitable")
    assert events[-1]["stage"] == "ESCALATED"
    assert events[-1]["decision"]["reason_codes"] == ["TASK_UNCERTAIN"]


def test_a05_stale_price_has_reason_and_no_signing(api):
    _, events = run(api, "stale_price")
    assert "STALE_PRICE" in events[-1]["decision"]["reason_codes"]


@pytest.mark.parametrize("change", ["artifact", "summary", "calldata", "snapshot", "block_hash"])
def test_a05_tamper_or_wrong_binding_never_approves(api, monkeypatch, change):
    if change == "artifact":
        original = MockExecutionClient.artifact

        def artifact(self, ref):
            return original(self, ref) + (b" " if ref.endswith("/report.json") else b"")

        monkeypatch.setattr(MockExecutionClient, "artifact", artifact)
    elif change == "summary":
        original = MockExecutionClient.simulate

        def simulate(self, built):
            original_evidence = original(self, built)
            data = original_evidence.model_dump()
            data["baseline"]["token_out_delta_base_units"] = "25000000000000000001"
            return SimulationEvidence.model_validate(data)

        monkeypatch.setattr(MockExecutionClient, "simulate", simulate)
    elif change == "calldata":
        original = MockExecutionClient.build

        def build(self, prop):
            tx = original(self, prop)
            changed = tx.router_calldata[:-2] + ("00" if tx.router_calldata[-2:] != "00" else "01")
            return tx.model_copy(update={"router_calldata": changed})

        monkeypatch.setattr(MockExecutionClient, "build", build)
    elif change == "snapshot":
        original = MockExecutionClient.balances

        def balances(self):
            return original(self).model_copy(update={"vault_address": "0x" + "88" * 20})

        monkeypatch.setattr(MockExecutionClient, "balances", balances)
    else:
        original = MockExecutionClient.context

        def context(self, **kwargs):
            ctx = original(self, **kwargs)
            if kwargs.get("fork_block") is not None:
                return ctx.model_copy(update={"fork_block_hash": "0x" + "00" * 32})
            return ctx

        monkeypatch.setattr(MockExecutionClient, "context", context)
    _, events = run(api)
    assert events[-1]["decision"]["verdict"] == "ESCALATE"
    assert "HASH_MISMATCH" in events[-1]["decision"]["reason_codes"]
    assert "ATTESTED" not in [e["stage"] for e in events]


def test_a06_replay_forgery_and_token_separation(api):
    headers = {"Authorization": f"Bearer {TOKEN}", "X-Request-Id": "audit_a06"}
    route = "/v1/approvals/attest"
    denied = api.post(route, json={"decision_id": "not_issued"})
    assert denied.status_code == 401
    forged = api.post(
        route,
        headers=headers,
        json={
            "decision_id": "not_issued",
            "verdict": "APPROVE",
            "approval": {},
        },
    )
    assert forged.status_code == 400
    assert forged.json()["error"]["correlation_id"] == "audit_a06"
    missing = api.post(route, headers=headers, json={"decision_id": "not_issued"})
    assert missing.status_code == 404
    _, events = run(api)
    decision_id = next(e["decision"]["decision_id"] for e in events if "decision" in e)
    replay = api.post(route, headers=headers, json={"decision_id": decision_id})
    fixture = json.loads((FIXTURES / "replay_request.json").read_text("utf-8"))
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == fixture["expected_error"]


def test_a08_policy_rotation_after_sde_blocks_signing(api, monkeypatch):
    control = api.app.state.control
    original = control.attest

    def attest(id_):
        workflow_id, _ = control.store.decision(decision_id=id_)
        control.mock_clients[workflow_id].policy_changed = True
        return original(id_)

    monkeypatch.setattr(control, "attest", attest)
    _, events = run(api)
    assert any(event["stage"] == "APPROVED" for event in events)
    assert events[-1]["stage"] == "ESCALATED"
    assert events[-1]["reason_codes"] == ["STALE_REQUIRES_REEVALUATION"]
    assert "ATTESTED" not in [e["stage"] for e in events]


def test_a08_policy_rotation_after_signing_stops_submit(api, monkeypatch):
    control = api.app.state.control
    original = control._submit

    def submit(workflow_id, decision, signed):
        control.mock_clients[workflow_id].policy_changed = True
        original(workflow_id, decision, signed)

    monkeypatch.setattr(control, "_submit", submit)
    _, events = run(api)
    assert any(event["stage"] == "ATTESTED" for event in events)
    assert events[-1]["stage"] == "EXPIRED"
    assert "SUBMITTING" not in [e["stage"] for e in events]


def test_a09_protected_revert_is_allowed_when_policy_permits(api):
    _, events = run(api)
    sim = next(e["simulation"] for e in events if "simulation" in e)
    assert sim["stress_tests"][-1]["status"] == "PROTECTED_REVERT"
    assert events[-1]["stage"] == "CONFIRMED"


def test_replans_exhaust_new_build_and_sim_each_time(api, monkeypatch):
    control = api.app.state.control
    original = control.mandate

    def mandate(id_=None):
        original_mandate = original(id_)
        return original_mandate.model_copy(
            update={
                "required_stress": {
                    "reserve_shift_adverse": "SUCCESS_REQUIRED",
                }
            }
        )

    monkeypatch.setattr(control, "mandate", mandate)
    _, events = run(api)
    decisions = [e["decision"] for e in events if "decision" in e]
    assert [d["verdict"] for d in decisions] == ["REPLAN"] * 3
    assert len({d["calldata_hash"] for d in decisions}) == 3
    assert len({d["simulation_evidence_root"] for d in decisions}) == 3
    assert all(d["reason_codes"] == ["REQUIRED_STRESS_NOT_SATISFIED"] for d in decisions)
    assert not any(e["stage"] == "ATTESTED" for e in events)


def test_immutable_decisions_and_reference_only_apis(api):
    _, events = run(api)
    decision = next(e["decision"] for e in events if "decision" in e)
    sim = next(e["simulation"] for e in events if "simulation" in e)
    align = next(e["alignment"] for e in events if "alignment" in e)
    postgres_free_store = api.app.state.control.store
    with (
        pytest.raises(sqlite3.IntegrityError, match="immutable decision"),
        postgres_free_store.connection(write=True) as conn,
    ):
        conn.execute("UPDATE decisions SET body='{}' WHERE id=?", (decision["decision_id"],))
    refs = {
        k: decision[k]
        for k in (
            "intent_id",
            "build_id",
            "snapshot_id",
            "simulation_evidence_root",
        )
    }
    assert api.post("/v1/decisions", json={**refs, "alignment": align}).json() == decision
    assert (
        api.post(
            "/v1/decisions",
            json={
                **refs,
                "alignment": {**align, "verdict": "UNCERTAIN"},
            },
        ).status_code
        == 409
    )
    risk = api.post("/v1/risk/evaluate", json={"snapshot_id": refs["snapshot_id"], "evidence": sim})
    assert risk.json()["result"] == "PASS"


def test_stage_never_claims_confirmed_without_receipt(api, monkeypatch):
    def execution(self, tx_hash):
        raise ControlError("EXECUTION_PLANE_UNAVAILABLE", 503)

    monkeypatch.setattr(MockExecutionClient, "execution", execution)
    workflow, events = run(api)
    assert workflow["status"] == "SUBMITTED"
    assert all(e["stage"] != "CONFIRMED" for e in events)


def test_ambiguous_execution_does_not_retry_submission(api, monkeypatch):
    calls = []

    def execute(self, built, pdr):
        calls.append(pdr.decision_id)
        raise ControlError("EXECUTION_PLANE_UNAVAILABLE", 503)

    monkeypatch.setattr(MockExecutionClient, "execute", execute)
    workflow, events = run(api)
    assert workflow["status"] == "SUBMITTING"
    assert "SUBMISSION_OUTCOME_UNKNOWN" in events[-1]["reason_codes"]
    assert len(calls) == 1


def test_chain_daily_spend_drives_replan(api, monkeypatch):
    original = MockExecutionClient.__init__

    def setup(self, *args):
        original(self, *args)
        self.spent = 800_000_000

    monkeypatch.setattr(MockExecutionClient, "__init__", setup)
    _, events = run(api)
    verdicts = [e["decision"] for e in events if "decision" in e]
    assert verdicts[0]["reason_codes"] == ["TRADE_SIZE_LIMIT"]
    assert verdicts[1]["verdict"] == "APPROVE"
    assert events[-1]["receipt"]["actual_token_in_delta_base_units"] == "-200000000"


def test_confirmed_receipt_with_wrong_delta_is_flagged(api, monkeypatch):
    original = MockExecutionClient.execution

    def execution(self, tx_hash):
        return original(self, tx_hash).model_copy(update={"actual_token_in_delta_base_units": "-1"})

    monkeypatch.setattr(MockExecutionClient, "execution", execution)
    workflow, events = run(api)
    assert workflow["status"] == "RECEIPT_MISMATCH"
    assert all(event["stage"] != "CONFIRMED" for event in events)


def test_slower_build_expires_before_signature(api, monkeypatch):
    control = api.app.state.control
    time = [NOW]
    control.clock = lambda: time[0]
    original = MockExecutionClient.simulate

    def simulate(self, built):
        result = original(self, built)
        time[0] = built.deadline
        return result

    monkeypatch.setattr(MockExecutionClient, "simulate", simulate)
    workflow, events = run(api)
    assert workflow["status"] == "ESCALATED"
    assert "STALE_REQUIRES_REEVALUATION" in events[-1]["decision"]["reason_codes"]
    assert all(event["stage"] != "ATTESTED" for event in events)
