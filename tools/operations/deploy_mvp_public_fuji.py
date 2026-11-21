"""Explicit, resumable public Fuji deployment using the existing three user EOAs."""
import argparse
import json
import os
import time
from pathlib import Path

from dotenv import dotenv_values
from eth_account import Account
from web3 import Web3

from treasury_backend.modules.execution.chain import artifact, contract
from treasury_backend.modules.execution.dex.lfj import LFJClient
from treasury_contracts.crypto import content_hash
from treasury_contracts.mvp import MvpManifest
from treasury_contracts.rpc import evm_web3

ROOT=Path(__file__).resolve().parents[2]


def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2),encoding='utf-8')
    os.replace(tmp,path)


def deploy(args):
    env=dotenv_values(args.env,interpolate=True)
    owner=Account.from_key(env['B_FUJI_OWNER_PRIVATE_KEY'])
    old=json.loads((ROOT/'deployments/treasury-fuji-v2.json').read_text(encoding='utf-8'))
    roles={name:old[name] for name in ['owner','attestor','relayer']}
    if owner.address.lower()!=roles['owner'].lower():
        raise ValueError('OWNER_IDENTITY_MISMATCH')
    for role,key in [('attestor','PACEVANT_ATTESTOR_KEY'),('relayer','B_FUJI_RELAYER_PRIVATE_KEY')]:
        if Account.from_key(env[key]).address.lower()!=roles[role].lower():
            raise ValueError('SYSTEM_ROLE_MISMATCH')
    w3=evm_web3(Web3.HTTPProvider(args.rpc,request_kwargs={'timeout':20}))
    if w3.eth.chain_id!=43113 or w3.client_version.lower().startswith('anvil'):
        raise ValueError('PUBLIC_FUJI_REQUIRED')
    public={'environment':'REAL_FUJI_EXECUTION','chain_id':43113,'roles':roles,'transactions':[]}
    args.journal.mkdir(parents=True,exist_ok=True)

    def send(label,fn):
        path=args.journal/(label+'.json')
        if path.exists():
            entry=json.loads(path.read_text(encoding='utf-8'))
            if entry['sender'].lower()!=owner.address.lower():
                raise ValueError('JOURNAL_SENDER_MISMATCH')
            tx_hash=entry['tx_hash']
        else:
            estimate=fn.estimate_gas({'from':owner.address})
            price=w3.eth.gas_price
            gas=estimate*12//10+10000
            if price>5_000_000_000 or gas*price>10**16:
                raise ValueError('DEPLOYMENT_GAS_CAP_EXCEEDED')
            tx=fn.build_transaction({'from':owner.address,'nonce':w3.eth.get_transaction_count(owner.address,'pending'),
                'chainId':43113,'gas':gas,'gasPrice':price})
            if w3.eth.get_balance(owner.address)<gas*price:
                raise ValueError('OWNER_GAS_INSUFFICIENT')
            signed=owner.sign_transaction(tx)
            entry={'sender':owner.address,'tx_hash':Web3.to_hex(signed.hash),
                'raw_tx':Web3.to_hex(signed.raw_transaction),'nonce':tx['nonce']}
            atomic(path,entry)
            tx_hash=entry['tx_hash']
        try:
            w3.eth.get_transaction(tx_hash)
        except Exception:
            # Rebroadcast only the exact already journaled bytes, never a replacement.
            w3.eth.send_raw_transaction(Web3.to_bytes(hexstr=entry['raw_tx']))
        receipt=w3.eth.wait_for_transaction_receipt(tx_hash,timeout=90)
        if receipt.status!=1 or w3.eth.get_block(receipt.blockNumber).hash!=receipt.blockHash:
            raise ValueError('DEPLOYMENT_RECEIPT_FAILED')
        result={'label':label,'tx_hash':tx_hash,'block_number':receipt.blockNumber,
            'gas_used':receipt.gasUsed,'fee_wei':str(receipt.gasUsed*receipt.effectiveGasPrice),
            'contract_address':receipt.contractAddress,'status':receipt.status}
        atomic(path,{**entry,'receipt':result})
        public['transactions'].append(result)
        atomic(args.output,public)
        print(json.dumps(result),flush=True)
        return receipt

    def create(name,label,parameters):
        compiled=artifact(name)
        if len(compiled['deployedBytecode']['object'].removeprefix('0x'))//2>24576:
            raise ValueError('DEPLOYED_BYTECODE_SIZE_EXCEEDED')
        factory=w3.eth.contract(abi=compiled['abi'],bytecode=compiled['bytecode']['object'])
        receipt=send(label,factory.constructor(*parameters))
        return w3.eth.contract(address=receipt.contractAddress,abi=compiled['abi'])

    route=LFJClient(w3,old['token_in']).v1_route(w3.eth.block_number)
    vault=create('PolicyVaultMVP','01-deploy-vault',(owner.address,roles['attestor'],old['token_in'],old['token_out']))
    adapter=create('LFJSwapAdapterV3','02-deploy-adapter',(vault.address,route['lfj_router'],route['pair'],old['token_in'],old['token_out']))
    public.update(treasury=vault.address,adapter=adapter.address)
    previous=contract(w3,'PolicyVault',old['vault_address'])
    proof=list(previous.functions.proofPolicy().call())
    proof[0]=10**16
    send('03-allow-adapter',vault.functions.setRouter(adapter.address,True))
    send('04-proof-policy',vault.functions.configureProofPolicy(adapter.address,tuple(proof)))
    send('05-approval-ttl',vault.functions.setApprovalTtl(180))
    send('06-mvp-limits',vault.functions.configureMVP(100_000_000,500_000_000,10_000,1_000_000,2500))
    # The user explicitly authorized small test transfers among the three existing roles.
    for index,role in enumerate(['owner','attestor','relayer'],7):
        send(f'{index:02}-payee-{role}',vault.functions.setMvpPayee(roles[role],10_000,1_000_000,1_000_000))
    config_path=args.journal/'policy-window.json'
    if config_path.exists():
        window=json.loads(config_path.read_text(encoding='utf-8'))
    else:
        now=int(time.time())
        window={'start':now,'expires':now+604800,'policy_hash':content_hash({'MVP_PUBLIC_USER_AUTHORIZED':vault.address,'started':now}),
            'session_id':content_hash({'MVP_PUBLIC_SESSION':vault.address,'started':now})}
        atomic(config_path,window)
    send('10-activate-policy',vault.functions.configurePolicy(window['policy_hash'],1_000_000,10_000_000,
        previous.functions.maxSlippageBps().call(),window['expires']))
    send('11-create-session',vault.functions.createSession(window['session_id'],window['start'],window['expires'],proof[6]))
    send('12-authorize-two-operations',vault.functions.authorizeMvpSession(window['session_id'],3,300_000_000,1_000_000,500,0))
    token=contract(w3,'MockUSDC',old['token_in'])
    send('13-fund-one-test-usdc',token.functions.transfer(vault.address,1_000_000))
    if vault.functions.owner().call().lower()!=owner.address.lower() or not vault.functions.policyActive().call():
        raise ValueError('DEPLOYMENT_ACTIVATION_MISMATCH')
    ids={'treasury':vault.address,'adapter':adapter.address,'usdc':old['token_in'],'wavax':old['token_out']}
    manifest=MvpManifest(environment='REAL_FUJI_EXECUTION',chain_id=43113,**ids,**roles,
        default_session_id=window['session_id'],payee_candidates=tuple(roles.values()),
        code_hashes={name:Web3.to_hex(Web3.keccak(w3.eth.get_code(Web3.to_checksum_address(address)))) for name,address in ids.items()})
    manifest=manifest.model_copy(update={'owner_signature':Web3.to_hex(owner.sign_message(manifest.signing_message()).signature)})
    manifest.verify_owner()
    atomic(args.manifest,manifest.model_dump(mode='json'))
    public.update(session_id=window['session_id'],policy_expires_at=window['expires'],manifest_file=str(args.manifest.relative_to(ROOT)),
        total_gas_fee_wei=str(sum(int(tx['fee_wei']) for tx in public['transactions'])),
        funded_usdc_base_units='1000000',balances_after={role:{'avax_wei':str(w3.eth.get_balance(Web3.to_checksum_address(address))),
            'usdc_base_units':str(token.functions.balanceOf(Web3.to_checksum_address(address)).call())} for role,address in {**roles,'treasury':vault.address}.items()})
    atomic(args.output,public)
    print(json.dumps({'status':'DEPLOYED_AND_OWNER_SIGNED','treasury':vault.address,'adapter':adapter.address,
        'total_gas_fee_wei':public['total_gas_fee_wei'],'manifest':str(args.manifest)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--rpc',default='https://api.avax-test.network/ext/bc/C/rpc')
    parser.add_argument('--env',type=Path,default=ROOT/'.env')
    parser.add_argument('--journal',type=Path,default=ROOT/'data/mvp-public-deployment')
    parser.add_argument('--manifest',type=Path,default=ROOT/'deployments/mvp-fuji.json')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/audit/mvp-public-deployment-20261121.json')
    deploy(parser.parse_args())
