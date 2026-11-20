import {motion, useReducedMotion} from 'motion/react';
import {CircleCheck, ShieldX, Clock3, ExternalLink, FileText, CircleAlert} from 'lucide-react';
import type {Job} from '@/lib/types';
import {environment, publicExplorer, reason, stage, text, units} from '@/lib/format';
import {Button} from './ui/button';
import {CopyHash} from './evidence';

export function Result({job, onEvidence}: {job?:Job; onEvidence:()=>void}) {
  const reduced = useReducedMotion();
  if (!job) return <div className="empty-result"><ShieldX size={18}/><p>No transaction has been requested.<br/><span>Choose a scenario to see the security pipeline in action.</span></p></div>;
  const success = job.status === 'CONFIRMED', rejected = job.status === 'REJECTED', waiting = !job.terminal;
  const Icon = success ? CircleCheck : rejected ? ShieldX : waiting ? Clock3 : CircleAlert;
  const outcome = job.workflow?.outcome;
  const title = waiting ? (job.phase === 'WAITING_FOR_ORACLE' ? 'Waiting for a fresh Chainlink round' : job.phase === 'PREPARING_FORK' ? 'Preparing an isolated Fuji fork' : 'Evaluating the requested transaction')
    : success ? (job.environment === 'VERIFIED_REPLAY' ? 'Recorded fork confirmation' : job.environment === 'LOCAL_TEST' ? 'Local execution confirmed' : 'Fork execution confirmed')
    : rejected ? 'Rejected by security policy' : job.status === 'UNKNOWN' ? 'Outcome not verified' : 'Live verification unavailable';
  const explorer = publicExplorer(job);
  return <motion.section key={job.job_id + job.status} initial={reduced ? false : {opacity:0,y:6}} animate={{opacity:1,y:0}} transition={{duration:.2}}
    className={'result-panel ' + (success ? 'result-success' : rejected ? 'result-rejected' : 'result-pending')} data-testid="execution-result" aria-live="polite">
    <div className="flex items-start gap-3"><span className="mt-0.5"><Icon size={20}/></span><div className="min-w-0 flex-1"><h3 className="font-semibold text-sm">{title}</h3><p className="mt-1 text-xs leading-relaxed">{job.reason_code ? reason(job.reason_code) : waiting ? 'Progress comes from real backend events. Closing this tab does not create another transaction.' : `${environment(job.environment)} · ${job.environment === 'VERIFIED_REPLAY' ? 'Recorded evidence. No new execution.' : 'No public treasury assets were spent.'}`}</p></div></div>
    {job.terminal && <>
      {job.reason_code && <p className="mt-2 font-mono text-xs" data-testid="reason-code">{job.reason_code}</p>}
      {outcome && <div className="result-facts"><div><span>Actual receipt / output</span><strong>{outcome.payee_received && outcome.payee_received !== '0' ? units(outcome.payee_received) + ' USDC' : outcome.actual_deltas?.[1] ? units(outcome.actual_deltas[1],18,8) + ' WAVAX' : 'Unavailable'}</strong></div>
        <div><span>Gas consumed</span><strong>{outcome.gas_used ? Number(outcome.gas_used).toLocaleString() + ' gas' : 'Unavailable'}</strong></div>
        <div><span>Economic risk debit</span><strong>{stage(job.workflow,'PROOF') ? units(text(stage(job.workflow,'PROOF')?.risk_debit_usd_e8),8,4) + ' USD ref.' : 'Not certified'}</strong></div></div>}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><span className="text-xs">{outcome ? <CopyHash value={outcome.tx_hash}/> : 'No verified workflow transaction receipt'}</span><div className="flex gap-2">{explorer && <a href={explorer} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs">View on Fuji <ExternalLink size={12}/></a>}<Button variant="ghost" size="sm" onClick={onEvidence}><FileText size={13}/>View evidence</Button></div></div>
    </>}
  </motion.section>;
}
