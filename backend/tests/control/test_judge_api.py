"""Public controller security and durable quotas. The fork engine is tested separately."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest
from fastapi.testclient import TestClient

from treasury_backend.api.judge import create_app
from treasury_backend.config.judge import JudgeSettings
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.workflows.judge import JudgeController, worker_environment


@pytest.fixture
def judge(tmp_path, monkeypatch):
    settings = JudgeSettings(data_dir=tmp_path, enabled=True, secure_cookie=False)
    monkeypatch.setattr(JudgeSettings, "configured", lambda _:True)
    release = Event()

    def runner(id_, scenario):
        release.wait(2)
        return {"status":"REJECTED", "reason_code":"PAYEE_NOT_ALLOWED", "environment":"ANVIL_FORK", "public_chain_broadcast":False}

    controller = JudgeController(settings, runner=runner)
    with TestClient(create_app(settings, controller=controller)) as client:
        yield client, controller, release
        release.set()


def test_anonymous_fixed_job_recovery_and_separate_permissions(judge):
    client, controller, release = judge
    client.get('/judge/config')
    first = client.post('/judge/jobs', json={'scenario':'guard'}, headers={'Idempotency-Key':'same-attempt'})
    assert first.status_code == 202
    id_ = first.json()['job_id']
    assert client.post('/judge/jobs', json={'scenario':'guard'}, headers={'Idempotency-Key':'same-attempt'}).json()['job_id'] == id_
    assert client.get('/judge/requests/same-attempt').json()['job_id'] == id_
    assert client.post('/judge/jobs', json={'scenario':'payment'}, headers={'Idempotency-Key':'different-attempt'}).status_code == 429
    assert client.post('/judge/jobs', json={'scenario':'guard', 'recipient':'arbitrary'}, headers={'Idempotency-Key':'bad-payload'}).status_code == 400
    assert client.post('/judge/jobs', json={'scenario':'guard'}, headers={'Idempotency-Key':'same-attempt','Origin':'https://evil.test'}).status_code == 403
    for path in ['/mvp/workflows','/mvp/admin/prepare','/execution/v1/execute','/docs','/openapi.json']:
        assert client.post(path, json={}).status_code in {404,405}
    with TestClient(create_app(controller.settings, controller=JudgeController(replace(controller.settings, data_dir=controller.settings.data_dir/'second')))) as other:
        assert other.get('/judge/jobs/'+id_).status_code == 404
    release.set()


def test_atomic_global_concurrency_and_persistent_quota(judge):
    _, controller, release = judge
    def attempt(i):
        try:
            return controller.create('visitor-'+str(i), 'same-ip', 'swap', 'attempt-'+str(i))
        except ControlError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert sum(isinstance(x,dict) for x in results) == 1
    assert results.count('DEMO_BUSY') == 3
    assert controller.remaining(next('visitor-'+str(i) for i,r in enumerate(results) if isinstance(r,dict))) == 5
    release.set()


def test_restart_marks_uncertain_fork_interrupted_without_resend(tmp_path, monkeypatch):
    settings = JudgeSettings(data_dir=tmp_path, enabled=True, secure_cookie=False)
    monkeypatch.setattr(JudgeSettings,'configured',lambda _:True)
    first = JudgeController(settings, runner=lambda *_:{'status':'UNKNOWN'})
    first.start()
    record = first.create('visitor','ip','payment','attempt-123')
    first.pool.shutdown(wait=True)
    first.update(record['job_id'],status='RUNNING')
    first.instance.release()
    second = JudgeController(settings, runner=lambda *_:pytest.fail('Restart must not resend'))
    second.start()
    assert second.get('visitor',id_=record['job_id'])['status'] == 'INTERRUPTED'
    assert second.remaining('visitor') == 5
    second.close()


def test_worker_environment_excludes_system_keys(monkeypatch, tmp_path):
    for name in ['PACEVANT_ATTESTOR_KEY','B_RELAYER_PRIVATE_KEY','B_FUJI_OWNER_PRIVATE_KEY','PACEVANT_OPERATOR_TOKEN']:
        monkeypatch.setenv(name,'never-forward-this')
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-model-only')
    env = worker_environment(JudgeSettings(data_dir=tmp_path))
    assert 'never-forward-this' not in env.values()
    assert env['DEEPSEEK_API_KEY'] == 'test-model-only'


def test_size_limit_and_visitor_separation(judge):
    client, controller, release = judge
    client.get('/judge/config')
    assert client.post('/judge/jobs',content=b'x'*5000,headers={'Content-Type':'application/json'}).status_code == 413
    record = client.post('/judge/jobs',json={'scenario':'payment'},headers={'Idempotency-Key':'private-job'}).json()
    client.cookies.clear()
    assert client.get('/judge/jobs/'+record['job_id']).status_code == 404
    release.set()


def test_durable_daily_and_ip_limits(tmp_path, monkeypatch):
    settings=JudgeSettings(data_dir=tmp_path,enabled=True,secure_cookie=False,daily_limit=1,ip_hourly_limit=1,global_daily_limit=5)
    monkeypatch.setattr(JudgeSettings,'configured',lambda _:True)
    controller=JudgeController(settings,runner=lambda *_:{'status':'CONFIRMED'},clock=lambda:10000)
    controller.start()
    try:
        first=controller.create('one','ip-one','payment','first-attempt')
        controller.pool.shutdown(wait=True)
        assert controller.get('one',id_=first['job_id'])['terminal']
        with pytest.raises(ControlError,match='DEMO_RATE_LIMIT'):
            controller.create('one','ip-other','payment','second-attempt')
        with pytest.raises(ControlError,match='DEMO_RATE_LIMIT'):
            controller.create('new-cookie','ip-one','payment','third-attempt')
    finally:
        controller.close()


def test_timeout_stops_owned_worker_tree_and_preserves_job(tmp_path,monkeypatch):
    import subprocess
    from types import SimpleNamespace

    settings=JudgeSettings(data_dir=tmp_path,enabled=True,secure_cookie=False)
    controller=JudgeController(settings)
    proc=SimpleNamespace(wait=lambda **_:(_ for _ in ()).throw(subprocess.TimeoutExpired('test-worker',1)))
    stopped=[]
    monkeypatch.setattr('treasury_backend.modules.workflows.judge.subprocess.Popen',lambda *_,**__:proc)
    monkeypatch.setattr('treasury_backend.modules.workflows.judge.stop_tree',lambda owned:stopped.append(owned))
    with pytest.raises(ValueError,match='DEMO_TIMEOUT'):
        controller.run_worker('judge_timeout','payment')
    assert stopped and all(item is proc for item in stopped)
    assert controller.process is None
    controller.pool.shutdown()


def test_dynamic_source_is_labeled_and_replay_is_never_new_public_execution(judge, monkeypatch):
    client, _, _ = judge
    sample={'status':'VERIFIED_READ','block_number':123,'balances':{'usdc':'1','wavax':'0'}}
    monkeypatch.setattr('treasury_backend.operations.judge_source.observe',lambda _:sample)
    assert client.get('/judge/source').json()==sample
    replay=client.get('/judge/replays/payment').raise_for_status().json()
    assert replay['environment']=='VERIFIED_REPLAY'
    assert replay['public_chain_broadcast'] is False
    assert replay['workflow']['outcome']['environment']=='ANVIL_FORK'
    guard=client.get('/judge/replays/guard').raise_for_status().json()
    assert guard['reason_code']=='LFJ_UNSUPPORTED_ROUTE'
    assert guard['active_stage']=='BUILD'
