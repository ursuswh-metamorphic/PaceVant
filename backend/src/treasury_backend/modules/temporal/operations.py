"""Typed operation extension of ITAG: exact authority plus the existing trajectory evaluator."""

from treasury_backend.modules.temporal.models import Graph, GraphEdge, GraphNode
from treasury_contracts.crypto import content_hash
from treasury_contracts.v3 import KINDS


def evaluate_operation(temporal, intent, built, context, history, runtime, plan, *, on_check=None):
    violations = []
    auth = context["authority"]
    if (
        built["intent"] != intent.model_dump(mode="json")
        or built["operation"]["intentHash"] != intent.hash
        or built["operation"]["policyHash"] != context["policy_hash"]
    ):
        violations.append("ITAG_BUILD_MISMATCH")
    if not auth["operation_mask"] & (1 << (KINDS[intent.operation] - 1)):
        violations.append("ITAG_ACTION_SCOPE_MISMATCH")
    if intent.rebalance and (
        not auth["operation_mask"] & 16
        or auth["last_rebalance"]
        and temporal.clock() < auth["last_rebalance"] + auth["cooldown"]
    ):
        violations.append("ITAG_REBALANCE_COOLDOWN_OR_SCOPE")
    if auth["actions"] >= auth["max_actions"] or intent.deadline > context["session_expires_at"]:
        violations.append("ITAG_SESSION_EXHAUSTED")
    if any(
        h["status"] not in {"CONFIRMED", "REVERTED", "REJECTED", "EXPIRED_UNSIGNED"}
        for h in history
    ):
        violations.append("ITAG_UNRESOLVED_HISTORY")
    candidate, task = "candidate_" + intent.hash[2:18], "task_" + intent.hash[2:18]
    nodes = [
        GraphNode(
            node_id=task,
            kind="AUTHENTICATED_USER_INTENT",
            trust="AUTHENTICATED",
            evidence_refs=[task],
            data={
                "source": "USER",
                "authorization_source": "OPERATOR_API",
                "status": "AUTHENTICATED",
                "terms": intent.model_dump(mode="json"),
                "objective": intent.objective,
                "typed_intent": intent.model_dump(mode="json"),
                "owner_session": context["session_id"],
            },
        ),
        GraphNode(
            node_id=candidate,
            kind="AGENT_ACTION",
            trust="UNTRUSTED",
            evidence_refs=[candidate],
            # Catalog grounding reads the actual model rationale from this path.
            # It must not be synthesized from the objective or builder output.
            data={
                **built,
                "proposal": {
                    **plan.model_dump(mode="json"),
                    "amount_in_base_units": plan.amount,
                    "user_goal_reason": plan.explanation,
                },
            },
        ),
        GraphNode(
            node_id="owner_scope",
            kind="MANDATE",
            trust="VERIFIED_RECORD",
            evidence_refs=[context["policy_hash"]],
            data={
                "policy_hash": context["policy_hash"],
                "authority": auth,
                "chain_id": context["chain_id"],
                "policy_version": context["policy_version"],
            },
        ),
    ]
    for index, entry in enumerate(history[-12:]):
        nodes.append(
            GraphNode(
                node_id=f"prior_{index}",
                kind="TRANSACTION_OUTCOME",
                trust="VERIFIED_RECORD",
                evidence_refs=[entry["workflow_id"]],
                data=entry,
            )
        )
    graph = Graph(
        nodes=nodes,
        edges=[
            GraphEdge(
                edge_id="authorized",
                source=task,
                target=candidate,
                kind="AUTHORIZES",
                provenance="AUTHORIZATION_RECORD",
                evidence_refs=[task],
            )
        ],
    )
    if on_check:
        on_check("ITAG_AUTHORITY_HISTORY", "FAIL" if violations else "PASS",
                 expected={"reason_codes": []}, observed={"reason_codes": violations, "history_count": len(history), "actions": auth["actions"], "max_actions": auth["max_actions"]})
        on_check("ITAG_GRAPH", "PASS", observed={
            "nodes": [{"node_id": n.node_id, "kind": n.kind, "trust": n.trust, "evidence_refs": n.evidence_refs} for n in graph.nodes],
            "edges": [e.model_dump(mode="json") for e in graph.edges],
        })
        on_check("ITAG_SEMANTIC", "RUNNING", expected="ALIGNED")
    semantic = temporal.semantic.before_decision(
        graph, candidate, "ALIGNED", shield_blocked=runtime.last_feedback is not None
    )
    if on_check:
        on_check("ITAG_SEMANTIC", "PASS" if semantic.verdict == "ALIGNED" else "UNKNOWN" if semantic.verdict == "UNCERTAIN" else "FAIL",
                 expected="ALIGNED", observed=semantic.model_dump(mode="json"))
    if semantic.verdict != "ALIGNED":
        violations.extend(semantic.reason_codes or ["ITAG_SEMANTIC_NOT_ALIGNED"])
    proof = runtime.proof(intent)
    temporal.shield.validate(proof["session_id"], proof["check_ids"], proof["revision"])
    return {
        "verdict": "PASS" if not violations else "REJECT",
        "reason_codes": violations,
        "semantic": semantic.model_dump(mode="json"),
        "graph": graph.model_dump(mode="json"),
        "graph_hash": content_hash(graph.model_dump(mode="json")),
        "intent_hash": intent.hash,
        "history_hash": content_hash(history),
        "shield": proof,
    }
