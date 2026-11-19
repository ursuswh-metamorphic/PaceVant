import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_task_shield import NOW, WalletFixtureProvider

from app.alignment.provider import Completion, ShieldConfig
from app.api import create_app
from app.errors import ControlError
from app.models import Mandate
from app.settings import Settings
from app.storage import Store
from app.temporal.benchmark import load_cases, run_case
from app.temporal.semantic_evaluator import PROMPT

HEADERS = {"Authorization": "Bearer " + "o" * 24}


class TrajectoryFixture(WalletFixtureProvider):
    def __init__(self, finding="ALIGNED"):
        super().__init__()
        self.finding = finding
        self.graphs = []

    def complete(self, messages):
        if messages[0]["content"] != PROMPT:
            return super().complete(messages)
        if self.finding == "UNAVAILABLE":
            raise ControlError("TEST_PROVIDER_OUTAGE")
        data = json.loads(messages[1]["content"])
        self.graphs.append(data["graph"])
        action = data["candidate_action_id"]
        task = data["active_task_ids"][0]
        return Completion(
            json.dumps(
                {
                    "candidate_action_id": action,
                    "referenced_task_ids": [task],
                    "referenced_graph_node_ids": [
                        action,
                        task if self.finding != "FABRICATED" else "fabricated",
                    ],
                    "semantic_verdict": self.finding
                    if self.finding in {"ALIGNED", "MISALIGNED", "UNCERTAIN"}
                    else "ALIGNED",
                    "contribution_assessments": [
                        {
                            "task_id": task,
                            "relationship": "IRRELEVANT"
                            if self.finding == "NEGATIVE_ONLY"
                            else "INDIRECT",
                            "explanation": "Scripted assessment for regression.",
                        }
                    ],
                    "detected_goal_drift": self.finding == "MISALIGNED",
                    "claimed_instruction_source": "USER",
                    "reasoning_summary": "The cited graph nodes describe the requested trajectory.",
                    "supporting_evidence_refs": [action, task],
                    "uncertainty_reasons": [],
                }
            ),
            1,
            {"total_tokens": 7},
        )


@pytest.fixture
def api(tmp_path, monkeypatch):
    provider = TrajectoryFixture()
    monkeypatch.setattr("app.alignment.engine.ChatProvider", lambda *_: provider)
    settings = replace(
        Settings(),
        db=tmp_path / "itag.sqlite3",
        operator_token="o" * 24,
        internal_token="i" * 24,
        shield=ShieldConfig(mode="wallet_hardened", context_chars=100000, retries=0),
    )
    with TestClient(create_app(settings, lambda: NOW), headers=HEADERS) as client:
        yield client, provider


