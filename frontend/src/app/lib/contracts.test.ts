import {describe, expect, it} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {RawEvidence} from '../components/evidence';
import {beginAttempt, clearAttempt, loadAttempt, saveAttempt} from './recovery';
import {gateStates} from './pipeline';
import {intentAmount, publicExplorer, units} from './format';
import type {Job} from './types';

function storage() {
  const map = new Map<string,string>();
  return {getItem:(key:string)=>map.get(key)??null,setItem:(key:string,value:string)=>{map.set(key,value);},removeItem:(key:string)=>{map.delete(key);}} as Storage;
}
const base:Job = {job_id:'test',scenario:'payment',created_at:1,status:'RUNNING',environment:'ANVIL_FORK',public_chain_broadcast:false,terminal:false,
  workflow:{workflow_id:'w',status:'STARTED',created_at:1,intent:{operation:'TOKEN_PAYMENT',amount:'10000',token_in:'u',token_out:'u',recipient:'o',treasury:'v',objective:'exact',deadline:1,session_id:'s',chain_id:43113},timeline:[]}};

describe('request identity and recovery',()=>{
  it('reload retains exact scenario/key and never invents another attempt',()=>{
    const memory=storage(), first=beginAttempt('payment',memory);
    expect(beginAttempt('swap',memory)).toEqual(first);
    saveAttempt({...first,job_id:'accepted'},memory);
    expect(loadAttempt(memory)?.job_id).toBe('accepted');
    expect(loadAttempt(memory)?.key).toBe(first.key);
    clearAttempt(memory); expect(loadAttempt(memory)).toBeNull();
  });
  it('storage failure or corrupt data prevents creating an untracked request',()=>{
    const memory=storage(); memory.setItem('pacevant.judge.attempt.v1','{"bad":true}');
    expect(()=>beginAttempt('payment',memory)).toThrow();
    expect(()=>beginAttempt('payment',{...storage(),setItem:()=>{throw Error('quota');}})).toThrow('quota');
  });
});
describe('evidence-driven pipeline',()=>{
  it('never moves pending gates on a timer or declares receipt from running',()=>{
    expect(gateStates(base).every(value=>value==='pending')).toBe(true);
    expect(gateStates({...base,active_stage:'SIMULATION'})[2]).toBe('running');
  });
  it('marks actual rejection and not-run gates honestly',()=>{
    const value:Job={...base,status:'REJECTED',terminal:true,active_stage:'BUILD',workflow:{...base.workflow!,timeline:[{stage:'AGENT_PROPOSAL',created_at:1,evidence:{}}]}};
    expect(gateStates(value)[0]).toBe('rejected');
    expect(gateStates(value)[6]).toBe('skipped');
  });
  it('does not show failed ITAG as passed just because an event exists',()=>{
    const value:Job={...base,status:'REJECTED',terminal:true,workflow:{...base.workflow!,timeline:[{stage:'ITAG',created_at:1,evidence:{verdict:'FAIL'}}]}};
    expect(gateStates(value)[1]).toBe('rejected');
  });
  it('only canonical confirmed outcome marks execution and receipt passed',()=>{
    const unknown:Job={...base,status:'UNKNOWN',workflow:{...base.workflow!,outcome:{status:'SUBMITTED_UNKNOWN',environment:'ANVIL_FORK',public_chain_receipt:false}}};
    expect(gateStates(unknown)[6]).toBe('unknown');
    expect(gateStates({...unknown,workflow:{...unknown.workflow!,outcome:{...unknown.workflow!.outcome!,status:'CONFIRMED'}}})[6]).toBe('passed');
  });
});
describe('units and explorer attribution',()=>{
  it('renders provider evidence as text rather than executable HTML',()=>{
    const markup=renderToStaticMarkup(createElement(RawEvidence,{value:{explanation:'<script>alert(1)</script>'}}));
    expect(markup).not.toContain('<script>');
    expect(markup).toContain('&lt;script&gt;');
  });
  it('formats exact tiny test amounts without float loss',()=>{expect(units('1',6)).toBe('0.000001');expect(units('10000',6)).toBe('0.01');});
  it('uses the actual asset for guard history, including the payment fallback',()=>{
    const workflow={...base.workflow!,intent:{...base.workflow!.intent,amount:'10000',token_in:'USDC'},timeline:[{stage:'OWNER_AUTHORITY',created_at:1,evidence:{usdc:'USDC',wavax:'WAVAX'}}]};
    expect(intentAmount(workflow)).toBe('0.01');
    expect(intentAmount({...workflow,intent:{...workflow.intent,token_in:'WAVAX',amount:'50000000000000'}})).toBe('0.00005');
  });
  it('never links a fork or replay hash to public Fuji',()=>{
    const outcome={status:'CONFIRMED',environment:'ANVIL_FORK',public_chain_receipt:false,tx_hash:'0x'+'a'.repeat(64)};
    expect(publicExplorer({...base,workflow:{...base.workflow!,outcome}})).toBeNull();
    expect(publicExplorer({...base,environment:'VERIFIED_REPLAY',workflow:{...base.workflow!,outcome:{...outcome,environment:'REAL_FUJI_EXECUTION',public_chain_receipt:true}}})).toBeNull();
  });
});
