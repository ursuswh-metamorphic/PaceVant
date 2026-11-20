"""Export an existing real fork workflow as labeled, hash-pinned recorded evidence."""

import argparse
import hashlib
import json
from pathlib import Path

from treasury_backend.paths import ROOT


def export(source, scenario):
    value = json.loads(source.read_text(encoding="utf-8"))
    workflow = value.get("workflow",value)
    events = {item['stage']:item['evidence'] for item in workflow.get('timeline',[])}
    if workflow.get('status') == 'CONFIRMED':
        outcome = workflow.get('outcome',{})
        if (outcome.get('environment')!='ANVIL_FORK' or outcome.get('public_chain_receipt') is not False
                or events.get('PROOF',{}).get('status')!='VERIFIED'
                or events.get('EXACT_SIGNED_PREFLIGHT',{}).get('exact_signed_preflight') is not True):
            raise ValueError('RECORDED_SUCCESS_NOT_VERIFIED')
    elif workflow.get('status')!='REJECTED' or not workflow.get('reason_code'):
        raise ValueError('RECORDED_RESULT_NOT_VERIFIED')
    workflow.pop('signed_approval',None)
    text = json.dumps(workflow,indent=2)+'\n'
    if any(name in text.lower() for name in ('private_key','raw_tx','mnemonic','bearer ')):
        raise ValueError('SENSITIVE_EVIDENCE_NOT_EXPORTABLE')
    directory=ROOT/'fixtures/judge'
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/(scenario+'.json')
    path.write_text(text,encoding='utf-8')
    index=directory/'manifest.json'
    manifest=json.loads(index.read_text()) if index.exists() else {}
    manifest[scenario]={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'recorded_at':workflow['created_at'],'source_environment':'ANVIL_FORK',
                        'active_stage':value.get('active_stage'),
                        'public_chain_broadcast':False}
    index.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--scenario',choices=['payment','swap','guard'],required=True)
    args=p.parse_args()
    export(args.source,args.scenario)
    print(json.dumps({'scenario':args.scenario,'mode':'VERIFIED_REPLAY','exported':True}))


if __name__=='__main__':
    main()
