import {useRef} from 'react';
import './module-evidence.css';
import {FileInput, FileOutput, Database, Clock3, ChevronRight, ShieldCheck} from 'lucide-react';
import {Accordion, AccordionItem} from './ui/accordion';
import {Facts} from './evidence-facts';
import {EvidenceBindings, IntentGraph, ModelMetrics, OracleEvidence, ProcessLog} from './module-process';
import {nodeTitle, workflowNodes} from '@/lib/workflow-nodes';
import {pick, sourceTitle, stepEvents, stepInputs} from '@/lib/module-evidence';
import {describeReason} from '@/lib/run-feedback';
import {object, stage, text} from '@/lib/format';
import type {Job, Json, Evidence} from '@/lib/types';
import type {Language} from '@/lib/i18n';

export function stageDescription(index:number,language:Language){return workflowNodes[index].explanation[language==='vi'?0:1];}
const fields:Record<string,string[]>={
 OWNER_AUTHORITY:['policy_active','session_active','paused','policy_version','policy_expires_at','session_expires_at','balances','authority','proof_policy','recipient_allowlist','token_allowlist','max_payment_usdc','payment_spend_remaining_usdc','daily_payment_remaining_usdc'],
 AGENT_PROPOSAL:['typed_intent','candidate_plan','explanation'],BUILD:['build_id','min_output','quote','route','call','operation','context_hash'],
 SIMULATION:['execution_status','before','after','deltas','received','allowances','gas_used','source_block','source_block_hash'],
 RISK:['result','reason_codes','oracle_source','gas_economics'],ITAG:['verdict','reason_codes','semantic','shield','history_hash'],
 PROOF:['status','risk_debit_usd_e8','spend_debit_usd_e8','phi','phi_hash','assumptions'],PROOF_REJECTION:['status','counterexample'],
 SDE:['verdict','reason_codes','expires_at','intent_hash','build_hash','evidence_root','proof_hash','risk_hash','temporal_hash'],
 ATTESTATION:['signer','domain_version','chain_id','verifying_contract','nonce','deadline','typed_data_hash','constraints_hash','signed_fields'],
 EXACT_SIGNED_PREFLIGHT:['execution_status','before','after','deltas','received','gas_used','exact_signed_preflight','source_block_hash','allowances'],
 OUTCOME:['status','environment','public_chain_receipt','tx_hash','block_number','block_hash','confirmations','actual_deltas','payee_received','gas_used','system_gas_expense'],
 RECONCILIATION:['status','environment','public_chain_receipt','tx_hash','block_number','block_hash','confirmations','actual_deltas','payee_received','gas_used','system_gas_expense'],
};
const usp=[
 ['Quyền do chủ ví cấp; AI không được tự mở rộng phạm vi.','Authority belongs to the owner; the AI cannot expand it.'],
 ['Đề xuất của AI phải giữ nguyên token, số tiền, người nhận và nghiệp vụ.','AI proposals must preserve exact assets, amount, recipient and operation.'],
 ['Danh mục cố định quyết định contract và phương thức gọi; báo giá không tự cấp quyền.','The fixed registry determines targets and selectors; a quote grants no authority.'],
 ['Đo tác động giao dịch trên EVM trước khi cấp chữ ký thực thi.','Measure EVM effects before granting execution authority.'],
 ['Tách tiền thanh toán, tổn thất và phí gas thành các giới hạn riêng.','Payment principal, economic loss and gas expenses have separate bounds.'],
 ['Shield kiểm tra từ đầu luồng; ITAG đối chiếu nguồn gốc, lịch sử và ý định.','Shield intercepts throughout the workflow; ITAG verifies provenance, history and intent.'],
 ['Z3 kiểm tra trong miền giả định đã xác định và biên dịch Phi để bảo vệ khi thực thi.','Z3 verifies bounded assumptions and compiles Phi for execution enforcement.'],
 ['Mọi điều kiện bắt buộc đều phải đạt; một điểm số AI không bù được kiểm tra thất bại.','Every required gate must pass; AI scores cannot compensate for a failed gate.'],
 ['Đọc lại trạng thái, chạy lại proof và ký duy nhất dữ liệu đã được ràng buộc EIP-712.','Revalidate state, recompute proof and sign the bound EIP-712 operation once.'],
 ['Kiểm tra đúng giao dịch đã ký với Phi cuối cùng, rồi đọc lại trạng thái trước khi gửi.','Check the exact signed operation with final Phi and revalidate before submission.'],
 ['Ghi nhật ký và giữ phí nguyên tử; hợp đồng thực thi điều kiện trong cùng giao dịch.','Atomic journaling and fee reservation precede guarded contract execution.'],
 ['Đối chiếu biên nhận, sự kiện và phí thực tế; kết quả chưa rõ vẫn được giữ chưa xác định.','Verify canonical receipts, effects and actual fees; preserve uncertain outcomes.'],
];
function ProofQueries({value,language}:{value:Json;language:Language}){
 const vi=language==='vi';if(!Array.isArray(value))return null;
 const names:Record<string,[string,string]>={feasible_prices:['Miền giả định giá có nghiệm','Feasible price assumptions'],check_mode:['Kiểm tra vi phạm giới hạn tổn thất','Loss-bound violation query'],compile_mode:['Điều kiện Phi bảo vệ trong miền giả định','Compiled Phi protection'],risk_bound:['Cận trên ngân sách rủi ro','Risk budget upper bound']};
 return <div className="proof-checks">{value.map((entry,index)=>{const query=object(entry),name=text(query.name),result=text(query.result),expected=name==='feasible_prices'?'SAT':name in names?'UNSAT':undefined;return <div key={index}><div><strong>{names[name]?.[vi?0:1]??name}</strong><p>{vi?'Kết quả yêu cầu: ':'Required: '}{expected??(vi?'Xem nghĩa vụ gốc':'See original obligation')}. {vi?'Kết quả solver thực tế: ':'Actual solver result: '}{result}.</p>{query.smt2&&<Accordion type="single" collapsible><AccordionItem value="smt" title={vi?'Xem truy vấn solver và dấu vân tay':'View solver query and hash'}><code className="solver-source">{text(query.smt2)}</code><code className="binding-code">{text(query.hash,'')}</code></AccordionItem></Accordion>}</div><span className="proof-result" data-valid={expected===result}>{result}</span></div>})}</div>;
}
export function StageDetail({job,index,events,language}:{job?:Job;index:number;events:string[];language:Language}){
 const inputRef=useRef<HTMLElement>(null),processRef=useRef<HTMLDivElement>(null),outputRef=useRef<HTMLElement>(null);
 if(!job)return null;
 const vi=language==='vi',workflow=job.workflow,authority=stage(workflow,'OWNER_AUTHORITY');
 const context:Evidence={...authority,input_token:workflow?.intent.token_in??job.request?.token_in??null,output_token:workflow?.intent.token_out??job.request?.token_out??null};
 const input=stepInputs(job,index),activity=stepEvents(job,index);
 const timeline=workflow?.timeline.filter(e=>events.includes(e.stage)||(events.includes('PROOF')&&e.stage==='PROOF_REJECTION')).slice().reverse()??[];
 const latest=timeline[0],output=(index>=10?workflow?.outcome as unknown as Evidence|undefined:undefined)??latest?.evidence,eventName=latest?.stage??events[0];
 const curated=pick(output,fields[eventName]??Object.keys(output??{}));
 if(workflow?.intent.operation==='TOKEN_SWAP'){delete curated.received;delete curated.payee_received;}
 if(eventName==='AGENT_PROPOSAL')curated.typed_intent=pick(object(output?.candidate_plan??output?.typed_intent),['operation','amount','token_in','token_out','recipient']);
 const additional=pick(output,Object.keys(output??{}).filter(key=>!Object.keys(curated).includes(key)&&!['graph','queries','signature','raw_tx','owner_signature'].includes(key)));
 const start=activity.find(e=>e.kind==='started'),beforeWorkflow=index===0&&!workflow;
 return <div className="stage-detail-content" data-module={index}>
  <div className="module-value"><ShieldCheck size={17}/><p>{usp[index]?.[vi?0:1]}</p></div>
  <div className="evidence-provenance"><Database size={16}/><div><strong>{job.environment==='VERIFIED_REPLAY'?(vi?'Dữ liệu từ bản ghi thực thi':'Recorded execution data'):(vi?'Dữ liệu do backend ghi nhận':'Backend-recorded evidence')}</strong><span>{workflow?.workflow_id??job.job_id}</span></div></div>
  <nav className="detail-section-nav" aria-label={vi?'Nội dung chi tiết bước':'Step detail sections'}><span className="detail-step-context">{nodeTitle(index,language)}</span>{[[vi?'Đầu vào':'Inputs',inputRef],[vi?'Xử lý':'Processing',processRef],[vi?'Đầu ra':'Outputs',outputRef]].map(([label,ref])=><button type="button" key={String(label)} onClick={()=>{const target=ref as typeof inputRef;target.current?.scrollIntoView({block:'start',behavior:'instant'});}}>{String(label)}</button>)}</nav>
  <section className="stage-input" ref={inputRef}><h4><FileInput size={16}/>{vi?'Đầu vào và nguồn dữ liệu':'Inputs and data sources'}</h4>
   {events.includes('AGENT_PROPOSAL')&&workflow?.intent.objective&&<><blockquote>{workflow.intent.objective}</blockquote><p className="request-caption">{vi?'Yêu cầu demo cố định được gửi tới AI. Các điều khoản chính xác dưới đây là phạm vi được cấp quyền.':'The fixed demo request is sent to AI. The exact terms below define its authority.'}</p></>}
   {input.length?input.map(item=><div className="input-source" key={item.source}><span>{sourceTitle(item.source,language)}</span>{item.source==='INTENT'?<Facts value={item.value} language={language} context={context}/>:<Accordion type="single" collapsible><AccordionItem value="source" title={(vi?'Xem dữ liệu từ ':'View data from ')+sourceTitle(item.source,language)}><Facts value={item.value} language={language} context={context}/></AccordionItem></Accordion>}</div>):<p className="module-note">{vi?'Chưa có dữ liệu đầu vào của bước này.':'Inputs have not been recorded yet.'}</p>}
   {start?.inputs&&Object.keys(start.inputs).length>0&&<Accordion type="single" collapsible className="technical-evidence"><AccordionItem value="start" title={vi?'Đầu vào tại thời điểm bắt đầu bước':'Inputs recorded at stage start'}><Facts value={start.inputs} language={language} context={context}/></AccordionItem></Accordion>}
  </section>
  {beforeWorkflow&&<section className="module-process"><h4><Clock3 size={16}/>{vi?'Chuẩn bị nguồn dữ liệu':'Preparing source data'}</h4><p className="module-note">{job.terminal?(vi?'Không thể hoàn tất xác minh dữ liệu nguồn. Chưa lập đề xuất, ký hoặc gửi giao dịch.':'Source verification did not complete. No proposal, signature or submission was made.'):job.phase==='WAITING_FOR_ORACLE'?(vi?'Đang chờ vòng giá Chainlink đủ mới. Chưa lập đề xuất, ký hoặc gửi giao dịch.':'Waiting for a fresh Chainlink round. No proposal, signing or submission yet.'):(vi?'Backend đang chuẩn bị môi trường và xác minh nguồn dữ liệu.':'The backend is preparing execution and verifying sources.')}</p>{job.oracle_observation&&<Facts value={job.oracle_observation} language={language} context={context}/>} {!!job.preparation?.length&&<Accordion type="single" collapsible><AccordionItem value="preparation" title={vi?'Các mốc chuẩn bị đã ghi nhận':'Recorded preparation events'}><Facts value={job.preparation} language={language} context={context}/></AccordionItem></Accordion>}</section>}
  <div ref={processRef} className="process-anchor"><ProcessLog job={job} index={index} language={language} context={context}/></div>
  {index===5&&<><IntentGraph job={job} language={language} context={context}/><Accordion type="single" collapsible className="shield-history"><AccordionItem value="shield" title={vi?'Các lần Shield kiểm tra xuyên suốt quy trình':'Shield checks throughout the workflow'}><ProcessLog job={{...job,workflow:workflow?{...workflow,activity:workflow.activity?.filter(e=>e.check_id?.startsWith('SHIELD_')).map(e=>({...e,stage:'ITAG'}))}:undefined}} index={5} language={language} context={context}/></AccordionItem></Accordion></>}
  {(index===0||index===4)&&<OracleEvidence job={job} language={language} context={context}/>}
  {index>=7&&<EvidenceBindings job={job} language={language}/>}
  {(index===1||index===11)&&<ModelMetrics job={job} language={language} context={context}/>}
  <section className="stage-output" ref={outputRef}><h4><FileOutput size={16}/>{vi?'Đầu ra và kết quả mới nhất':'Latest output and result'}</h4>
   {output?<><div className="event-recorded"><Clock3 size={12}/>{latest&&<time dateTime={new Date(latest.created_at*1000).toISOString()}>{new Date(latest.created_at*1000).toLocaleString(vi?'vi-VN':'en-GB',{timeZone:'Asia/Ho_Chi_Minh'})} · UTC+7</time>}<span>{sourceTitle(eventName,language)}</span></div><Facts value={curated} language={language} context={context}/>{output.queries&&<ProofQueries value={output.queries} language={language}/>} {!!Object.keys(additional).length&&<Accordion type="single" collapsible className="technical-evidence"><AccordionItem value="technical" title={vi?'Bằng chứng và thông số bổ sung':'Additional evidence and parameters'}><Facts value={additional} language={language} context={context}/></AccordionItem></Accordion>}</>:<p className="module-note">{job.terminal?(vi?'Bước này chưa tạo đầu ra. Không có kết quả xác minh được ghi nhận.':'This stage produced no output. No verified result is recorded.'):(vi?'Chưa có đầu ra. Kết quả sẽ cập nhật ngay khi backend ghi nhận.':'No output yet. Results appear when recorded by the backend.')}</p>}
  </section>
  {timeline.length>1&&<Accordion type="single" collapsible><AccordionItem value="previous" title={vi?'Lịch sử kết quả trước đó':'Previous results'}>{timeline.slice(1).map((event,i)=><div className="prior-result" key={i}><p>{new Date(event.created_at*1000).toLocaleString(vi?'vi-VN':'en-GB',{timeZone:'Asia/Ho_Chi_Minh'})} · {sourceTitle(event.stage,language)}</p><Facts value={pick(event.evidence,fields[event.stage]??Object.keys(event.evidence))} language={language} context={context}/></div>)}</AccordionItem></Accordion>}
  {job.terminal&&job.reason_code&&(workflowNodes[index].active.includes(job.active_stage??'')||beforeWorkflow)&&<div className="module-stop"><ChevronRight size={15}/><span>{describeReason(job.reason_code,language)}</span></div>}
  <div className="module-handoff"><strong>{vi?'Chuyển tiếp':'Next handoff'}</strong><span>{index<11?(vi?'Bằng chứng của bước này được dùng tại: ':'Evidence from this step is used by: ')+nodeTitle(index+1,language):(vi?'Lưu kết quả, đối soát tài sản và phí; giữ trạng thái chưa rõ để khôi phục an toàn.':'Persist outcome and reconcile assets and fees; preserve uncertainty for recovery.')}</span></div>
 </div>;
}
