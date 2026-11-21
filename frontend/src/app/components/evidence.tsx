import {useState} from 'react';
import {Check, Copy, FileCheck2, LockKeyhole} from 'lucide-react';
import {Accordion, AccordionItem} from './ui/accordion';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from './ui/dialog';
import {Button} from './ui/button';
import {BlockReason} from './run-session';
import {date, environment, object, short, stage, text} from '@/lib/format';
import type {Evidence, Job} from '@/lib/types';
import {dictionary, type Language} from '@/lib/i18n';

export function CopyHash({value}: {value?: string}) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="text-slate-400">Unavailable</span>;
  return <span className="inline-flex items-center gap-1 font-mono text-xs"><span title={value}>{short(value)}</span><button className="rounded p-1 hover:bg-slate-100" aria-label="Copy full value" onClick={() => navigator.clipboard.writeText(value).then(() => setCopied(true)).catch(() => setCopied(false))}>{copied ? <Check size={12}/> : <Copy size={12}/>}</button></span>;
}
export function RawEvidence({value}: {value: unknown}) {
  return <pre className="evidence-json">{JSON.stringify(value ?? {status:'Unavailable'}, null, 2)}</pre>;
}
export function ProofSummary({evidence, language = 'en'}: {evidence?: Evidence; language?:Language}) {
  const vi = language === 'vi';
  const queries = Array.isArray(evidence?.queries) ? evidence.queries.map(object) : [];
  return <div><div className="flex items-center gap-2 mb-4"><FileCheck2 size={17} className="text-primary"/><span className="font-semibold text-foreground">{text(evidence?.status, vi ? 'Chưa xác minh' : 'Not verified')}</span><span className="text-xs">{vi ? 'Xác minh Z3 ngoài chuỗi' : 'Off-chain Z3 verification'}</span></div>
    {queries.length ? <div className="grid gap-2">{queries.map((query, index) => <div key={index} className="flex justify-between rounded-lg bg-slate-50 px-3 py-2"><span>{text(query.name)}</span><span className="font-mono text-xs font-semibold">{text(query.result)}</span></div>)}</div> : <p>{vi ? 'Chưa có kết quả solver cho lần chạy này.' : 'No solver query results are available for this run.'}</p>}
    <p className="mt-3 text-xs leading-relaxed">{vi ? 'SAT xác nhận các giả định có nghiệm; các phép kiểm tra vi phạm cần UNSAT. UNKNOWN không cấp quyền thực thi.' : 'SAT establishes satisfiable assumptions only. Violation checks require UNSAT. UNKNOWN never authorizes execution.'}</p>
  </div>;
}
export function EvidenceSections({job, language = 'en'}: {job?: Job; language?:Language}) {
  const vi = language === 'vi';
  const workflow = job?.workflow;
  const context = stage(workflow, 'OWNER_AUTHORITY');
  return <Accordion type="multiple" defaultValue={['policy']}>
    <AccordionItem value="policy" title={vi ? "Policy và quyền do Owner xác định" : "Owner-defined policy & permissions"}><RawEvidence value={context ? {policy_hash:context.policy_hash, policy_version:context.policy_version, proof_policy:context.proof_policy,
      payees:context.recipient_allowlist, session_id:context.session_id, authority:context.authority,
      tokens:context.token_allowlist, adapter:context.adapter, max_payment_usdc:context.max_payment_usdc,
      payment_spend_remaining_usdc:context.payment_spend_remaining_usdc, daily_payment_remaining_usdc:context.daily_payment_remaining_usdc,
      swap_spend_remaining:context.swap_spend_remaining, risk_remaining:context.risk_remaining, gas_budget:context.max_daily_execution_cost_usd_e8} : undefined}/></AccordionItem>
    <AccordionItem value="simulation" title={vi ? "Simulation, oracle và economic risk" : "Simulation, oracle & economic risk"}><RawEvidence value={{oracle:context?.oracle, build:stage(workflow,'BUILD'), simulation:stage(workflow,'SIMULATION'), risk:stage(workflow,'RISK')}}/></AccordionItem>
    <AccordionItem value="proof" title={vi ? "Xác minh Z3 và Phi đã ký" : "Z3 formal verification & signed Phi"}><ProofSummary language={language} evidence={stage(workflow,'PROOF')}/><details className="mt-4"><summary className="cursor-pointer text-primary">{vi ? 'Proof và constraints đầy đủ' : 'Full proof and constraints'}</summary><RawEvidence value={stage(workflow,'PROOF') ?? stage(workflow,'PROOF_REJECTION')}/></details></AccordionItem>
    <AccordionItem value="attestation" title={vi ? "Attestation và thực thi on-chain" : "Attestation & on-chain enforcement"}><RawEvidence value={{attestation:stage(workflow,'ATTESTATION'), exact_preflight:stage(workflow,'EXACT_SIGNED_PREFLIGHT'), receipt:workflow?.outcome}}/></AccordionItem>
    <AccordionItem value="alignment" title={vi ? "Task Shield, Temporal ITAG và quyết định bảo mật" : "Task Shield, Temporal ITAG & security decision"}><RawEvidence value={{proposal:stage(workflow,'AGENT_PROPOSAL'), itag:stage(workflow,'ITAG'), decision:stage(workflow,'SDE')}}/></AccordionItem>
  </Accordion>;
}
export function EvidenceDrawer({job, open, onOpenChange, language = 'en'}: {job?:Job; open:boolean; onOpenChange:(open:boolean)=>void; language?:Language}) {
  const t = dictionary[language], vi = language === 'vi';
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent>
    <p className="eyebrow mb-3"><LockKeyhole size={13}/> VERIFIABLE EXECUTION RECORD</p>
    <DialogTitle className="text-2xl font-semibold tracking-tight text-foreground">{vi ? 'Bằng chứng thực thi' : 'Workflow evidence'}</DialogTitle>
    <DialogDescription className="mt-2 mb-6 text-sm text-muted-foreground">{environment(job?.environment)} · {date(job?.created_at)}</DialogDescription>
    <div className="flex items-center justify-between rounded-xl border border-border bg-slate-50 p-4 mb-4"><span className="text-sm font-medium">Workflow ID</span><CopyHash value={job?.workflow?.workflow_id ?? job?.job_id}/></div>
    {job&&<BlockReason job={job} language={language}/>}<EvidenceSections job={job} language={language}/><details className="mt-5"><summary className="text-sm font-semibold cursor-pointer">{vi ? 'Intent và dòng thời gian sự kiện gốc' : 'Requested intent & raw event timeline'}</summary><RawEvidence value={{intent:job?.workflow?.intent, events:job?.workflow?.timeline}}/></details>
    <Button variant="outline" className="mt-6" onClick={() => onOpenChange(false)}>{t.close}</Button>
  </DialogContent></Dialog>;
}
