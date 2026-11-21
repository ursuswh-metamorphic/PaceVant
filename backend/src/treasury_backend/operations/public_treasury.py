"""Real Fuji composition. Owner keys are never read by the serving worker."""
import json
import os
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr

from treasury_backend.config.control import Settings as ControlSettings
from treasury_backend.config.execution import Settings
from treasury_backend.modules.execution.mvp import MvpExecution
from treasury_backend.modules.workflows.service import ControlPlane
from treasury_backend.modules.workflows.treasury import TreasuryWorkflows
from treasury_contracts.mvp import MvpManifest


@contextmanager
def prepared_public(directory,shield,progress):
    if os.environ.get('PACEVANT_MVP_LIVE_ENABLED')!='1':
        raise ValueError('MVP_PUBLIC_EXECUTION_NOT_AUTHORIZED')
    manifest=MvpManifest.model_validate(json.loads(Path(os.environ['PACEVANT_MVP_MANIFEST_FILE']).read_text(encoding='utf-8')))
    manifest.verify_owner()
    if manifest.environment!='REAL_FUJI_EXECUTION':
        raise ValueError('PUBLIC_MANIFEST_REQUIRED')
    root=directory.parents[1]
    rpc=os.environ['PACEVANT_JUDGE_RPC_URL']
    settings=Settings(_env_file=None,mode='fuji',rpc_url=rpc,fork_rpc_url=rpc,
        data_dir=root/'execution',relayer_private_key=SecretStr(os.environ['B_FUJI_RELAYER_PRIVATE_KEY']),
        max_ttl=180,required_confirmations=2,receipt_timeout=45)
    execution=MvpExecution(settings,manifest,live_enabled=True)
    # This checks the live oracle and current session; no transaction is signed
    # while waiting, and no fixture price can authorize execution.
    until=time.monotonic()+int(os.environ.get('PACEVANT_JUDGE_ORACLE_WAIT_SECONDS','45'))
    while True:
        try:
            context=execution.context(manifest.default_session_id)
            if context['oracle_valid_until']-int(time.time())>=90:
                break
        except ValueError as error:
            if str(error)!='ORACLE_WINDOW_UNAVAILABLE':
                raise
        if time.monotonic()>=until:
            raise ValueError('FRESH_CHAINLINK_SIGNING_WINDOW_UNAVAILABLE')
        progress(phase='WAITING_FOR_ORACLE')
        time.sleep(5)
    control_settings=replace(ControlSettings(),mode='FUJI',db=root/'control.sqlite3',require_itag=True,
        shield=shield,attestor_key=os.environ['PACEVANT_ATTESTOR_KEY'],chain_rpc_url=rpc,
        relayer_address=manifest.relayer)
    control=ControlPlane(control_settings,client_factory=lambda *_:None)
    try:
        yield SimpleNamespace(workflows=TreasuryWorkflows(control,execution),execution=execution,manifest=manifest,
            source_block=context['block_number'],setup=[])
    finally:
        control.close()
