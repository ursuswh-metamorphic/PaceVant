from app.temporal.models import ExplainableTemporalAssessment


def explain(assessment, graph):
    semantic = assessment.semantic
    finding = semantic.finding
    located = set(assessment.violating_node_ids) | {assessment.candidate_action_id}
    refs = set(assessment.evidence_refs)
    if finding:
        located.update(finding.referenced_graph_node_ids)
        refs.update(finding.supporting_evidence_refs)
    path = [
        edge
        for edge in graph.edges
        if edge.source in located or edge.target in located or refs.intersection(edge.evidence_refs)
    ]
    for edge in path:
        located.update([edge.source, edge.target])
    if "ITAG_UPSTREAM_TASK_SHIELD_INTERVENTION" in assessment.reason_codes:
        summary = "Task Shield intervened before ITAG could authorize a trajectory assessment."
    else:
        summary = f"ITAG returned {assessment.verdict}. Semantic assessment: {semantic.verdict}. Deterministic constraints: {assessment.deterministic.verdict}."
    if semantic.verdict == "ALIGNED" and assessment.deterministic.verdict != "PASS":
        summary += (
            " The model's positive judgment does not satisfy the cited deterministic constraints."
        )
    recovery = {
        "PASS": "Continue through the remaining SDE and signing checks.",
        "REJECT": "Review the cited task constraints. Submit a new candidate only within authenticated limits.",
        "REPLAN": "Build and reassess a candidate within the remaining step budget.",
        "ESCALATE": "Resolve the cited missing evidence, pending outcome or provider failure before retrying.",
    }[assessment.verdict]
    return ExplainableTemporalAssessment(
        assessment=assessment,
        decision_summary=summary,
        semantic_deviation=finding.reasoning_summary
        if finding
        else "No grounded model finding was established.",
        temporal_violations=assessment.deterministic.violations,
        evidence_path=path,
        source_trust={node.node_id: node.trust for node in graph.nodes if node.node_id in located},
        recovery=recovery,
        uncertainty=finding.uncertainty_reasons if finding else semantic.reason_codes,
    )
