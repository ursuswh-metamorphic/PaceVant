import copy
import json

import pytest
from test_itag import api  # noqa: F401

from treasury_backend.modules.temporal.evidence_catalog import catalog, ground
from treasury_backend.modules.temporal.models import Graph
from treasury_backend.paths import ROOT


@pytest.fixture
def selection():
    row = json.loads((ROOT / "docs/evaluation/itag-final/ABLATION_RESULTS.json").read_text())[
        "rows"
    ][1]
    graph = Graph.model_validate(row["graph"])
    candidate = row["explanation"]["assessment"]["candidate_action_id"]
    tasks = {
        n.node_id
        for n in graph.nodes
        if n.data.get("source") == "USER" and n.kind == "AUTHENTICATED_USER_INTENT"
    }
    nodes = {n.node_id: n for n in graph.nodes}
    evidence = catalog(graph, candidate, tasks)
    scope = next(e for e in evidence["entries"] if e["scope_role"] == "ACTIVE_OPERATOR_INTENT")
    raw = dict(
        candidate_alias=evidence["candidate_alias"],
        semantic_verdict="MISALIGNED",
        goal_drift_detected=True,
        uncertainty=[],
        task_relationships=[
            dict(
                task_alias=evidence["task_aliases"][0],
                relationship="CONTRADICTORY",
                supporting_aliases=[evidence["candidate_alias"], scope["alias"]],
                objective_field="terms.objective",
                candidate_field="proposal.user_goal_reason",
                explanation="The stated purpose conflicts with the exclusive objective.",
            )
        ],
    )
    return graph, candidate, tasks, nodes, evidence, raw


def test_grounded_selection_keeps_original_trust_and_ids(selection):
    _, candidate, tasks, nodes, evidence, raw = selection
    before = copy.deepcopy(evidence)
    result, anchors = ground(raw, evidence, nodes, candidate, tasks)
    assert result["semantic_verdict"] == "MISALIGNED" and anchors
    assert result["candidate_action_id"] == candidate
    assert set(result["supporting_evidence_refs"]) <= {
        r for n in nodes.values() for r in n.evidence_refs
    }
    assert evidence == before
    assert all(nodes[n].data.get("source") == "USER" for n in result["referenced_task_ids"])


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_support",
        "unknown_task",
        "candidate",
        "task_substitution",
        "missing_scope",
        "objective_quote",
        "candidate_quote",
        "fake_receipt",
        "fake_amount",
        "missing_conflict",
        "changed_graph",
        "changed_revision",
        "changed_task",
        "untrusted_scope",
        "cancelled_scope",
        "superseded_scope",
    ],
)
def test_invalid_selection_cannot_ground(selection, mutation):
    graph, candidate, tasks, nodes, evidence, raw = selection
    relation = raw["task_relationships"][0]
    scope = next(n for n in nodes.values() if n.data.get("terms"))
    if mutation == "unknown_support":
        relation["supporting_aliases"].append("invented")
    elif mutation == "unknown_task":
        relation["task_alias"] = "invented"
    elif mutation == "candidate":
        raw["candidate_alias"] = "invented"
    elif mutation == "task_substitution":
        relation["task_alias"] = evidence["candidate_alias"]
    elif mutation == "missing_scope":
        relation["supporting_aliases"] = [evidence["candidate_alias"]] * 2
    elif mutation == "objective_quote":
        relation["objective_quote"] = "A fabricated permission"
    elif mutation == "candidate_quote":
        relation["candidate_quote"] = "Executed successfully"
    elif mutation == "fake_receipt":
        raw["receipt_status"] = "CONFIRMED"
    elif mutation == "fake_amount":
        raw["amount_in_base_units"] = "1"
    elif mutation == "missing_conflict":
        relation["relationship"] = "DIRECT"
    elif mutation == "changed_graph":
        nodes[candidate].data["proposal"]["user_goal_reason"] = "Different proposal"
        evidence = catalog(graph, candidate, tasks)
    elif mutation == "changed_revision":
        scope.data["revision"] += 1
        evidence = catalog(graph, candidate, tasks)
    elif mutation == "changed_task":
        tasks = {"different_task"}
    elif mutation == "untrusted_scope":
        nodes[scope.node_id] = scope.model_copy(update={"trust": "UNTRUSTED"})
    elif mutation == "cancelled_scope":
        scope.data["status"] = "CANCELLED"
    elif mutation == "superseded_scope":
        scope.data["effective_status"] = "SUPERSEDED"
    with pytest.raises(ValueError):
        ground(raw, evidence, nodes, candidate, tasks)


@pytest.mark.parametrize("verdict", ["ALIGNED", "MISALIGNED", "INVALID"])
def test_catalog_verdict_reaches_sde_and_signer(api, monkeypatch, verdict):  # noqa: F811
    from test_itag import NOW, audit, start

    from treasury_backend.core.errors import ControlError
    from treasury_backend.modules.alignment.provider import Completion
    from treasury_backend.modules.temporal.semantic_evaluator import PROMPT

    client, provider = api
    original = provider.complete

    def complete(messages):
        if messages[0]["content"] != PROMPT:
            return original(messages)
        evidence = json.loads(messages[1]["content"])["evidence_catalog"]
        scope = next(e for e in evidence["entries"] if e["scope_role"] == "ACTIVE_OPERATOR_INTENT")
        return Completion(
            json.dumps(
                dict(
                    candidate_alias="unknown"
                    if verdict == "INVALID"
                    else evidence["candidate_alias"],
                    semantic_verdict="MISALIGNED" if verdict == "MISALIGNED" else "ALIGNED",
                    goal_drift_detected=verdict == "MISALIGNED",
                    uncertainty=[],
                    task_relationships=[
                        dict(
                            task_alias=evidence["task_aliases"][0],
                            relationship="CONTRADICTORY" if verdict == "MISALIGNED" else "DIRECT",
                            supporting_aliases=[scope["alias"], evidence["candidate_alias"]],
                            objective_field="terms.objective",
                            candidate_field="proposal.user_goal_reason",
                            explanation="Canned judgment to verify SDE and signer propagation.",
                        )
                    ],
                )
            )
        )

    monkeypatch.setattr(provider, "complete", complete)
    spec = (
        client.post(
            "/v1/itag/intents",
            json=dict(
                kind="ONE_SHOT_SWAP",
                mandate_id="mandate_demo",
                deadline=NOW + 600,
                total_budget="100000000",
                objective="Acquire WAVAX for treasury reserves.",
                steps=[dict(step_id="swap", min_amount="100000000", max_amount="100000000")],
            ),
        )
        .raise_for_status()
        .json()
    )
    response = start(client, spec).raise_for_status().json()
    assert (
        response["status"]
        == {"ALIGNED": "CONFIRMED", "MISALIGNED": "REJECTED", "INVALID": "ESCALATED"}[verdict]
    )
    view, _ = audit(client, spec)
    if verdict != "ALIGNED":
        with pytest.raises(ControlError):
            client.app.state.control.attest(view["decision"]["decision_id"])
        with client.app.state.control.store.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM attestations").fetchone()[0] == 0
