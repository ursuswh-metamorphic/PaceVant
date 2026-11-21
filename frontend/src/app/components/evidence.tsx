import {useState} from 'react';
import {Check, Copy, FileCheck2, LockKeyhole, ShieldCheck, ShieldAlert} from 'lucide-react';
import {Accordion, AccordionItem} from './ui/accordion';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from './ui/dialog';
import {Button} from './ui/button';
import {BlockReason} from './run-session';
import {date, environment, object, short, stage, text} from '@/lib/format';
import type {Evidence, Job} from '@/lib/types';
import {dictionary, type Language} from '@/lib/i18n';

export function CopyHash({value}: {value?: string}) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="hash-empty">Unavailable</span>;

  return (
    <span className="hash" translate="no">
      <span className="hash-value" title={value}>
        {short(value)}
      </span>
      <button
        type="button"
        className="hash-copy"
        aria-label={copied ? 'Copied' : 'Copy full value'}
        onClick={() =>
          navigator.clipboard
            .writeText(value)
            .then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1600);
            })
            .catch(() => setCopied(false))
        }
      >
        {copied ? <Check size={13} style={{color: 'var(--ok)'}} /> : <Copy size={13} />}
      </button>
    </span>
  );
}

export function RawEvidence({value}: {value: unknown}) {
  return (
    <pre className="evidence-json">
      {JSON.stringify(value ?? {status: 'Unavailable'}, null, 2)}
    </pre>
  );
}

