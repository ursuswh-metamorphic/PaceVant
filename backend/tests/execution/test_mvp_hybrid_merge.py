"""The merged hybrid gate must bind exact MVP authority before signing."""

import pytest
from test_mvp_workflows import workflows  # noqa: F401
from test_v3_execution import intent

from treasury_backend.modules.alignment.types import Message


@pytest.mark.parametrize('change', [
    {'amount':'1000001'}, {'amount':'999999'}, {'min_output':'999999'}, {'recipient':'0x'+'11'*20}, {'chain_id':1},
    {'slippage_bps':101}, {'deadline':2**32}, {'token_in':'0x'+'22'*20},
    {'treasury':'0x'+'11'*20}, {'operation':'VAULT_WITHDRAW'},
])
def test_hybrid_rejects_changes_to_authenticated_fixed_terms(mvp, workflows, change):
    request = intent(mvp,'TOKEN_PAYMENT','1000000').model_copy(update={'min_output':'1000000'})
    runtime = workflows._runtime('hybrid-'+next(iter(change)), request)
    message = Message(message_id='candidate',role='ASSISTANT',content='bounded operation')
    tool={'tool_name':'propose_fixed_operation','arguments':request.model_dump(mode='json')}
    allowed=workflows.control.shield.check(runtime.session_id,message,tool=tool)
    assert allowed.algorithm=='hybrid-v1'
    assert allowed.status=='ALIGNED'
    changed={**tool,'arguments':{**tool['arguments'],**change}}
    rejected=workflows.control.shield.check(runtime.session_id,message.model_copy(update={'message_id':'tampered'}),tool=changed)
    assert rejected.status=='MISALIGNED'
    assert any(result.status=='FAIL' for result in rejected.constraints)
