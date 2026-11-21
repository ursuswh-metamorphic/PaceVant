import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,expect,it} from 'vitest';
import {StageDetail} from '../components/stage-detail';
import {Facts} from '../components/evidence-facts';
import {latestChecks,stepInputs} from './module-evidence';
import {workflowNodes,workflowNodeState,nodeTitle} from './workflow-nodes';
import {stage} from './format';
import type {ActivityEvent,Job} from './types';

const workflow=JSON.parse(readFileSync(new URL('../../../../fixtures/judge/payment.json',import.meta.url),'utf-8'));
const base:Job={job_id:'evidence-test',scenario:'payment',status:'CONFIRMED',created_at:workflow.created_at,environment:'VERIFIED_REPLAY',workflow,terminal:true,public_chain_broadcast:false};
const render=(job:Job,index:number)=>renderToStaticMarkup(createElement(StageDetail,{job,index,events:workflowNodes[index].events,language:'vi'}));
describe('observable security modules',()=>{
 it('retains useful inputs while Attestor is running and has no output',()=>{
  const job:Job={...base,status:'RUNNING',terminal:false,active_stage:'ATTESTATION',workflow:{...workflow,outcome:undefined,timeline:workflow.timeline.filter((e:{stage:string})=>!['ATTESTATION','EXACT_SIGNED_PREFLIGHT','OUTCOME'].includes(e.stage))}};
  const html=render(job,8);
  expect(stepInputs(job,8).map(x=>x.source)).toContain('SDE');
  expect(html).toContain('Đầu vào và nguồn dữ liệu');
  expect(html).toContain('Chưa có đầu ra');
  expect(html).not.toContain('Đã xác nhận');
 });
 it('shows actual ITAG nodes and trust sources without fabricating edges',()=>{
  const html=render(base,5);
  expect(html).toContain('Đồ thị ý định và nguồn gốc bằng chứng');
  expect(html).toContain('Yêu cầu đã xác thực');
  expect(html).toContain('Cần được kiểm tra');
  expect(html).toContain('Quyền do chủ ví cấp');
 });
 it('uses latest reconciliation first and keeps previous success in collapsed history',()=>{
  const job:Job={...base,status:'UNKNOWN',workflow:{...workflow,outcome:{...workflow.outcome,status:'REORGED'},timeline:[...workflow.timeline,{stage:'RECONCILIATION',created_at:workflow.created_at+100,evidence:{...workflow.outcome,status:'REORGED'}}]}};
  const html=render(job,11);
  expect(stage(job.workflow,'RECONCILIATION')?.status).toBe('REORGED');
  expect(html).toContain('Chuỗi đã tổ chức lại');
  expect(html).not.toContain('Đã xác nhận');
  expect(html).toContain('Lịch sử kết quả trước đó');
  expect(workflowNodeState(job,11)).toBe('unknown');
 });
 it('formats nested USDC payment caps instead of exposing unlabeled base units',()=>{
  const html=renderToStaticMarkup(createElement(Facts,{value:{per_payment:'100000',per_day:'1000000'},language:'vi',context:{mvp:true}}));
  expect(html).toContain('0.1 USDC');
  expect(html).toContain('1 USDC');
  expect(html).toContain('Hạn mức mỗi lần thanh toán');
 });
 it('does not mark a completed proof stage while its real Shield checks still run',()=>{
  const activity:ActivityEvent[]=[{sequence:1,stage:'PROOF',created_at:1,kind:'started',status:'RUNNING'}];
  expect(workflowNodeState({...base,status:'RUNNING',terminal:false,active_stage:'PROOF',workflow:{...workflow,activity}},6)).toBe('running');
 });
 it('retains each distinct Shield interception and coalesces its start/result',()=>{
  const events:ActivityEvent[]=[
   {sequence:1,stage:'BUILD',created_at:1,kind:'check',status:'RUNNING',check_id:'SHIELD_TOOL_CALL',check_ref:'one'},
   {sequence:2,stage:'BUILD',created_at:2,kind:'check',status:'PASS',check_id:'SHIELD_TOOL_CALL',check_ref:'one'},
   {sequence:3,stage:'BUILD',created_at:3,kind:'check',status:'FAIL',check_id:'SHIELD_TOOL_CALL',check_ref:'two'},
  ];
  expect(latestChecks(events).map(e=>e.status)).toEqual(['PASS','FAIL']);
 });
 it('keeps all twelve module names in English in both locales',()=>{
  expect(nodeTitle(0,'vi')).toBe('Owner Policy');
  expect(nodeTitle(11,'vi')).toBe('Receipt');
  for(let i=0;i<12;i++){
   expect(nodeTitle(i,'vi')).toBe(workflowNodes[i].label);
   expect(nodeTitle(i,'en')).toBe(workflowNodes[i].label);
  }
 });
 it('does not invent live checkpoints for an older verified recording',()=>{
  const html=render(base,9);
  expect(html).toContain('chưa có nhật ký kiểm tra con');
  expect(html).not.toContain('Giữ chỗ và ký duy nhất');
 });
});
