import {describe,expect,it} from 'vitest';
import {beginAttempt,clearAttempt,loadAttempt,loadViewedRun,saveAttempt,saveViewedRun} from './recovery';
import {describeReason,runIssue} from './run-feedback';
import type {Job} from './types';

function storage(){const values=new Map<string,string>();return {getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value);},removeItem:(key:string)=>{values.delete(key);}} as Storage;}
const job:Job={job_id:'judge_'+'a'.repeat(32),scenario:'swap',created_at:100,status:'REJECTED',terminal:true,environment:'ANVIL_FORK',public_chain_broadcast:false,active_stage:'ITAG',reason_code:'SECURITY_GATE_FAILED',workflow:{workflow_id:'workflow',status:'REJECTED',created_at:100,intent:{operation:'TOKEN_SWAP',amount:'1',token_in:'u',token_out:'w',recipient:'v',treasury:'v',objective:'Authorized swap',deadline:200,session_id:'session',chain_id:43113},timeline:[{stage:'RISK',created_at:110,evidence:{result:'FAIL',reason_codes:['MIN_OUTPUT_NOT_MET']}},{stage:'REJECTION_OR_RECOVERY',created_at:120,evidence:{code:'SECURITY_GATE_FAILED',signed:false}}]}};

describe('run continuity',()=>{
 it('retains the completed viewed run after clearing only the pending request',()=>{
  const memory=storage(),attempt=beginAttempt('swap',memory);
  saveAttempt({...attempt,job_id:job.job_id},memory);saveViewedRun({job_id:job.job_id,scenario:'swap'},memory);
  clearAttempt(memory);
  expect(loadAttempt(memory)).toBeNull();expect(loadViewedRun(memory)).toEqual({job_id:job.job_id,scenario:'swap'});
 });
 it('keeps a new unacknowledged attempt distinct from an older completed view',()=>{
  const memory=storage();saveViewedRun({job_id:job.job_id,scenario:'swap'},memory);
  const pending=beginAttempt('payment',memory);
  expect(loadAttempt(memory)?.job_id).toBeUndefined();expect(loadAttempt(memory)?.key).toBe(pending.key);
  expect(beginAttempt('swap',memory)).toEqual(pending);
  expect(loadViewedRun(memory)?.scenario).toBe('swap');
 });
 it('ignores corrupt display references without creating a submission identity',()=>{
  const memory=storage();memory.setItem('pacevant.judge.view.v1','null');expect(loadViewedRun(memory)).toBeNull();
  memory.setItem('pacevant.judge.view.v1','{"job_id":"http://example.com","scenario":"swap"}');expect(loadViewedRun(memory)).toBeNull();
  expect(loadAttempt(memory)).toBeNull();
 });
});
describe('evidence-backed rejection explanations',()=>{
 it('surfaces the risk reason instead of the generic final security code',()=>{
  const issue=runIssue(job)!;expect(issue.stage).toBe('Economic Risk');expect(issue.reasons).toEqual(['MIN_OUTPUT_NOT_MET']);
  expect(issue.codes).toContain('SECURITY_GATE_FAILED');expect(issue.unsigned).toBe(true);
  expect(describeReason(issue.reasons[0],'vi')).toContain('đầu ra');
 });
 it('does not infer that a signed or submitted transaction never executed',()=>{
  const signed={...job,workflow:{...job.workflow!,timeline:[...job.workflow!.timeline,{stage:'ATTESTATION',created_at:115,evidence:{nonce:'1'}}]}};
  expect(runIssue(signed)?.unsigned).toBe(false);
 });
 it('never declares a blocked result while a run is still active or already confirmed',()=>{
  expect(runIssue({...job,status:'RUNNING',terminal:false})).toBeNull();expect(runIssue({...job,status:'CONFIRMED'})).toBeNull();
 });
 it('distinguishes verification output errors from an attack finding',()=>{
  const unavailable={...job,status:'UNAVAILABLE' as const,workflow:{...job.workflow!,timeline:[{stage:'ITAG',created_at:110,evidence:{verdict:'REJECT',reason_codes:['ITAG_INVALID_SEMANTIC_REFERENCES_OR_OUTPUT']}}]}};
  expect(runIssue(unavailable)?.stage).toBe('Shield + ITAG');
  expect(describeReason('ITAG_INVALID_SEMANTIC_REFERENCES_OR_OUTPUT','vi')).toContain('không phải kết luận');
 });
});
