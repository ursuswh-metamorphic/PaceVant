"""Summarize measured judge results; estimates never alter execution or approval."""
import argparse
import json
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def summarize(directory):
    report = json.loads((directory / 'report.json').read_text(encoding='utf-8'))
    result = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'acceptance_status': report['status'],
        'public_chain_writes': False,
        'browser_errors': report['errors'],
        'ui_checks': report['checks'],
        'cost_basis': {
            'source': 'https://api-docs.deepseek.com/quick_start/pricing/',
            'verified_on': '2026-11-21',
            'model': 'deepseek-flash',
            'off_peak_usd_per_million': {'cached_input':0.003,'uncached_input':0.15,'output':0.6},
            'peak_multiplier': 2,
            'note': 'Range for successful reported tokens only; cache split is not recorded. Not an invoice. VPS and RPC subscription costs are excluded.',
        },
        'measurement_limits': [
            'Browser timing starts with the accepted job response; waiting for a fresh source before clicking is excluded.',
            'Guard is submitted through the existing backend API, not a visible attack-preview option.',
            'Fork setup contains ten tracked deployment/configuration transactions; funding, RPC reads and nested simulation fees are not included.',
            'Successful reported token usage is metered across planning and security calls. Provider invoice and unreported/failed-attempt charges are unknown.',
            'Test sample is not a 24/7 availability, statistical reliability or production VPS acceptance guarantee.',
        ],
        'runs': [],
    }
    for run in report['runs']:
        job = json.loads((directory / (run['scenario']+'-job.json')).read_text(encoding='utf-8'))
        workflow = job.get('workflow', {})
        metrics = job.get('runtime_metrics', {})
        inference = metrics.get('inference', {})
        tokens = inference.get('reported_token_usage', {})
        calls = inference.get('calls', [])
        outcomes = [entry for entry in workflow.get('timeline', []) if entry['stage']=='OUTCOME']
        outcome = workflow.get('outcome') or (outcomes[-1]['evidence'] if outcomes else {})
        observed = [item['observed_at'] for item in report['observations'] if item['job_id']==job['job_id']]
        provider_models = {attempt.get('model') for call in calls for attempt in call['attempts'] if attempt.get('status')=='SUCCESS'}
        rates = [Decimal('0.003'),Decimal('0.15'),Decimal('0.6')]
        estimate = None
        if provider_models == {'deepseek-flash'} and tokens:
            p, c = Decimal(tokens.get('prompt_tokens',0)),Decimal(tokens.get('completion_tokens',0))
            estimate = {'off_peak_min_usd':str((p*rates[0]+c*rates[2])/10**6),
                'off_peak_max_usd':str((p*rates[1]+c*rates[2])/10**6),
                'peak_min_usd':str((p*rates[0]+c*rates[2])*2/10**6),
                'peak_max_usd':str((p*rates[1]+c*rates[2])*2/10**6),
                'test_tariff': 'off_peak' if datetime.fromtimestamp(job['created_at'],timezone.utc).weekday()>=5 else 'consult UTC schedule'}
        per_stage={}
        for call in calls:
            entry=per_stage.setdefault(call['stage'],{'calls':0,'wall_ms':0,'reported_tokens':0})
            entry['calls']+=1
            entry['wall_ms']+=call['wall_ms']
            entry['reported_tokens']+=call['usage'].get('total_tokens',0)
        fee=outcome.get('system_gas_expense',{}).get('actual_cost_wei')
        result['runs'].append({
            'scenario':run['scenario'],'job_id':job['job_id'],
            'surface':run.get('surface','Live Demo button'),
            'status':job['status'],'reason_code':job.get('reason_code'),
            'active_stage':job.get('active_stage'),'source_block':job.get('source_block'),
            'environment':job['environment'],'public_chain_broadcast':job['public_chain_broadcast'],
            'worker_wall_seconds':metrics.get('worker_wall_seconds'),
            'browser_observed_seconds':round(observed[-1]-observed[0],3) if observed else None,
            'median_poll_seconds':round(statistics.median(b-a for a,b in zip(observed,observed[1:],strict=False)),3) if len(observed)>1 else None,
            'ui_verification':{k:run[k] for k in ['reload_recovered','completed_refresh_restored','ai_panel_data_matched','post_count','modules','displayed_reason'] if k in run},
            'stages':run['stages'],'inference_calls':inference.get('call_count'),
            'reported_token_usage':tokens,'inference_stage_measurements':per_stage,
            'estimated_model_cost_for_reported_tokens':estimate,
            'model_billing_usd':None,
            'fork_execution_gas_used':outcome.get('gas_used'),
            'fork_execution_fee_avax':str(Decimal(fee)/10**18) if fee is not None else None,
            'fork_setup':metrics.get('fork_setup'),
            'public_network_fee_avax':'0',
            'outcome':outcome or None,
        })
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,default=ROOT/'data/judge-mvp-final')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/audit/judge-mvp-final-20261121.json')
    args=parser.parse_args()
    value=summarize(args.directory)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([{k:row[k] for k in ['scenario','status','worker_wall_seconds','reported_token_usage','estimated_model_cost_for_reported_tokens','fork_execution_fee_avax']} for row in value['runs']],indent=2))
