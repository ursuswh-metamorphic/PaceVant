import {describe, expect, it} from 'vitest';
import {presetsFor} from '../components/attack-select';
import {beginAttempt, loadAttempt} from './recovery';
import {workflowEdgeState, workflowNodeState} from './workflow-nodes';
import type {Job} from './types';

function storage(): Storage {
  const values = new Map<string, string>();
  return {length: 0, clear: () => values.clear(), key: () => null,
    getItem: key => values.get(key) ?? null, setItem: (key, value) => {values.set(key, value);},
    removeItem: key => {values.delete(key);}};
}

describe('adversarial demo requests', () => {
  it('colors only fully verified connections green and preserves warning/error states', () => {
    expect(workflowEdgeState('passed', 'skipped')).toBe('idle');
    expect(workflowEdgeState('passed', 'passed')).toBe('passed');
    expect(workflowEdgeState('passed', 'rejected')).toBe('rejected');
    expect(workflowEdgeState('passed', 'unknown')).toBe('unknown');
    expect(workflowEdgeState('passed', 'running')).toBe('running');
  });
  it('uses warning rather than passed/blocked for an unavailable source before planning', () => {
    const job: Job = {job_id: 'source', scenario: 'swap', status: 'UNAVAILABLE', created_at: 1,
      environment: 'REAL_FUJI_EXECUTION', terminal: true, public_chain_broadcast: false};
    expect(workflowNodeState(job, 0)).toBe('unknown');
    for (let index = 1; index < 12; index++) expect(workflowNodeState(job, index)).toBe('skipped');
  });
  it('shows a rejected contract call as blocked even though its evidence event exists', () => {
    const job: Job = {job_id: 'probe', scenario: 'payment', attack: 'payment-replay', status: 'REJECTED',
      created_at: 1, environment: 'REAL_FUJI_EXECUTION', terminal: true, public_chain_broadcast: false,
      active_stage: 'EXACT_SIGNED_PREFLIGHT', workflow: {workflow_id: 'probe', status: 'REJECTED', created_at: 1,
        intent: {operation: 'TOKEN_PAYMENT', amount: '10000', token_in: 'u', token_out: 'u', recipient: 'r', treasury: 'v', objective: 'probe', deadline: 1, session_id: 's', chain_id: 43113},
        timeline: [{stage: 'EXACT_SIGNED_PREFLIGHT', created_at: 1, evidence: {observed_selector: '0x6aa319b1'}}]}};
    expect(workflowNodeState(job, 9)).toBe('rejected');
    expect(workflowNodeState(job, 1)).toBe('skipped');
    expect(workflowNodeState(job, 10)).toBe('skipped');
  });
  it('exposes exactly two tests for each financial operation', () => {
    expect(presetsFor('payment').map(item => item.id)).toEqual(['payment-amount', 'payment-replay']);
    expect(presetsFor('swap').map(item => item.id)).toEqual(['swap-slippage', 'swap-route']);
  });
  it('retains the original attack and request key across interrupted responses', () => {
    const saved = storage();
    const first = beginAttempt('payment', saved, 'payment-replay');
    expect(loadAttempt(saved)?.body.attack).toBe('payment-replay');
    expect(beginAttempt('swap', saved, 'swap-route')).toEqual(first);
    expect(JSON.parse(saved.getItem('pacevant.judge.attempt.v1')!).body).toEqual({scenario: 'payment', attack: 'payment-replay'});
  });
});