def create(api, kind="ONE_SHOT_SWAP", budget=100, steps=None, proposed=False):
    response = api.post(
        "/v1/itag/intents",
        params={"proposed": proposed},
        json={
            "kind": kind,
            "mandate_id": "mandate_demo",
            "deadline": NOW + 600,
            "total_budget": str(budget * 10**6),
            "steps": steps
            or [{"step_id": "swap", "min_amount": "100000000", "max_amount": "100000000"}],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def start(api, spec=None, step="swap", amount=100):
    body = {"goal": f"Buy WAVAX with {amount} USDC", "mandate_id": "mandate_demo"}
    if spec:
        body["temporal_intent"] = {
            "spec_id": spec["spec_id"],
            "revision": spec["revision"],
            "step_id": step,
        }
    return api.post("/v1/workflows/start", json=body)


def audit(api, spec):
    history = api.get(f"/v1/itag/intents/{spec['spec_id']}/history").raise_for_status().json()
    digest = history["assessments"][0]["assessment_hash"]
    return api.get("/v1/itag/assessments/" + digest).raise_for_status().json(), history


def test_completed_intent_blocks_repeat_that_actual_baseline_accepts(api):
    client, provider = api
    spec = create(client)
    assert start(client, spec).json()["status"] == "CONFIRMED"
    assert start(client).json()["status"] == "CONFIRMED"
    assert start(client, spec).json()["status"] == "REJECTED"
    view, history = audit(client, spec)
    assert len(history["ledger"]) == 1
    assert "ITAG_STEP_ALREADY_COMPLETE" in view["decision"]["reason_codes"]
    assert "positive judgment" in view["explanation"]["decision_summary"]
    candidate = view["explanation"]["assessment"]["candidate_action_id"]
    digest = history["assessments"][0]["assessment_hash"]
    detail = (
        client.get(f"/v1/itag/assessments/{digest}/nodes/{candidate}").raise_for_status().json()
    )
    assert detail["violations"][0]["code"] == "ITAG_STEP_ALREADY_COMPLETE"
    assert detail["trajectory_finding"]["candidate_action_id"] == candidate
    assert detail["shield_reports"]
    assert client.get("/itag").status_code == 200
    assert any(n["kind"] == "TRANSACTION_OUTCOME" for n in view["graph"]["nodes"])
    reports = [n for n in view["graph"]["nodes"] if n["kind"] == "SEMANTIC_ASSESSMENT"]
    assert reports and all(
        n["data"]["source_message_id"] and n["data"]["prompt_version"] for n in reports
    )
    for edge in view["graph"]["edges"]:
        if edge["kind"] == "CONTRIBUTES_TO":
            assert edge["provenance"] == "MODEL_INFERENCE"
        if edge["kind"] == "AUTHORIZES":
            assert edge["provenance"] == "AUTHORIZATION_RECORD"
            assert edge["target"] != candidate
    assert provider.graphs


@pytest.mark.parametrize(
    "case_id", ["scope-chain", "tool-authority-laundering", "late-plan-change"]
)
def test_benchmark_scope_and_source_regressions(tmp_path, case_id):
    root = Path(__file__).resolve().parents[3]
    case = next(c for c in load_cases(root / "fixtures/itag/scenarios.csv") if c["id"] == case_id)
    result = run_case(
        Store(tmp_path / "bench.sqlite3"),
        ShieldConfig(mode="paper", context_chars=100000),
        case,
        Mandate.model_validate_json((root / "fixtures/mock/mandate.json").read_bytes()),
        json.loads((root / "fixtures/mock/normal_swap.json").read_bytes()),
    )
    assert result["action_alignment"] == "ALIGNED"
    assert result["explanation_references_grounded"]
    assert result["candidate_localized"]
    assert result["sde"]["hybrid"] == "REJECT"
    assert result["deterministic"] == ("REJECT" if case_id == "scope-chain" else "PASS")
    if case_id == "scope-chain":
        assert result["semantic"] == "ALIGNED"
    else:
        assert result["sde"]["shield_temporal"] == "APPROVE"
    if case_id == "tool-authority-laundering":
        assert result["semantic_finding"]["claimed_instruction_source"] == "TOOL"
        assert not result["untrusted_authorizes"]


def test_ordered_dependency_then_legitimate_completion(api):
    client, _ = api
    spec = create(
        client,
        "ORDERED_TASK",
        200,
        [
            {"step_id": "swap", "min_amount": "100000000", "max_amount": "100000000"},
            {
                "step_id": "second",
                "min_amount": "100000000",
                "max_amount": "100000000",
                "prerequisites": ["swap"],
            },
        ],
    )
    assert start(client, spec, "second").json()["status"] == "REJECTED"
    assert start(client, spec).json()["status"] == "CONFIRMED"
    assert start(client, spec, "second").json()["status"] == "CONFIRMED"
    view, _ = audit(client, spec)
    assert any(
        e["kind"] == "DEPENDS_ON" and e["target"].startswith("outcome:")
        for e in view["graph"]["edges"]
    )


@pytest.mark.parametrize(
    ("finding", "result", "code"),
    [
        ("FABRICATED", "ESCALATED", "ITAG_INVALID_SEMANTIC_REFERENCES_OR_OUTPUT"),
        ("UNAVAILABLE", "ESCALATED", "ITAG_PROVIDER_UNAVAILABLE"),
        ("UNCERTAIN", "ESCALATED", "ITAG_SEMANTIC_UNCERTAIN"),
        ("NEGATIVE_ONLY", "REJECTED", "ITAG_NO_AFFIRMATIVE_CONTRIBUTION"),
        ("MISALIGNED", "REJECTED", "ITAG_SEMANTIC_DIVERGENCE"),
    ],
)
def test_semantic_veto_and_reference_validation(api, finding, result, code):
    client, provider = api
    provider.finding = finding
    spec = create(client)
    assert start(client, spec).json()["status"] == result
    view, history = audit(client, spec)
    assert history["ledger"] == []
    assert code in view["decision"]["reason_codes"]
    assert view["explanation"]["assessment"]["violating_node_ids"]


def test_replan_to_authorized_bound(api):
    client, _ = api
    spec = create(
        client,
        "BOUNDED_SWAP",
        100,
        [{"step_id": "swap", "min_amount": "50000000", "max_amount": "100000000"}],
    )
    assert start(client, spec, amount=150).json()["status"] == "CONFIRMED"
    view, history = audit(client, spec)
    assert [row["verdict"] for row in history["assessments"]] == ["PASS", "REPLAN"]
    assert history["ledger"][0]["build"]["amount_in_base_units"] == "100000000"
    assert view["latest_outcome"]["verification"]["canonical"]


def test_signing_race_and_stale_graph(api, monkeypatch):
    client, _ = api
    spec = create(client)
    control = client.app.state.control
    original = control.attest
    monkeypatch.setattr(
        control, "attest", lambda _: (_ for _ in ()).throw(ControlError("PAUSED_TEST"))
    )
    for _ in range(2):
        assert start(client, spec).json()["status"] == "ESCALATED"
    with control.store.connection() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM decisions ORDER BY rowid")]

    # Both precomputed graphs saw the empty ledger. The second write transaction
    # must invalidate its graph after the first one reserves the shared budget.
    def reserve(id_):
        try:
            control.store.reserve_signature(
                id_=id_,
                workflow_id=control.store.decision(decision_id=id_)[0],
                scope=id_,
                nonce="1",
                now=NOW,
                expires_at=NOW + 30,
                sign=lambda: (
                    type(
                        "StubPdr",
                        (),
                        {"model_dump_json": lambda _: "{}", "typed_data_hash": "test"},
                    )(),
                    NOW,
                ),
            )
            return "RESERVED"
        except ControlError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, ids))
    assert sorted(results) == ["ITAG_STALE_OR_MISMATCHED_EVIDENCE", "RESERVED"]
    monkeypatch.setattr(control, "attest", original)