export function ProofSummary({
  evidence,
  language = 'en',
}: {
  evidence?: Evidence;
  language?: Language;
}) {
  const vi = language === 'vi';
  const queries = Array.isArray(evidence?.queries) ? evidence.queries.map(object) : [];

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <FileCheck2 size={16} className="text-primary" />
        <span className="font-semibold text-slate-800 text-sm">
          {text(evidence?.status, vi ? 'Chưa xác minh' : 'Not verified')}
        </span>
        <span className="text-xs text-slate-500">
          {vi ? 'Xác minh hình thức Z3 ngoài chuỗi' : 'Off-chain Z3 formal verification'}
        </span>
      </div>

      {queries.length ? (
        <div className="grid gap-1.5">
          {queries.map((query, index) => (
            <div
              key={index}
              className="flex justify-between items-center rounded-lg bg-slate-50 border border-slate-100 px-3 py-2 text-xs"
            >
              <span className="text-slate-700 font-medium">{text(query.name)}</span>
              <span className="font-mono font-semibold text-primary">{text(query.result)}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-slate-500">
          {vi
            ? 'Chưa có kết quả solver cho lần chạy này.'
            : 'No solver query results are available for this run.'}
        </p>
      )}

      <p className="mt-3 text-xs leading-relaxed text-slate-500">
        {vi
          ? 'SAT xác nhận các giả định có nghiệm; các phép kiểm tra vi phạm cần UNSAT. UNKNOWN không cấp quyền thực thi.'
          : 'SAT establishes satisfiable assumptions only. Violation checks require UNSAT. UNKNOWN never authorizes execution.'}
      </p>
    </div>
  );
}

export function EvidenceSections({
  job,
  language = 'en',
}: {
  job?: Job;
  language?: Language;
}) {
  const vi = language === 'vi';
  const workflow = job?.workflow;
  const context = stage(workflow, 'OWNER_AUTHORITY');

  return (
    <Accordion type="multiple" defaultValue={['policy']}>
      <AccordionItem
        value="policy"
        title={vi ? '01. Policy và quyền do Owner xác định' : '01. Owner-defined policy & permissions'}
      >
        <RawEvidence
          value={
            context
              ? {
                  policy_hash: context.policy_hash,
                  policy_version: context.policy_version,
                  proof_policy: context.proof_policy,
                  payees: context.recipient_allowlist,
                  session_id: context.session_id,
                  authority: context.authority,
                  tokens: context.token_allowlist,
                  adapter: context.adapter,
                  max_payment_usdc: context.max_payment_usdc,
                  payment_spend_remaining_usdc: context.payment_spend_remaining_usdc,
                  daily_payment_remaining_usdc: context.daily_payment_remaining_usdc,
                  swap_spend_remaining: context.swap_spend_remaining,
                  risk_remaining: context.risk_remaining,
                  gas_budget: context.max_daily_execution_cost_usd_e8,
                }
              : undefined
          }
        />
      </AccordionItem>

      <AccordionItem
        value="simulation"
        title={vi ? '02. Simulation, Oracle và Economic Risk' : '02. Simulation, Oracle & Economic Risk'}
      >
        <RawEvidence
          value={{
            oracle: context?.oracle,
            build: stage(workflow, 'BUILD'),
            simulation: stage(workflow, 'SIMULATION'),
            risk: stage(workflow, 'RISK'),
          }}
        />
      </AccordionItem>

      <AccordionItem
        value="proof"
        title={vi ? '03. Xác minh Z3 và Phi đã ký' : '03. Z3 Formal Verification & Signed Phi'}
      >
        <ProofSummary language={language} evidence={stage(workflow, 'PROOF')} />
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-semibold text-primary hover:underline">
            {vi ? 'Xem proof và constraints đầy đủ' : 'View full proof and constraints'}
          </summary>
          <RawEvidence value={stage(workflow, 'PROOF') ?? stage(workflow, 'PROOF_REJECTION')} />
        </details>
      </AccordionItem>

      <AccordionItem
        value="attestation"
        title={vi ? '04. Attestation EIP-712 và thực thi on-chain' : '04. EIP-712 Attestation & Execution'}
      >
        <RawEvidence
          value={{
            attestation: stage(workflow, 'ATTESTATION'),
            exact_preflight: stage(workflow, 'EXACT_SIGNED_PREFLIGHT'),
            receipt: workflow?.outcome,
          }}
        />
      </AccordionItem>

      <AccordionItem
        value="alignment"
        title={
          vi
            ? '05. Task Shield, Temporal ITAG và quyết định SDE'
            : '05. Task Shield, Temporal ITAG & SDE Decision'
        }
      >
        <RawEvidence
          value={{
            proposal: stage(workflow, 'AGENT_PROPOSAL'),
            itag: stage(workflow, 'ITAG'),
            decision: stage(workflow, 'SDE'),
          }}
        />
      </AccordionItem>
    </Accordion>
  );
}

export function EvidenceDrawer({
  job,
  open,
  onOpenChange,
  language = 'en',
}: {
  job?: Job;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  language?: Language;
}) {
  const t = dictionary[language];
  const vi = language === 'vi';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="module-sheet evidence-sheet">
        <div className="p-6 pb-2">
          <span className="chip tone-running" style={{marginBottom: 10}}>
            <LockKeyhole size={12} aria-hidden="true" />
            {vi ? 'Bằng chứng kiểm toán' : 'Audit evidence'}
          </span>
          <DialogTitle className="text-xl font-bold tracking-tight text-slate-900">
            {vi ? 'Bằng chứng thực thi có thể kiểm chứng' : 'Verifiable Execution Record'}
          </DialogTitle>
          <DialogDescription className="mt-1 text-xs text-slate-500">
            {environment(job?.environment)} · {date(job?.created_at)}
          </DialogDescription>
        </div>

        <div className="evidence-sheet-body px-6 pb-6">
          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-3 mb-4">
            <span className="text-xs font-semibold text-slate-700">Workflow ID</span>
            <CopyHash value={job?.workflow?.workflow_id ?? job?.job_id} />
          </div>

          {job && <BlockReason job={job} language={language} />}

          <div className="mt-4">
            <EvidenceSections job={job} language={language} />
          </div>

          <details className="mt-4 pt-4 border-t border-slate-100">
            <summary className="text-xs font-semibold text-slate-600 cursor-pointer hover:text-primary">
              {vi ? 'Intent và dòng thời gian sự kiện gốc' : 'Requested intent & raw event timeline'}
            </summary>
            <RawEvidence
              value={{
                intent: job?.workflow?.intent,
                events: job?.workflow?.timeline,
              }}
            />
          </details>
        </div>

        <div className="evidence-sheet-foot">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t.close}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
