"""Regression: MVP operation graphs must satisfy the merged ITAG citation protocol."""
from types import SimpleNamespace

import pytest

from treasury_backend.modules.planning.treasury import TreasuryPlan
from treasury_backend.modules.temporal.evidence_catalog import catalog, ground
from treasury_backend.modules.temporal.models import SemanticAssessment, SemanticFinding
from treasury_backend.modules.temporal.operations import evaluate_operation
from treasury_contracts.v3 import OperationIntent


@pytest.mark.parametrize("operation", ["TOKEN_PAYMENT", "TOKEN_SWAP"])
@pytest.mark.parametrize("verdict", ["ALIGNED", "MISALIGNED", "UNCERTAIN"])
def test_operation_catalog_grounds_real_authority_and_actual_model_rationale(operation, verdict):
    intent = OperationIntent(operation=operation, chain_id=43113, treasury="0x"+"11"*20,
        session_id="0x"+"22"*32, token_in="0x"+"33"*20,
        token_out="0x"+("33" if operation=="TOKEN_PAYMENT" else "44")*20,
        recipient="0x"+"55"*20, amount="10000", deadline=200,
        objective="Pay the approved invoice" if operation=="TOKEN_PAYMENT" else "Exchange approved treasury assets")
    plan = TreasuryPlan(**{k:getattr(intent,k) for k in ["operation","token_in","token_out","recipient","amount"]},
        explanation="Actual model rationale, distinct from the authenticated objective.")
    context = {"authority":{"operation_mask":3,"last_rebalance":0,"cooldown":0,"actions":0,"max_actions":5},
        "policy_hash":"0x"+"66"*32,"session_id":intent.session_id,"session_expires_at":300,"chain_id":43113,"policy_version":6}
    built = {"intent":intent.model_dump(mode="json"),"operation":{"intentHash":intent.hash,"policyHash":context['policy_hash']},
        "proposal":{"user_goal_reason":"Untrusted builder must not supply the model rationale"}}
    validated = []

    def assess(graph, candidate, alignment, **flags):
        assert alignment == 'ALIGNED' and not flags['shield_blocked']
        tasks = {node.node_id for node in graph.nodes if node.kind=='AUTHENTICATED_USER_INTENT'}
        nodes = {node.node_id:node for node in graph.nodes}
        evidence = catalog(graph, candidate, tasks)
        assert len(evidence['objective_aliases']) == 1
        raw = {"candidate_alias":evidence['candidate_alias'],"semantic_verdict":verdict,
            "goal_drift_detected":verdict=='MISALIGNED',"uncertainty":["Insufficient semantic support"] if verdict=='UNCERTAIN' else [],
            "task_relationships":[{"task_alias":evidence['task_aliases'][0],
                "relationship":"CONTRADICTORY" if verdict=='MISALIGNED' else 'UNCERTAIN' if verdict=='UNCERTAIN' else 'DIRECT',
                "supporting_aliases":[evidence['candidate_alias'],evidence['objective_aliases'][0]],
                "objective_field":"terms.objective","candidate_field":"proposal.user_goal_reason",
                "explanation":"A test judgment to exercise citation grounding, not a model evaluation."}]}
        finding, anchors = ground(raw,evidence,nodes,candidate,tasks)
        assert anchors[0]['objective_quote'] == intent.objective
        assert anchors[0]['candidate_quote'] == plan.explanation
        return SemanticAssessment(verdict=verdict,finding=SemanticFinding.model_validate(finding),reason_codes=[],provider_metadata={},latency_ms=0,token_usage={})

    temporal = SimpleNamespace(clock=lambda:100,semantic=SimpleNamespace(before_decision=assess),
        shield=SimpleNamespace(validate=lambda *args:validated.append(args)))
    runtime = SimpleNamespace(last_feedback=None,proof=lambda intent:{'session_id':'shield_test','check_ids':['check_real'],'revision':1})
    result = evaluate_operation(temporal,intent,built,context,[],runtime,plan)
    assert result['verdict'] == ('PASS' if verdict=='ALIGNED' else 'REJECT')
    assert len(validated) == 1
    built['operation']['intentHash'] = '0x'+'00'*32
    rejected = evaluate_operation(temporal,intent,built,context,[],runtime,plan)
    assert rejected['verdict']=='REJECT' and 'ITAG_BUILD_MISMATCH' in rejected['reason_codes']