def test_cancel_revision_invalidates_before_signing(api, monkeypatch):
    client, _ = api
    spec = create(client)
    control = client.app.state.control
    original = control.attest

    def cancel_before_sign(id_):
        control.temporal.cancel(spec["spec_id"], 1)
        return original(id_)

    monkeypatch.setattr(control, "attest", cancel_before_sign)
    result = start(client, spec).json()
    assert result["status"] == "ESCALATED"
    assert start(client, spec).status_code == 409
    view, history = audit(client, spec)
    assert view["decision"]["verdict"] == "APPROVE"
    assert history["ledger"] == []


def test_reorg_or_invalidated_snapshot_blocks_completion_credit(api):
    client, _ = api
    spec = create(client, "BOUNDED_SWAP", 300)
    assert start(client, spec).json()["status"] == "CONFIRMED"
    _, history = audit(client, spec)
    snapshot = history["ledger"][0]["outcome"]["post_snapshot_id"]
    client.app.state.control.store.invalidate_snapshot(snapshot, NOW)
    assert start(client, spec).json()["status"] == "ESCALATED"
    view, _ = audit(client, spec)
    assert "ITAG_UNVERIFIED_OUTCOME" in view["decision"]["reason_codes"]


def test_intent_auth_and_proposed_then_revised(api):
    client, _ = api
    spec = create(client, proposed=True)
    path = f"/v1/itag/intents/{spec['spec_id']}"
    assert client.get(path, headers={"Authorization": ""}).status_code == 401
    assert start(client, spec).status_code == 409
    revised = (
        client.put(path, json={"expected_revision": 1, "terms": spec["terms"]})
        .raise_for_status()
        .json()
    )
    assert revised["status"] == "AUTHENTICATED" and revised["revision"] == 2
    assert client.get(path).json()["superseded"][0]["effective_status"] == "SUPERSEDED"
    assert start(client, revised).json()["status"] == "CONFIRMED"
