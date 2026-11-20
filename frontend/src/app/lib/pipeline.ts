import type {Job} from './types';
import {stage, text} from './format';

export type GateState = 'pending' | 'running' | 'passed' | 'rejected' | 'failed' | 'unknown' | 'skipped';
export const GATES = [
  {id:'proposal', label:'AI proposal', detail:'Bounded intent & trusted builder', events:['AGENT_PROPOSAL', 'BUILD'], active:['PLANNING', 'BUILD']},
  {id:'alignment', label:'Task Shield & ITAG', detail:'Authority, alignment & temporal intent', events:['ITAG'], active:['ITAG']},
  {id:'simulation', label:'EVM simulation', detail:'Pinned state & measured balance effects', events:['SIMULATION'], active:['SIMULATION', 'EXACT_SIGNED_PREFLIGHT']},
  {id:'proof', label:'Economic risk & Z3', detail:'Loss bounds, proof & security decision', events:['RISK', 'PROOF', 'SDE'], active:['RISK', 'PROOF', 'SDE']},
  {id:'attestation', label:'EIP-712 attestation', detail:'Signed intent, nonce & compiled Phi', events:['ATTESTATION'], active:['ATTESTATION']},
  {id:'execution', label:'Isolated fork execution', detail:'Guarded vault call & atomic enforcement', events:['OUTCOME'], active:['RELAY']},
  {id:'receipt', label:'Receipt verification', detail:'Actual effects & system gas reconciliation', events:['OUTCOME'], active:[]},
];
export function gateStates(job?: Job): GateState[] {
  if (!job?.workflow) return GATES.map(() => 'pending');
  const workflow = job.workflow;
  return GATES.map(gate => {
    if (gate.id === 'execution' || gate.id === 'receipt') {
      if (workflow.outcome?.status === 'CONFIRMED') return 'passed';
      if (workflow.outcome?.status === 'REVERTED') return gate.id === 'execution' ? 'rejected' : 'passed';
      if (workflow.outcome) return 'unknown';
    }
    if (gate.id === 'alignment' && stage(workflow, 'ITAG') && text(stage(workflow, 'ITAG')?.verdict) !== 'PASS') return 'rejected';
    if (gate.id === 'proof' && (stage(workflow,'RISK')?.result === 'FAIL' || stage(workflow,'SDE')?.verdict === 'REJECT' || stage(workflow,'PROOF_REJECTION'))) return 'rejected';
    const completed = gate.events.every(name => stage(workflow, name));
    if (completed) return 'passed';
    if (gate.active.includes(job.active_stage ?? '')) {
      if (job.status === 'REJECTED') return 'rejected';
      if (job.status === 'FAILED' || job.status === 'UNAVAILABLE') return 'failed';
      if (job.status === 'UNKNOWN' || job.status === 'INTERRUPTED') return 'unknown';
      return 'running';
    }
    return job.terminal ? 'skipped' : 'pending';
  });
}
