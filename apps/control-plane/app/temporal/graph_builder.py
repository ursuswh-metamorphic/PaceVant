from decimal import Decimal

from app.alignment.provider import safe_value
from app.portfolio.observations import content_hash
from app.temporal.models import Graph, GraphEdge, GraphNode
from app.temporal.verifier import confirmed_state


class GraphBuilder:
    def __init__(self):
        self.nodes = {}
        self.edges = {}

    def node(self, node_id, kind, trust, refs, data):
        self.nodes[node_id] = GraphNode(
            node_id=node_id, kind=kind, trust=trust, evidence_refs=refs, data=data
        )
        return node_id

    def link(self, source, target, kind, refs, provenance="SYSTEM_RECORD"):
        if source not in self.nodes or target not in self.nodes:
            raise ValueError("ITAG edge endpoint missing")
        fields = dict(
            source=source, target=target, kind=kind, provenance=provenance, evidence_refs=refs
        )
        edge_id = content_hash(fields)
        self.edges[edge_id] = GraphEdge(edge_id=edge_id, **fields)

    def finish(self):
        return Graph(
            nodes=sorted(self.nodes.values(), key=lambda node: node.node_id),
            edges=sorted(self.edges.values(), key=lambda edge: edge.edge_id),
        )


def build_graph(
    spec,
    mandate,
    proposal,
    built,
    sim,
    observation,
    entries,
    tasks,
    reports,
    revisions,
    *,
    authorized,
    current_report_ids,
    step_id=None,
    user_messages=(),
    output_context=None,
):
    graph = GraphBuilder()
    mandate_id = graph.node(
        "mandate:" + spec.mandate_hash,
        "MANDATE",
        "AUTHENTICATED",
        [spec.mandate_hash],
        {"mandate_id": mandate.mandate_id, "policy_hash": mandate.policy_hash},
    )
    spec_ref = f"{spec.spec_id}:{spec.revision}"
    intent = graph.node(
        spec_ref,
        "AUTHENTICATED_USER_INTENT",
        "AUTHENTICATED" if spec.status == "AUTHENTICATED" else "UNVERIFIED",
        [spec_ref],
        spec.model_dump(),
    )
    for prior in revisions:
        ref = f"{prior.spec_id}:{prior.revision}"
        graph.node(
            ref,
            "AUTHENTICATED_USER_INTENT",
            "AUTHENTICATED" if prior.status == "AUTHENTICATED" else "UNVERIFIED",
            [ref],
            {**prior.model_dump(), "effective_status": "SUPERSEDED"},
        )
    for before, after in zip(revisions, [*revisions[1:], spec], strict=False):
        graph.link(
            f"{after.spec_id}:{after.revision}",
            f"{before.spec_id}:{before.revision}",
            "SUPERSEDES",
            [f"{after.spec_id}:{after.revision}"],
        )
    if spec.status == "AUTHENTICATED" and spec.mandate_hash == content_hash(mandate.model_dump()):
        graph.link(
            mandate_id, intent, "AUTHORIZES", [spec_ref, spec.mandate_hash], "AUTHORIZATION_RECORD"
        )
    candidate = graph.node(
        proposal.intent_id,
        "AGENT_ACTION",
        "UNVERIFIED",
        [proposal.intent_id],
        {
            "proposal": safe_value(proposal),
            "build_id": built.build_id if built else None,
            "step_id": step_id,
        },
    )
    if authorized is not None:
        graph.link(
            intent, candidate, "AUTHORIZES", [spec_ref, proposal.intent_id], "AUTHORIZATION_RECORD"
        )
    if built and sim:
        simulation = graph.node(
            "simulation:" + sim.evidence_root,
            "TOOL_OBSERVATION",
            "UNVERIFIED",
            [sim.evidence_root],
            {"build_id": sim.build_id, "binding": "SIMULATION"},
        )
        graph.link(simulation, candidate, "DERIVED_FROM", [sim.evidence_root, built.build_id])
    if observation:
        state = graph.node(
            observation.snapshot_id,
            "PORTFOLIO_STATE",
            "VERIFIED_RECORD" if observation.verification_status == "VERIFIED" else "UNVERIFIED",
            [observation.snapshot_id, observation.content_hash],
            {"block_number": observation.block_number, "block_hash": observation.block_hash},
        )
        # The observation is an evaluation input collected after the proposal.
        graph.link(candidate, state, "DEPENDS_ON", [observation.snapshot_id])
    step_outcomes = {}
    last = None
    for entry in entries:
        decision_id = entry["decision_id"]
        previous = entry["build"]
        action = graph.node(
            previous["intent_id"],
            "AGENT_ACTION",
            "VERIFIED_RECORD",
            [decision_id, previous["build_id"]],
            {
                "build_id": previous["build_id"],
                "amount": previous["amount_in_base_units"],
                "step_id": entry["step_id"],
                "revision": entry["revision"],
                "state": entry["state"],
                "proposal": safe_value(entry.get("proposal")),
            },
        )
        graph.node(
            decision_id,
            "SECURITY_DECISION",
            "VERIFIED_RECORD",
            [decision_id, *([entry["assessment_hash"]] if entry.get("assessment_hash") else [])],
            {
                "state": entry["state"],
                "workflow_id": entry["workflow_id"],
                "assessment_hash": entry.get("assessment_hash"),
            },
        )
        graph.link(action, decision_id, "EVALUATED_BY", [decision_id])
        previous_spec = f"{spec.spec_id}:{entry['revision']}"
        if previous_spec in graph.nodes:
            graph.link(
                previous_spec,
                action,
                "AUTHORIZES",
                [previous_spec, decision_id],
                "AUTHORIZATION_RECORD",
            )
        if last:
            graph.link(last, action, "PRECEDES", [decision_id, last])
        last = action
        outcome = entry.get("outcome")
        if not outcome:
            continue
        proof = outcome["verification"]
        confirmed = confirmed_state(entry, spec)
        outcome_id = graph.node(
            "outcome:" + decision_id,
            "TRANSACTION_OUTCOME",
            "VERIFIED_RECORD" if confirmed else "UNVERIFIED",
            [decision_id, *([proof["tx_hash"]] if proof["tx_hash"] else [])],
            {"state": outcome["state"], "receipt": proof, "invalidated": entry["invalidated"]},
        )
        graph.link(decision_id, outcome_id, "PRODUCED_OUTCOME", [decision_id, outcome_id])
        if confirmed:
            graph.link(action, outcome_id, "EXECUTED_AS", [proof["tx_hash"], decision_id])
        for snap_id, snap_hash in entry.get("snapshots", {}).items():
            graph.node(
                snap_id,
                "PORTFOLIO_STATE",
                "UNVERIFIED" if entry["invalidated"] else "VERIFIED_RECORD",
                [snap_id, snap_hash],
                {"content_hash": snap_hash},
            )
            if confirmed:
                graph.link(
                    outcome_id,
                    snap_id,
                    "UPDATED_STATE" if snap_id == outcome["post_snapshot_id"] else "DERIVED_FROM",
                    [decision_id, snap_id],
                )
        if confirmed == "CONFIRMED":
            step_outcomes[entry["step_id"]] = outcome_id
    if last:
        graph.link(last, candidate, "PRECEDES", [last, proposal.intent_id])
    for dependency in authorized or []:
        if dependency in step_outcomes:
            graph.link(
                candidate,
                step_outcomes[dependency],
                "DEPENDS_ON",
                [spec_ref, step_outcomes[dependency]],
            )
    task_ids = {task["instruction_id"] for task in tasks}
    active_sources = {task["source_message_id"] for task in tasks}
    for message in user_messages:
        message_id = message["message_id"]
        if message_id in active_sources:
            source = graph.node(
                "user-message:" + message_id,
                "AUTHENTICATED_USER_INTENT",
                "AUTHENTICATED",
                [message_id],
                message,
            )
            graph.link(candidate, source, "DEPENDS_ON", [message_id, proposal.intent_id])
    for task in tasks:
        task_id = task["instruction_id"]
        graph.node(
            task_id,
            "AUTHENTICATED_USER_INTENT",
            "MODEL_JUDGMENT",
            [task_id, task["source_message_id"]],
            task,
        )
        source = "user-message:" + task["source_message_id"]
        if source in graph.nodes:
            graph.link(task_id, source, "DERIVED_FROM", [task["source_message_id"]])
    calls = {}
    for check in reports:
        check_id = check["check_id"]
        source_id = "shield-source:" + check_id
        is_tool = check["source"] == "TOOL"
        output = None
        if is_tool and output_context:
            output = output_context.get(check_id, output_context.get(check.get("tool_call_id")))
        graph.node(
            source_id,
            "TOOL_OBSERVATION" if is_tool else "AGENT_ACTION",
            "UNTRUSTED" if is_tool else "UNVERIFIED",
            [check["candidate_hash"]],
            {
                "source_message_id": check.get("source_message_id"),
                "tool_name": check.get("tool_name"),
                "tool_call_id": check.get("tool_call_id"),
                **({"sanitized_output": output} if output is not None else {}),
            },
        )
        graph.node(
            check_id,
            "SEMANTIC_ASSESSMENT",
            "MODEL_JUDGMENT",
            [check_id, check["candidate_hash"]],
            check,
        )
        graph.link(source_id, check_id, "EVALUATED_BY", [check_id, check["candidate_hash"]])
        if check_id in current_report_ids:
            graph.link(candidate, check_id, "EVALUATED_BY", [check_id, proposal.intent_id])
        call_id = check.get("tool_call_id")
        if call_id and check["kind"] == "TOOL_CALL":
            calls[call_id] = source_id
        if call_id in calls and is_tool:
            graph.link(calls[call_id], source_id, "PRODUCED_OUTCOME", [call_id, check_id])
        for result in check["results"]:
            for contribution in result["contributions"]:
                task_id = contribution["task_id"]
                if task_id in task_ids and Decimal(contribution["score"]) > 0:
                    graph.link(
                        source_id,
                        task_id,
                        "CONTRIBUTES_TO",
                        [check_id, result["instruction"]["instruction_id"], task_id],
                        "MODEL_INFERENCE",
                    )
    return graph.finish()
