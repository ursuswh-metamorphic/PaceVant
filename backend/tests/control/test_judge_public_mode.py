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
