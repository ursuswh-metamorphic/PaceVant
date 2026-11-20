"""CLI verification using the same isolated preparation/workflow as public judge mode."""

import argparse
import io
import json
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

from treasury_backend.modules.alignment.provider import ShieldConfig
from treasury_backend.operations.fork_treasury import prepared_fork, require_isolated_fork
from treasury_backend.paths import ROOT
from treasury_contracts.v3 import OperationIntent

__all__ = ["load_model_settings", "require_isolated_fork", "verify"]


def load_model_settings(path):
    """Only model lines are parsed; never load wallet/service keys from an env file."""
    prefixes = ("PACEVANT_SHIELD_", "GROQ_", "GEMINI_", "XINGCHI_", "DEEPSEEK_")
    with path.open(encoding="utf-8-sig") as source:
        selected = [line for line in source if line.partition("=")[0].strip().startswith(prefixes)]
    for name, value in dotenv_values(stream=io.StringIO("".join(selected)), interpolate=False).items():
        if value is not None:
            os.environ[name] = value


def verify(args):
    if args.model_env:
        load_model_settings(args.model_env)
    fixture = None
    if args.protocol_fixture:
        from treasury_backend.operations.mvp_protocol_fixture import ProtocolFixture

        fixture = ProtocolFixture()
        shield = ShieldConfig(mode="wallet_pipeline", model="LOCAL_PROTOCOL_FIXTURE", context_chars=100000)
    else:
        shield = ShieldConfig.from_env("FUJI")
    result = {"environment":"ANVIL_FORK", "public_writes":False, "results":[],
              "semantic_scope":fixture.evaluation_scope if fixture else "REAL_CONFIGURED_PROVIDER"}
    with prepared_fork(args.rpc, args.data, shield, provider=fixture, wait_seconds=args.wait_fresh_seconds) as prepared:
        m = prepared.manifest
        result.update(source_block=prepared.source_block, source_block_hash=prepared.source_block_hash,
                      test_role_keys="THREE_EPHEMERAL_KEYS_NOT_PERSISTED")
        for payment, amount in ((True,"10000"), (False,"1")):
            c = prepared.execution.context(m.default_session_id)
            intent = OperationIntent(operation="TOKEN_PAYMENT" if payment else "TOKEN_SWAP", chain_id=43113,
                treasury=m.treasury, session_id=m.default_session_id, token_in=m.usdc,
                token_out=m.usdc if payment else m.wavax, recipient=m.owner if payment else m.treasury, amount=amount,
                slippage_bps=0 if payment else 40, deadline=min(c["timestamp"]+180,c["oracle_valid_until"]),
                objective="Pay exactly 0.01 Circle USDC to the approved EOA" if payment else "Swap exactly 0.000001 Circle USDC for WAVAX to the treasury")
            record = prepared.workflows.run(intent,"fork-"+secrets.token_hex(8))
            (args.data/(intent.operation+'.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
            stages={event['stage']:event['evidence'] for event in record['timeline']}
            result['results'].append({'operation':'USDC_PAYMENT' if payment else 'SWAP_EXACT_IN', 'status':record['status'],
                'reason':record.get('reason_code'), 'stages':list(stages), 'outcome':record.get('outcome'),
                'proof_status':stages.get('PROOF',{}).get('status'),
                'risk_debit_usd_e8':stages.get('PROOF',{}).get('risk_debit_usd_e8'),
                'exact_signed_preflight':stages.get('EXACT_SIGNED_PREFLIGHT',{}).get('exact_signed_preflight'),
                'preflight_overrides':stages.get('EXACT_SIGNED_PREFLIGHT',{}).get('simulation_overrides')})
        result['setup']={'new_deployments_and_configuration':prepared.setup,
            'total_new_owner_setup_fee_wei':str(sum(int(x['actual_fee_wei']) for x in prepared.setup)),
            'funding':'5 copied Circle USDC, isolated fork only', 'prices':'Unmodified Chainlink rounds'}
    result['status']='PASS' if all(r['status']=='CONFIRMED' for r in result['results']) else 'NOT_VERIFIED'
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--rpc',default='https://api.avax-test.network/ext/bc/C/rpc')
    p.add_argument('--model-env',type=Path)
    p.add_argument('--protocol-fixture',action='store_true')
    p.add_argument('--wait-fresh-seconds',type=int,default=0)
    p.add_argument('--data',type=Path,default=ROOT/'data/mvp-real-fuji-fork')
    p.add_argument('--output',type=Path,default=ROOT/'docs/audit/mvp-full-fuji-fork.json')
    args=p.parse_args()
    if not 0<=args.wait_fresh_seconds<=600:
        p.error('Wait must be between 0 and 600 seconds')
    args.data=args.data/secrets.token_hex(8)
    try:
        result=verify(args)
    except Exception as error:
        from treasury_backend.modules.workflows.judge import code

        result={'environment':'ANVIL_FORK','public_writes':False,'status':'NOT_VERIFIED','reason':code(error)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 2


if __name__=='__main__':
    raise SystemExit(main())
