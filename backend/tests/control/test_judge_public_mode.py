import json
from dataclasses import replace

import pytest
from eth_account import Account
from web3 import Web3

from treasury_backend.config.judge import JudgeSettings
from treasury_backend.modules.workflows.judge import worker_environment
from treasury_contracts.mvp import MvpManifest


@pytest.fixture
def enabled_public(tmp_path,monkeypatch):
    owner,attestor,relayer=[Account.from_key('0x'+str(n).zfill(64)) for n in (1,2,3)]
    manifest=MvpManifest(environment='REAL_FUJI_EXECUTION',chain_id=43113,
        treasury='0x'+'11'*20,usdc='0x'+'22'*20,wavax='0x'+'33'*20,adapter='0x'+'44'*20,
        owner=owner.address,attestor=attestor.address,relayer=relayer.address,
        default_session_id='0x'+'55'*32,payee_candidates=(owner.address,),
        code_hashes={name:'0x'+'66'*32 for name in ['treasury','usdc','wavax','adapter']})
    manifest=manifest.model_copy(update={'owner_signature':Web3.to_hex(owner.sign_message(manifest.signing_message()).signature)})
    path=tmp_path/'manifest.json'
    path.write_text(manifest.model_dump_json(),encoding='utf-8')
    for key in ['B_FUJI_OWNER_PRIVATE_KEY','B_OWNER_PRIVATE_KEY','DEPLOYER_PRIVATE_KEY']:
        monkeypatch.delenv(key,raising=False)
    for key,value in {'PACEVANT_JUDGE_EXECUTION_MODE':'REAL_FUJI_EXECUTION','PACEVANT_MVP_LIVE_ENABLED':'1',
        'PACEVANT_MVP_MANIFEST_FILE':str(path),'PACEVANT_ATTESTOR_KEY':attestor.key.hex(),
        'B_FUJI_RELAYER_PRIVATE_KEY':relayer.key.hex(),'PACEVANT_JUDGE_ENABLED':'1',
        'PACEVANT_SHIELD_MODE':'wallet_pipeline','DEEPSEEK_API_KEY':'unit-model-key'}.items():
        monkeypatch.setenv(key,value)
    return JudgeSettings.from_env(),path


def test_public_worker_receives_only_two_serving_keys(enabled_public,monkeypatch):
    settings,_=enabled_public
    monkeypatch.setenv('DEPLOYER_PRIVATE_KEY','must-never-forward')
    monkeypatch.setenv('B_FUJI_OWNER_PRIVATE_KEY','must-never-forward')
    env=worker_environment(settings)
    assert env['PACEVANT_JUDGE_EXECUTION_MODE']=='REAL_FUJI_EXECUTION'
    assert env['PACEVANT_MVP_MANIFEST_FILE']==str(settings.manifest_file)
    assert env['PACEVANT_ATTESTOR_KEY'] and env['B_FUJI_RELAYER_PRIVATE_KEY']
    assert 'must-never-forward' not in env.values()
    fork=worker_environment(replace(settings,execution_mode='ANVIL_FORK'))
    assert 'PACEVANT_ATTESTOR_KEY' not in fork and 'B_FUJI_RELAYER_PRIVATE_KEY' not in fork


def test_public_requires_explicit_activation_and_forbids_owner_in_server(enabled_public,monkeypatch):
    monkeypatch.setenv('PACEVANT_MVP_LIVE_ENABLED','0')
    with pytest.raises(ValueError,match='MVP_PUBLIC_EXECUTION_NOT_AUTHORIZED'):
        JudgeSettings.from_env()
    monkeypatch.setenv('PACEVANT_MVP_LIVE_ENABLED','1')
    monkeypatch.setenv('B_FUJI_OWNER_PRIVATE_KEY','unit-only')
    with pytest.raises(ValueError,match='OWNER_KEY_FORBIDDEN_IN_SERVING'):
        JudgeSettings.from_env()


def test_unsigned_manifest_cannot_configure_live_service(enabled_public):
    settings,path=enabled_public
    value=json.loads(path.read_text(encoding='utf-8'))
    value['owner_signature']='0x'
    path.write_text(json.dumps(value),encoding='utf-8')
    assert not settings.configured()


