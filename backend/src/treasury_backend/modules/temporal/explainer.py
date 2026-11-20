from treasury_backend.modules.temporal.models import ExplainableTemporalAssessment


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
        summary = "Task Shield blocked this candidate before the trajectory model ran."
    elif "ITAG_WALLET_ALIGNMENT_INTERVENTION" in assessment.reason_codes:
        summary = "Wallet alignment checks blocked this candidate before the trajectory model ran."
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
    if "ITAG_CANDIDATE_EXPIRED" in assessment.reason_codes:
        recovery = "Create a fresh candidate and repeat the checks within its approval window."
    candidate = next((n for n in graph.nodes if n.node_id == assessment.candidate_action_id), None)
    proposal = (candidate.data.get("proposal") or {}) if candidate else {}
    facts = {
        "intent_records": [
            {"node": n.node_id, "trust": n.trust, "revision": n.data.get("revision"),
             "status": n.data.get("effective_status", n.data.get("status")), "terms": n.data["terms"]}
            for n in graph.nodes if n.kind == "AUTHENTICATED_USER_INTENT" and "terms" in n.data
        ],
        "candidate": {k: proposal.get(k) for k in (
            "intent_id", "action", "chain_id", "token_in", "token_out", "recipient",
            "amount_in_base_units", "user_goal_reason")},
        "budget_in_token_base_units": {"spent": assessment.deterministic.spent,
                                       "reserved": assessment.deterministic.reserved,
                                       "remaining": assessment.deterministic.remaining},
        "prior_outcomes": [
            {"node": n.node_id, "state": n.data.get("state"), "trust": n.trust,
             "invalidated": n.data.get("invalidated")} for n in graph.nodes
            if n.kind == "TRANSACTION_OUTCOME"
        ],
        "stage": "PRE_SIGN", "first_semantic_divergence_step": None,
        "semantic_anchors": semantic.provider_metadata.get("semantic_anchors", []),
        "semantic_text_status": "MODEL_INFERENCE",
    }
    return ExplainableTemporalAssessment(
        assessment=assessment,
        recorded_facts=facts,
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
