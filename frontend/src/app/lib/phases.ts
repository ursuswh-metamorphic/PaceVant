import type {Job} from './types';
import {workflowNodes, workflowNodeState, type ModuleState} from './workflow-nodes';

/*
 * Presentation-only grouping of the existing workflow nodes into their three
 * phases. States are always derived from workflowNodeState; nothing here can
 * advance a node on its own.
 */
export const PHASES = [
  {
    title: ['Chuẩn bị', 'Preparation'],
    description: [
      'Đọc policy, nhận đề xuất của AI và dựng giao dịch chính xác.',
      'Read policy, take the AI proposal and build the exact transaction.',
    ],
  },
  {
    title: ['Xác minh', 'Verification'],
    description: [
      'Mô phỏng EVM, giới hạn rủi ro, đối chiếu ý định và chứng minh bằng Z3.',
      'Simulate in the EVM, bound risk, check intent and prove with Z3.',
    ],
  },
  {
    title: ['Thực thi', 'Execution'],
    description: [
      'Quyết định, ký EIP-712, kiểm tra lại và thực thi qua PolicyVault.',
      'Decide, sign EIP-712, recheck and enforce through PolicyVault.',
    ],
  },
] as const;

export function phaseMembers(phase: number) {
  return workflowNodes.map((node, index) => (node.phase === phase ? index : -1)).filter(index => index >= 0);
}

export function summarizePhase(states: ModuleState[], terminal: boolean): ModuleState {
  if (states.includes('rejected')) return 'rejected';
  if (states.includes('failed')) return 'failed';
  if (states.includes('unknown')) return 'unknown';
  if (states.includes('running')) return 'running';
  if (states.every(state => state === 'passed')) return 'passed';
  if (states.some(state => state === 'passed')) return terminal ? 'skipped' : 'running';
  if (states.every(state => state === 'skipped')) return 'skipped';
  return 'idle';
}

export function workflowProgress(job?: Job) {
  const states = workflowNodes.map((_, index) => workflowNodeState(job, index));
  const terminal = !!job?.terminal;
  const phases = PHASES.map((_, phase) => summarizePhase(phaseMembers(phase).map(index => states[index]), terminal));
  const passed = states.filter(state => state === 'passed').length;
  return {states, phases, passed, total: states.length};
}
