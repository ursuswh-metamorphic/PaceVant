from types import SimpleNamespace

import pytest

from treasury_backend.modules.alignment.provider import Completion
from treasury_backend.operations.judge_metrics import InferenceMeter


def test_meter_preserves_completion_and_provider_contract_without_recording_content():
    completion = Completion("private model response", 15, {"prompt_tokens":10,"completion_tokens":4,"total_tokens":14,"secret":"do not record"})
    provider = SimpleNamespace(complete=lambda messages:completion,
        last_attempts=[{"provider":"deepseek","model":"deepseek-flash","status":"SUCCESS","endpoint":"secret"}],
        evaluation_scope="REAL",close=lambda:None)
    meter = InferenceMeter(provider,lambda:"ITAG")
    assert meter.complete([{"content":"private prompt"}]) is completion
    assert meter.evaluation_scope == 'REAL'
    report = meter.summary()
    assert report['reported_token_usage'] == {'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}
    assert report['calls'][0]['stage'] == 'ITAG'
    assert not any(value in str(report) for value in ['private','secret','endpoint'])
    assert report['billing_usd'] is None


def test_meter_never_turns_provider_failure_into_a_successful_response():
    def fail(messages):
        raise ValueError('private provider error')
    meter = InferenceMeter(SimpleNamespace(complete=fail,last_attempts=[]),lambda:'PLANNING')
    with pytest.raises(ValueError,match='private provider error'):
        meter.complete([])
    report=meter.summary()
    assert report['call_count']==1 and report['calls'][0]['status']=='FAILED'
    assert report['reported_token_usage']=={} and 'private' not in str(report)
