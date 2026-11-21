import {object, stage} from './format';
import type {Evidence, Job, Json} from './types';
import type {Language} from './i18n';

export type BindingState = 'match' | 'mismatch' | 'missing';
export function compareBinding(expected: unknown, observed: unknown): BindingState {
  if (typeof expected !== 'string' || typeof observed !== 'string' || !expected || !observed) return 'missing';
  return expected === observed ? 'match' : 'mismatch';
}
export function evidenceScope(job?: Job): string {
  if (!job) return 'EVIDENCE NOT AVAILABLE';
  if (job.execution_kind === 'HISTORICAL_ETH_CALL' || job.attack_evidence?.method === 'eth_call') return 'HISTORICAL FUJI ETH_CALL';
  const recorded = job.environment === 'VERIFIED_REPLAY';
  const environment = recorded ? job.workflow?.environment ?? job.workflow?.outcome?.environment : job.environment;
  const label = environment === 'REAL_FUJI_EXECUTION' ? 'PUBLIC FUJI EXECUTION'
    : environment === 'LOCAL_TEST' || environment === 'ANVIL_FORK' ? 'LOCAL ANVIL'
    : job.semantic_scope?.includes('SCRIPTED') ? 'SCRIPTED EVALUATION' : 'SCOPE NOT VERIFIED';
  return (recorded ? 'RECORDED · ' : '') + label;
}
export function publicEvidence(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(publicEvidence);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([key, entry]) =>
    key === 'same_original_signature' && typeof entry === 'boolean' || !/private.?key|secret|password|api.?key|credential|raw.?tx|raw.?transaction|signature|signed.?transaction|signed.?pdr/i.test(key),
  ).map(([key, entry]) => [key, publicEvidence(entry)]));
  return value;
}
export function riskChecks(job?: Job) {
  return (job?.workflow?.activity ?? []).filter(event => event.stage === 'RISK' && event.kind === 'check' && event.expected != null && event.observed != null)
    .filter((event, index, rows) => !rows.slice(index + 1).some(other => other.check_id === event.check_id && other.check_ref === event.check_ref));
}
export function bindingChain(job?: Job) {
  const proof = stage(job?.workflow, 'PROOF'), attestation = stage(job?.workflow, 'ATTESTATION');
  const signed = object(attestation?.signed_fields);
  const simulation = stage(job?.workflow, 'SIMULATION');
  const receipt = job?.workflow?.activity?.filter(event => event.check_id === 'VAULT_EFFECTS' && event.status === 'PASS').at(-1);
  const receiptEvidence = job?.workflow?.outcome?.status === 'CONFIRMED' ? object(receipt?.observed) : {};
  return [
    {id: 'intent', labels: ['Ý định', 'Intent'], expected: proof?.intent_hash, observed: signed.intentHash, raw: {proof: proof?.intent_hash, signed: signed.intentHash}},
    {id: 'simulation', labels: ['Bằng chứng mô phỏng', 'Simulation evidence'], expected: proof?.evidence_root, observed: signed.evidenceRoot, raw: {proof: proof?.evidence_root, signed: signed.evidenceRoot, source_block_hash: simulation?.source_block_hash}},
    {id: 'proof', labels: ['Z3 Proof / Φ', 'Z3 Proof / Φ'], expected: proof?.phi_hash, observed: attestation?.constraints_hash, raw: {proof_hash: proof?.proof_hash, phi_hash: proof?.phi_hash, signed_constraints_hash: attestation?.constraints_hash}},
    {id: 'pdr', labels: ['PDR đã ký', 'Signed PDR'], expected: proof?.proof_hash, observed: signed.proofContextHash, raw: {proof_hash: proof?.proof_hash, signed_proof_hash: signed.proofContextHash, typed_data_hash: attestation?.typed_data_hash, nonce: signed.nonce}},
    {id: 'vault', labels: ['PolicyVault', 'PolicyVault'], expected: proof?.evidence_root, observed: receiptEvidence.evidence_root, raw: {expected: proof?.evidence_root, contract_event: receiptEvidence.evidence_root, tx_hash: job?.workflow?.outcome?.tx_hash}},
    {id: 'receipt', labels: ['Biên nhận', 'Receipt'], expected: proof?.proof_hash, observed: receiptEvidence.proof_hash, raw: {expected: proof?.proof_hash, contract_event: receiptEvidence.proof_hash, outcome: job?.workflow?.outcome}},
  ].map(link => ({...link, state: compareBinding(link.expected, link.observed)}));
}
export function bindingLabel(state: BindingState, language: Language) {
  return ({match: ['Khớp bằng chứng', 'Evidence matches'], mismatch: ['Không khớp — cần kiểm tra', 'Mismatch — inspect evidence'], missing: ['Chưa đủ trường để đối chiếu', 'Missing comparison evidence']} as const)[state][language === 'vi' ? 0 : 1];
}
export function graphRecords(graph?: Evidence) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes.map(object).filter(node => typeof node.node_id === 'string') : [];
  const ids = new Set(nodes.map(node => node.node_id));
  const sourceEdges = Array.isArray(graph?.edges) ? graph.edges.map(object) : [];
  const edges = sourceEdges.filter(edge => typeof edge.source === 'string' && typeof edge.target === 'string' && ids.has(edge.source) && ids.has(edge.target));
  return {nodes, edges, invalidEdges: sourceEdges.length - edges.length};
}
/** Only the versioned, source-bound showcase may carry its fixed research narrative. */
export function researchArtifactAvailable(value: Evidence): boolean {
  const budget = object(value.budget), purpose = object(value.purpose);
  const steps = Array.isArray(budget.steps) ? budget.steps.map(object) : [];
  const hasSource = (section: Evidence) => /^[a-f0-9]{64}$/.test(String(object(section.source).sha256 ?? ''));
  return value.version === 1 && hasSource(budget) && hasSource(purpose)
    && purpose.id === 'lh002' && purpose.repetition === 1 && purpose.deterministic === 'PASS'
    && purpose.semantic === 'MISALIGNED' && object(purpose.sde).hybrid === 'REJECT'
    && steps.length === 3 && steps.every((step, i) => step.budget === '20000000'
      && object(step.candidate).amount_in_base_units === '10000000'
      && object(step.deterministic).spent === ['0', '10000000', '20000000'][i]
      && step.signed === (i < 2) && Array.isArray(object(step.graph).nodes))
    && Array.isArray(object(purpose.graph).nodes);
}
export const evidenceObject = (value: unknown) => publicEvidence(value) as Json;