def test_public_can_wait_for_real_oracle_without_extending_fork_limits(enabled_public,monkeypatch):
    monkeypatch.setenv('PACEVANT_JUDGE_TIMEOUT_SECONDS','900')
    monkeypatch.setenv('PACEVANT_JUDGE_ORACLE_WAIT_SECONDS','720')
    assert JudgeSettings.from_env().wait_oracle_seconds==720
    monkeypatch.setenv('PACEVANT_JUDGE_EXECUTION_MODE','ANVIL_FORK')
    with pytest.raises(ValueError,match='INVALID_JUDGE_LIMIT'):
        JudgeSettings.from_env()


def test_public_waits_on_stale_feed_instead_of_approving_or_stopping_early(enabled_public,tmp_path,monkeypatch):
    from types import SimpleNamespace

    from treasury_backend.core.errors import ControlError
    from treasury_backend.operations import public_treasury as module

    calls=[]
    progress=[]
    header=SimpleNamespace(number=123,timestamp=1000)
    def reference(*args):
        calls.append(args)
        if len(calls)==1:
            raise ControlError('STALE_OR_UNVERIFIED_CHAINLINK_PRICE')
        return (100,200,{},1300)
    chain=SimpleNamespace(w3=SimpleNamespace(eth=SimpleNamespace(get_block=lambda _:header)),
        vault=SimpleNamespace(functions=SimpleNamespace(proofPolicy=lambda:SimpleNamespace(call=lambda **_: (0,0,0,0,0,300)))),
        reference=reference)
    monkeypatch.setenv('PACEVANT_JUDGE_RPC_URL','https://api.avax-test.network/ext/bc/C/rpc')
    monkeypatch.setattr(module,'MvpExecution',lambda *_,**__:SimpleNamespace(chain=chain))
    monkeypatch.setattr(module,'ControlPlane',lambda *_,**__:SimpleNamespace(close=lambda:None))
    monkeypatch.setattr(module,'TreasuryWorkflows',lambda *_:None)
    monkeypatch.setattr(module.time,'time',lambda:1000)
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    with module.prepared_public(tmp_path/'runs'/'job',None,lambda **v:progress.append(v)) as prepared:
        assert prepared.intent_context['oracle_valid_until']==1300
    assert len(calls)==2 and progress==[{'phase':'WAITING_FOR_ORACLE'}]


def test_shared_reconciliation_never_publishes_another_workflow_to_current_job():
    from types import SimpleNamespace

    from treasury_backend.operations.judge_worker import job_event_writer

    persisted,published=[],[]
    claimed=[None]
    store=SimpleNamespace(event=lambda *args:persisted.append(args),
        by_key=lambda key:claimed[0],get=lambda id_:{'workflow_id':id_})
    writer=job_event_writer(store,'job-current',lambda **value:published.append(value))
    writer('prior','RECONCILIATION',{'status':'CONFIRMED'},1)
    assert len(persisted)==1 and published==[]
    claimed[0]={'workflow_id':'current'}
    writer('prior','RECONCILIATION',{'status':'CONFIRMED'},2)
    assert published==[]
    writer('current','OWNER_AUTHORITY',{},3)
    assert published==[{'workflow':{'workflow_id':'current'}}]


def test_progress_replace_retries_transient_windows_reader_without_changing_data(tmp_path,monkeypatch):
    from treasury_backend.operations import judge_worker

    real_replace=judge_worker.os.replace
    attempts=[]
    def replace(source,target):
        attempts.append(target)
        if len(attempts)<3:
            raise PermissionError('controlled reader sharing violation')
        return real_replace(source,target)
    monkeypatch.setattr(judge_worker.os,'replace',replace)
    monkeypatch.setattr(judge_worker.time,'sleep',lambda _:None)
    target=tmp_path/'progress.json'
    judge_worker.atomic(target,{'active_stage':'ITAG','proof':'real persisted value'})
    assert len(attempts)==3
    assert json.loads(target.read_text())=={'active_stage':'ITAG','proof':'real persisted value'}
