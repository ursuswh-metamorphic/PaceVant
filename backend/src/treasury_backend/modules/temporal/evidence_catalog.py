"""Graph-bound evidence selections. Models judge meaning; the server resolves records."""

import json
from typing import Literal

from pydantic import Field

from treasury_backend.modules.portfolio.observations import content_hash
from treasury_backend.modules.temporal.models import SemanticFinding, Text
from treasury_contracts.models import Wire


class Relationship(Wire):
    task_alias: str
    relationship: Literal["DIRECT", "INDIRECT", "IRRELEVANT", "CONTRADICTORY", "UNCERTAIN"]
    supporting_aliases: list[str] = Field(min_length=2, max_length=16)
    objective_field: Literal["terms.objective"]
    candidate_field: Literal["proposal.user_goal_reason"]
    explanation: Text


class Judgment(Wire):
    candidate_alias: str
    semantic_verdict: Literal["ALIGNED", "MISALIGNED", "UNCERTAIN"]
    goal_drift_detected: bool
    task_relationships: list[Relationship] = Field(min_length=1, max_length=16)
    uncertainty: list[Text] = Field(max_length=8)


def catalog(graph, candidate, tasks):
    binding = content_hash({"graph": graph.model_dump(mode="json"), "candidate": candidate})
    nodes = sorted(graph.nodes, key=lambda n: n.node_id)
    aliases = {n.node_id: f"E{i}_{binding[2:34]}" for i, n in enumerate(nodes)}
    entries = []
    for n in nodes:
        data = n.data
        # Keep scope, all action/history fields and trust. Remove repeated serialized checks.
        if n.kind == "SEMANTIC_ASSESSMENT":
            data = {k: data[k] for k in ("status", "verdict", "reason_codes") if k in data}
        if n.kind == "TOOL_OBSERVATION" and "sanitized_output" in data:
            data = dict(data)
            output = data.pop("sanitized_output")
            preview = json.dumps(output, ensure_ascii=False)
            data.update(
                output_preview=preview[:400],
                preview_truncated=len(preview) > 400,
                output_record_hash=content_hash(output),
            )
        entries.append(
            {
                "alias": aliases[n.node_id],
                "node_id": n.node_id,
                "kind": n.kind,
                "trust": n.trust,
                "scope_role": "ACTIVE_OPERATOR_INTENT"
                if n.data.get("authorization_source") == "OPERATOR_API"
                and n.data.get("status") == "AUTHENTICATED"
                and n.data.get("effective_status") != "SUPERSEDED"
                else "CONTEXT",
                "evidence_refs": n.evidence_refs,
                "fields": data,
            }
        )
    return {
        "binding": binding,
        "candidate_alias": aliases[candidate],
        "task_aliases": [aliases[t] for t in sorted(tasks)],
        "objective_aliases": [e["alias"] for e in entries if e["scope_role"] == "ACTIVE_OPERATOR_INTENT"],
        "entries": entries,
        "edges": [
            {
                "source": aliases[e.source],
                "target": aliases[e.target],
                "kind": e.kind,
                "provenance": e.provenance,
            }
            for e in graph.edges
        ],
    }


def ground(raw, evidence, nodes, candidate, tasks):
    judgment = Judgment.model_validate(raw)
    entries = {e["alias"]: e for e in evidence["entries"]}
    if judgment.candidate_alias != evidence["candidate_alias"]:
        raise ValueError("CATALOG_CANDIDATE_MISMATCH")
    selected = set()
    contributions = []
    seen = set()
    anchors = []
    for relation in judgment.task_relationships:
        task = entries.get(relation.task_alias)
        if not task or task["node_id"] not in tasks or relation.task_alias in seen:
            raise ValueError("CATALOG_TASK_MISMATCH")
        seen.add(relation.task_alias)
        if any(a not in entries for a in relation.supporting_aliases):
            raise ValueError("CATALOG_UNKNOWN_ALIAS")
        support = {entries[a]["node_id"] for a in relation.supporting_aliases}
        if candidate not in support:
            raise ValueError("CATALOG_MISSING_CANDIDATE")
        # Only the active operator-authenticated scope can anchor an objective claim.
        scopes = [
            nodes[n]
            for n in support
            if nodes[n].kind == "AUTHENTICATED_USER_INTENT"
            and nodes[n].trust == "AUTHENTICATED"
            and nodes[n].data.get("status") == "AUTHENTICATED"
            and nodes[n].data.get("effective_status") != "SUPERSEDED"
            and nodes[n].data.get("authorization_source") == "OPERATOR_API"
        ]
        if len(scopes) != 1 or not scopes[0].data.get("terms", {}).get("objective"):
            raise ValueError("CATALOG_OBJECTIVE_UNSUPPORTED")
        quote = scopes[0].data["terms"]["objective"]
        rationale = (nodes[candidate].data.get("proposal") or {}).get("user_goal_reason", "")
        if not rationale:
            raise ValueError("CATALOG_CANDIDATE_QUOTE_UNSUPPORTED")
        selected.update(support | {task["node_id"]})
        anchors.append(
            {
                "task": task["node_id"],
                "objective_quote": quote,
                "candidate_quote": rationale,
            }
        )
        contributions.append(
            {
                "task_id": task["node_id"],
                "relationship": relation.relationship,
                "explanation": relation.explanation,
            }
        )
    if judgment.semantic_verdict == "MISALIGNED" and not any(
        c["relationship"] in {"IRRELEVANT", "CONTRADICTORY"} for c in contributions
    ):
        raise ValueError("CATALOG_MISSING_SEMANTIC_CONFLICT")
    if judgment.goal_drift_detected and judgment.semantic_verdict != "MISALIGNED":
        raise ValueError("CATALOG_INCONSISTENT_DRIFT")
    finding = SemanticFinding(
        candidate_action_id=candidate,
        referenced_task_ids=[c["task_id"] for c in contributions],
        referenced_graph_node_ids=sorted(selected),
        semantic_verdict=judgment.semantic_verdict,
        contribution_assessments=contributions,
        detected_goal_drift=judgment.goal_drift_detected,
        claimed_instruction_source="ASSISTANT",
        reasoning_summary=" ".join(c["explanation"] for c in contributions)[:1200],
        supporting_evidence_refs=sorted({r for n in selected for r in nodes[n].evidence_refs}),
        uncertainty_reasons=judgment.uncertainty,
    )
    return finding.model_dump(mode="json"), anchors
