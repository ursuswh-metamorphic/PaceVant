import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,expect,it} from 'vitest';
import {StageDetail} from '../components/stage-detail';
import {nodeState} from '../components/pipeline';
import {workflowNodes} from './workflow-nodes';
import type {Job} from './types';

const workflow=JSON.parse(readFileSync(new URL('../../../../fixtures/judge/payment.json',import.meta.url),'utf-8'));
const job:Job={job_id:'recorded-test',scenario:'payment',status:'CONFIRMED',created_at:workflow.created_at,environment:'VERIFIED_REPLAY',workflow,terminal:true,public_chain_broadcast:false};
describe('readable real stage evidence',()=>{
 it('shows no data before a stage has evidence',()=>{
   expect(renderToStaticMarkup(createElement(StageDetail,{index:0,events:['AGENT_PROPOSAL'],language:'vi'}))).toBe('');
   expect(renderToStaticMarkup(createElement(StageDetail,{job:{...job,workflow:{...workflow,timeline:[]}},index:0,events:['AGENT_PROPOSAL'],language:'vi'}))).toBe('');
 });
 it('shows the recorded objective and structured intent without JSON',()=>{
   const html=renderToStaticMarkup(createElement(StageDetail,{job,index:0,events:['AGENT_PROPOSAL'],language:'vi'}));
   expect(html).toContain(workflow.intent.objective);
   expect(html).toContain('0.01 USDC');
   expect(html).toContain('Người nhận');
   expect(html).not.toContain('<pre');
 });
 it('shows measured USDC and WAVAX balances',()=>{
   const html=renderToStaticMarkup(createElement(StageDetail,{job,index:3,events:['SIMULATION'],language:'vi'}));
   expect(html).toContain('Số dư trước mô phỏng');
   expect(html).toContain('USDC');
   expect(html).toContain('Gas đã sử dụng');
 });
 it('keeps unknown and interrupted stages uncertain',()=>{
   const pending={...job,status:'UNKNOWN' as const,active_stage:'EXACT_SIGNED_PREFLIGHT',workflow:{...workflow,timeline:[],outcome:undefined}};
   const preflight=workflowNodes.findIndex(node=>node.events.includes('EXACT_SIGNED_PREFLIGHT'));
   expect(nodeState(pending,preflight)).toBe('unknown');
   expect(nodeState({...pending,status:'INTERRUPTED'},preflight)).toBe('unknown');
 });
});
