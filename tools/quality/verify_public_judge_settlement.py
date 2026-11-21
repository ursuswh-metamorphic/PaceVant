"""Read-only public receipt/balance verification. Does not load wallet keys."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from web3 import Web3

from treasury_backend.modules.execution.chain import contract
from treasury_contracts.mvp import MvpManifest
from treasury_contracts.rpc import evm_web3


def verify(jobs, output):
    manifest_path=Path('deployments/mvp-fuji.json')
    manifest=MvpManifest.model_validate_json(manifest_path.read_text())
    manifest.verify_owner()
    w3=evm_web3(Web3.HTTPProvider('https://api.avax-test.network/ext/bc/C/rpc',request_kwargs={'timeout':15}))
    assert w3.eth.chain_id==43113
    address=Web3.to_checksum_address
    tokens={name:contract(w3,'MockUSDC' if name=='usdc' else 'MockWAVAX',getattr(manifest,name)) for name in ('usdc','wavax')}
    result={'verified_at':datetime.now(timezone.utc).isoformat(),'chain_id':43113,
        'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'verification':'Independent public RPC receipts and historical balances; no state overrides',
        'code_hashes':{},'runs':[]}
    for name,expected in manifest.code_hashes.items():
        actual=Web3.to_hex(Web3.keccak(w3.eth.get_code(address(getattr(manifest,name)))))
        assert actual==expected
        result['code_hashes'][name]=actual
    for path in jobs:
        job=json.loads(path.read_text(encoding='utf-8'))
        assert job['environment']=='REAL_FUJI_EXECUTION' and job['status']=='CONFIRMED'
        workflow=job['workflow']
        intent=workflow['intent']
        outcome=workflow['outcome']
        receipt=w3.eth.get_transaction_receipt(outcome['tx_hash'])
        n=receipt.blockNumber
        tx=w3.eth.get_transaction(outcome['tx_hash'])
        assert receipt.status==1 and w3.eth.get_block(n).hash==receipt.blockHash
        assert tx['from'].lower()==manifest.relayer and tx['to'].lower()==manifest.treasury
        fee=receipt.gasUsed*receipt.effectiveGasPrice
        debit=w3.eth.get_balance(address(manifest.relayer),n-1)-w3.eth.get_balance(address(manifest.relayer),n)
        assert debit==fee
        def delta(token,owner,n=n):
            return tokens[token].functions.balanceOf(address(owner)).call(block_identifier=n)-tokens[token].functions.balanceOf(address(owner)).call(block_identifier=n-1)
        vault_deltas={name:str(delta(name,manifest.treasury)) for name in tokens}
        assert int(vault_deltas['usdc'])==-int(intent['amount'])
        payee_delta=delta('usdc',intent['recipient']) if job['scenario']=='payment' else None
        if job['scenario']=='payment':
            assert payee_delta==int(intent['amount'])
        else:
            assert int(vault_deltas['wavax'])>0
        metrics=job.get('runtime_metrics',{})
        inference=metrics.get('inference',{})
        result['runs'].append({'job_id':job['job_id'],'scenario':job['scenario'],
            'tx_hash':outcome['tx_hash'],'block_number':n,'status':1,
            'confirmations':w3.eth.block_number-n+1,'recipient':intent['recipient'],
            'amount_in_base_units':intent['amount'],'vault_delta_base_units':vault_deltas,
            'payee_usdc_received_base_units':str(payee_delta) if payee_delta is not None else None,
            'gas_used':receipt.gasUsed,'effective_gas_price_wei':str(receipt.effectiveGasPrice),
            'fee_wei':str(fee),'fee_avax':format(Decimal(fee)/10**18,'f'),
            'relayer_balance_debit_wei':str(debit),'worker_wall_seconds':metrics.get('worker_wall_seconds'),
            'inference_calls':inference.get('call_count'),'reported_token_usage':inference.get('reported_token_usage'),
            'model_invoice_usd':None})
    head=w3.eth.block_number
    result['current_block']=head
    result['balances']={role:{'address':getattr(manifest,role),'avax_wei':str(w3.eth.get_balance(address(getattr(manifest,role)),head)),
        **{name:str(token.functions.balanceOf(address(getattr(manifest,role))).call(block_identifier=head)) for name,token in tokens.items()}}
        for role in ('owner','attestor','relayer','treasury')}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'verified_runs':len(result['runs']),'output':str(output)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('jobs',type=Path,nargs='+')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    verify(args.jobs,args.output)
