import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {RawEvidence} from '../components/evidence';
import {ExecutionStatus} from '../components/execution-panels';
import {Facts} from '../components/evidence-facts';
import {BindingChain, HistoricalProbeEvidence, ReceiptGas, RiskComparison} from '../components/security-evidence';
import {ResearchContent} from '../components/security-research';
import {bindingChain, riskChecks} from './security-evidence';
import type {Job} from './types';

const acceptance = JSON.parse(readFileSync(new URL('../../../../docs/audit/live-adversarial-20261121/acceptance.json', import.meta.url), 'utf8'));
const research = JSON.parse(readFileSync(new URL('../../../public/evidence/security-research.json', import.meta.url), 'utf8'));
const render = renderToStaticMarkup;
describe('source-bound security views', () => {
  it.each(acceptance.cases.map((entry: {job: Job}) => entry.job) as Job[])('shows the actual historical control, mutation and selectors ($attack)', (job: Job) => {
    const html = render(createElement(HistoricalProbeEvidence, {job, language: 'en'}));
    for (const field of ['seed_tx_hash', 'expected_selector', 'observed_selector', 'field', 'original', 'candidate']) expect(html).toContain(String(job.attack_evidence![field]));
    expect(html).toContain('HISTORICAL FUJI ETH_CALL');
    expect(html).toContain('Expected revert matched; control succeeded');
    if (job.attack_evidence?.expected_error === 'BadSignature()') expect(html).toContain('does not establish AI attack detection');
  });
  it('an unavailable RPC or failed control cannot become a passing probe', () => {
    const job: Job = {...acceptance.cases[0].job, status: 'UNAVAILABLE', attack_evidence: {control: 'UNAVAILABLE', expected_selector: '0x1234'}};
    const html = render(createElement(HistoricalProbeEvidence, {job, language: 'en'}));
    expect(html).not.toContain('Expected revert matched; control succeeded');
    expect(html).toContain('Test result not fully verified');
  });
  it.each(['0', '41050', '43783680', undefined, 'bad'])('uses one gas formatter in summary, evidence facts and receipt (%s)', cost => {
    const job: Job = structuredClone(acceptance.normal[0].job);
    job.workflow!.outcome!.system_gas_expense = {actual_cost_wei: cost as string};
    const summary = render(createElement(ExecutionStatus, {job, language: 'en', onEvidence: () => {}}));
    const facts = render(createElement(Facts, {value: cost ?? null, language: 'en', field: 'actual_cost_wei'}));
    const receipt = render(createElement(ReceiptGas, {job, language: 'en'}));
    const value = cost === '0' ? '0 AVAX' : cost === '41050' ? '0.00000000000004105 AVAX' : cost === '43783680' ? '0.00000000004378368 AVAX' : 'Unavailable';
    for (const html of [summary, facts, receipt]) expect(html).toContain(value);
  });
  it('does not use simulated gas as actual receipt expense', () => {
    const job: Job = structuredClone(acceptance.normal[0].job);
    delete job.workflow!.outcome!.system_gas_expense;
    expect(render(createElement(ReceiptGas, {job, language: 'en'}))).toContain('Unavailable');
  });
  it('never infers receipt bindings from a confirmed label alone', () => {
    const job: Job = structuredClone(acceptance.normal[0].job);
    expect(bindingChain(job).map(link => link.state)).toEqual(Array(6).fill('match'));
    job.workflow!.activity = [];
    expect(bindingChain(job).slice(-2).map(link => link.state)).toEqual(['missing', 'missing']);
    const html = render(createElement(BindingChain, {language: 'en'}));
    expect(html.match(/Missing comparison evidence/g)).toHaveLength(6);
  });
  it('shows only sourced risk comparisons and an explicit empty state', () => {
    const job: Job = acceptance.normal[0].job;
    expect(riskChecks(job)).toHaveLength(7);
    expect(riskChecks(job).every(check => check.expected != null && check.observed != null)).toBe(true);
    expect(render(createElement(RiskComparison, {language: 'en'}))).toContain('No expected / observed comparison is recorded');
  });
  it('never leaks signing capability through raw views', () => {
    const html = render(createElement(RawEvidence, {value: {signature: 'secret-marker', signed_transaction: 'secret-marker', nested: {private_key: 'secret-marker'}, proof_hash: 'public-marker'}}));
    expect(html).not.toContain('secret-marker'); expect(html).toContain('public-marker');
  });
  it.each(['vi', 'en'] as const)('renders both research mechanisms with scope, metrics and caveats (%s)', language => {
    const html = render(createElement(ResearchContent, {data: research, language}));
    for (const text of ['LOCAL ANVIL', 'SCRIPTED EVALUATION', 'REAL-MODEL RESEARCH', '95.67%', '8/12', '12/12', '7/8', '16/19', 'MISALIGNED', '30 USDC']) expect(html).toContain(text);
    expect(research.budget.steps.map((step: {signed: boolean}) => step.signed)).toEqual([true, true, false]);
    expect(research.purpose.sde.hybrid).toBe('REJECT');
  });
  it('does not present the fixed narrative for absent or inconsistent research records', () => {
    for (const data of [{}, {...research, version: 2}, {...research, budget: {steps: []}}]) {
      const html = render(createElement(ResearchContent, {data, language: 'en'}));
      expect(html).toContain('Research results cannot be verified');
      expect(html).not.toContain('7/8');
      expect(html).not.toContain('30 USDC');
    }
  });
});
