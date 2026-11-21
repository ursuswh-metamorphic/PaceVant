import {FileInput, FileOutput, Database, LockKeyhole, Clock3, ChevronRight} from 'lucide-react';
import {Accordion, AccordionItem} from '@/components/ui/accordion';
import {workflowNodes} from '@/lib/workflow-nodes';
import {describeReason} from '@/lib/run-feedback';
import {object, stage, text, units} from '@/lib/format';
import type {Job, Json, Evidence} from '@/lib/types';
import type {Language} from '@/lib/i18n';

export function stageDescription(index:number,language:Language){return workflowNodes[index].explanation[language==='vi'?0:1];}

const fields:Record<string,string[]> = {
 OWNER_AUTHORITY:['policy_active','session_active','paused','policy_version','balances','authority','proof_policy','recipient_allowlist','token_allowlist'],
 AGENT_PROPOSAL:['explanation','typed_intent','candidate_plan'],
 ITAG:['verdict','reason_codes','semantic','shield'],
 BUILD:['min_output','quote','route','call'],
 SIMULATION:['execution_status','before','after','deltas','received','allowances','gas_used'],
 RISK:['result','reason_codes','oracle_source','gas_economics'],
 PROOF:['status','risk_debit_usd_e8','spend_debit_usd_e8','phi','queries','assumptions'],
 SDE:['verdict','reason_codes','expires_at'],
 ATTESTATION:['signer','nonce','deadline','verifying_contract','typed_data_hash'],
 EXACT_SIGNED_PREFLIGHT:['execution_status','before','after','deltas','received','gas_used','exact_signed_preflight'],
 OUTCOME:['status','tx_hash','block_number','confirmations','actual_deltas','payee_received','gas_used','system_gas_expense'],
 RECONCILIATION:['status','tx_hash','block_number','confirmations','actual_deltas','payee_received','gas_used','system_gas_expense'],
 PROOF_REJECTION:['status','queries','counterexample'],
};
const labels:Record<string,[string,string]>={
 policy_active:['Policy đang có hiệu lực','Policy active'],session_active:['Phiên được cấp quyền','Session authorized'],paused:['Tạm dừng','Paused'],policy_version:['Phiên bản policy','Policy version'],balances:['Số dư tài sản','Asset balances'],authority:['Phạm vi được cấp quyền','Granted authority'],proof_policy:['Giới hạn bảo vệ tài sản','Asset protection limits'],recipient_allowlist:['Địa chỉ nhận được phép','Approved recipients'],token_allowlist:['Token được phép','Approved tokens'],
 price_intervals:['Miền giá giả định đã xác minh','Verified price bounds'],counterexample:['Trường hợp vi phạm được tìm thấy','Detected counterexample'],fixed_loss_usd_e8:['Tổn thất cố định cho phép','Allowed fixed loss'],slippage_bps:['Trượt giá cho phép','Allowed slippage'],chain_id:['Mã mạng blockchain','Blockchain chain ID'],treasury:['Treasury thực thi','Executing treasury'],session_id:['Mã phiên được cấp quyền','Authorized session ID'],
 spend_limit_usd_e8:['Giới hạn chi tiêu','Spend limit'],spend_used_usd_e8:['Đã sử dụng ngân sách','Spend used'],max_actions:['Số hành động tối đa','Action limit'],actions:['Số hành động đã dùng','Actions used'],cooldown:['Thời gian chờ (giây)','Cooldown (seconds)'],operation_mask:['Phạm vi nghiệp vụ (bitmask)','Operation scope (bitmask)'],
 max_relative_loss_bps:['Tổn thất tương đối tối đa','Maximum relative loss'],oracle_band_bps:['Biên giá oracle','Oracle price band'],tolerance_bps:['Biên dung sai','Tolerance'],max_oracle_age:['Tuổi oracle tối đa (giây)','Maximum oracle age (seconds)'],max_wavax_per_swap:['WAVAX tối đa mỗi lần hoán đổi','Maximum WAVAX per swap'],max_session_risk_usd_e8:['Ngân sách rủi ro phiên','Session risk budget'],global_daily_risk_usd_e8:['Ngân sách rủi ro ngày','Daily risk budget'],owner_approved:['Chủ ví đã cấp quyền','Owner authorized'],
 call:['Lệnh gọi contract','Contract call'],target:['Contract đích','Target contract'],value:['Giá trị AVAX đi kèm','AVAX value'],data:['Calldata thực thi','Execution calldata'],before_balances:['Số dư làm mốc','Reference balances'],min_deltas:['Thay đổi tối thiểu được phép','Minimum allowed changes'],receipt_credit:['Lượng nhận tối thiểu','Minimum receipt'],max_wavax_balance:['Số dư WAVAX tối đa','Maximum WAVAX balance'],
 maximum_next_fee_wei:['Phí tối đa của lượt chạy','Maximum next execution fee'],daily_spent_reserved_plus_next_reference_usd_e8:['Chi phí ngày gồm lượt chạy này','Daily cost including next execution'],separate_from_trading_loss:['Theo dõi chi phí riêng với tổn thất giao dịch','Costs tracked separately from trading loss'],actual_cost_wei:['Chi phí gas thực tế','Actual gas cost'],effective_gas_price_wei:['Giá gas thực tế (wei)','Effective gas price (wei)'],payer:['Bên chi trả','Payer'],transaction_status:['Kết quả Receipt (1 = thành công)','Receipt status (1 = success)'],billing:['Tính phí người dùng','User billing'],
 reasoning_summary:['Diễn giải kết quả','Reasoning summary'],detected_goal_drift:['Phát hiện lệch mục tiêu','Goal drift detected'],uncertainty_reasons:['Điểm chưa chắc chắn','Uncertainties'],contribution_assessments:['Đối chiếu đóng góp với yêu cầu','Task contribution checks'],relationship:['Mối liên hệ với yêu cầu','Relationship to request'],finding:['Kết luận kiểm tra','Finding'],semantic_verdict:['Mức khớp ý định','Intent alignment'],model:['Mô hình sử dụng','Model used'],provider:['Nhà cung cấp','Provider'],latency_ms:['Thời gian xử lý (ms)','Processing time (ms)'],check_ids:['Các kiểm tra đã ghi nhận','Recorded checks'],revision:['Phiên bản yêu cầu','Request revision'],unresolved_feedback:['Phản hồi chưa xử lý','Unresolved feedback'],
 explanation:['Diễn giải của AI','AI explanation'],typed_intent:['Intent được đề xuất','Proposed intent'],candidate_plan:['Kế hoạch đề xuất','Proposed plan'],
 operation:['Nghiệp vụ','Operation'],amount:['Số lượng đầu vào','Input amount'],token_in:['Tài sản đầu vào','Input asset'],token_out:['Tài sản đầu ra','Output asset'],recipient:['Người nhận','Recipient'],objective:['Yêu cầu','Request'],intent:['Intent giao dịch','Transaction intent'],
 verdict:['Quyết định','Decision'],reason_codes:['Lý do','Reasons'],result:['Kết quả kiểm tra','Check result'],status:['Trạng thái','Status'],
 before:['Số dư trước mô phỏng','Balances before simulation'],after:['Số dư sau mô phỏng','Balances after simulation'],deltas:['Thay đổi tài sản đo được','Measured asset changes'],actual_deltas:['Thay đổi tài sản thực tế','Actual asset changes'],
 gas_used:['Gas đã sử dụng','Gas used'],received:['USDC nhận được','USDC received'],payee_received:['USDC người nhận thực nhận','USDC received by payee'],
 execution_status:['Kết quả thực thi','Execution result'],risk_debit_usd_e8:['Ngân sách rủi ro sử dụng','Risk budget debit'],spend_debit_usd_e8:['Giá trị chi tiêu tham chiếu','Reference spend debit'],
 queries:['Các phép kiểm tra Z3','Z3 checks'],name:['Phép kiểm tra','Check'],phi:['Điều kiện bảo vệ Phi','Phi protection conditions'],assumptions:['Giả định của proof','Proof assumptions'],
 min_output:['Đầu ra tối thiểu','Minimum output'],quote:['Báo giá đầu ra','Output quote'],route:['Đường giao dịch','Route'],signer:['Địa chỉ ký xác nhận','Attestation signer'],nonce:['Nonce chống lặp','Replay protection nonce'],
 deadline:['Thời hạn','Deadline'],expires_at:['Hết hiệu lực','Expires at'],tx_hash:['Mã giao dịch','Transaction hash'],block_number:['Block ghi nhận','Receipt block'],confirmations:['Số xác nhận','Confirmations'],
 exact_signed_preflight:['Đã kiểm tra đúng giao dịch đã ký','Exact signed transaction checked'],semantic:['Kiểm tra ngữ nghĩa','Semantic check'],shield:['Kiểm tra Shield','Shield check'],
 verifying_contract:['Contract xác minh','Verifying contract'],typed_data_hash:['Dấu vân tay nội dung ký','Signed content fingerprint'],oracle_source:['Nguồn giá tham chiếu','Oracle source'],gas_economics:['Ngân sách chi phí','Execution cost budget'],system_gas_expense:['Chi phí thực thi thực tế','Actual execution expense'],
};
const ignored=new Set(['smt2','trace','graph','signature','raw_tx','source_hash','hash']);
function Facts({value,language,context,depth=0,field=''}:{value:Json;language:Language;context?:Evidence;depth?:number;field?:string}) {
 const vi=language==='vi';
 if(value===null)return <span>{vi?'Không có':'None'}</span>;
 if(Array.isArray(value)){
   if(field==='price_intervals')return <div className="price-bounds">{value.map((bounds,i)=><div key={i}><span>{['USDC','WAVAX',vi?'Tài sản khác':'Other asset','AVAX'][i]??String(i+1)}</span><strong>{Array.isArray(bounds)&&bounds.length===2?units(String(bounds[0]),8,8)+' – '+units(String(bounds[1]),8,8)+' USD':String(bounds)}</strong></div>)}</div>;
   if(['before','after','deltas','actual_deltas','balances','before_balances','min_deltas'].includes(field))return <div className="asset-facts">{value.map((amount,i)=><div key={i}><span>{['USDC','WAVAX',vi?'Tài sản khác':'Other asset', 'AVAX'][i]??String(i+1)}</span><strong>{i===2?String(amount)+' '+(vi?'đơn vị gốc':'base units'):units(String(amount),i===0?6:18,12)}</strong></div>)}</div>;
   return <div className="detail-list">{value.length?value.map((item,i)=><div key={i}><Facts value={item} language={language} context={context} depth={depth+1} field={field==='reason_codes'?'reason_code':''}/></div>):<span>{vi?'Không có':'None'}</span>}</div>;
 }
 if(typeof value==='object'){
  if(depth>2)return <Accordion type="single" collapsible className="nested-evidence"><AccordionItem value="fields" title={vi?'Xem '+Object.keys(value).filter(key=>!ignored.has(key)).length+' trường dữ liệu':'View '+Object.keys(value).filter(key=>!ignored.has(key)).length+' data fields'}><Facts value={value} language={language} context={context} depth={0} field={field}/></AccordionItem></Accordion>;
  return <dl className="fact-list">{Object.entries(value).filter(([key])=>!ignored.has(key)).map(([key,v])=><div key={key}><dt>{labels[key]?.[vi?0:1]??key.replaceAll('_',' ')}</dt><dd><Facts value={v} language={language} context={{...context,input_token:value.token_in??context?.input_token??null,output_token:value.token_out??context?.output_token??null}} depth={depth+1} field={key}/></dd></div>)}</dl>;
 }
 let display=String(value);
 if(field==='reason_code')display=describeReason(String(value),language);
 if(typeof value==='boolean')display=value?(vi?'Có':'Yes'):(vi?'Không':'No');
 if(field==='received'||field==='payee_received')display=units(String(value),6)+' USDC';
 if(field.endsWith('_usd_e8'))display=units(String(value),8,6)+' USD';
 const tokenName=(token:Json|undefined)=>typeof token==='string'&&token.toLowerCase()===String(context?.usdc).toLowerCase()?'USDC':typeof token==='string'&&token.toLowerCase()===String(context?.wavax).toLowerCase()?'WAVAX':undefined;
 if(field==='token_in'||field==='token_out')display=tokenName(value)??String(value);
 if(['amount','min_output','quote'].includes(field)&&/^-?\d+$/.test(String(value))){const token=tokenName(field==='amount'?context?.input_token:context?.output_token);display=token==='USDC'?units(String(value),6)+' USDC':token==='WAVAX'?units(String(value),18,12)+' WAVAX':String(value)+' base units';}
 if(['receipt_credit','max_payment_usdc','payment_spend_remaining_usdc'].includes(field))display=units(String(value),6)+' USDC';
 if(['max_wavax_balance','max_wavax_per_swap','maximum_next_fee_wei','actual_cost_wei','value'].includes(field)&&/^-?\d+$/.test(String(value)))display=units(String(value),18,18)+(['max_wavax_balance','max_wavax_per_swap'].includes(field)?' WAVAX':' AVAX');
 if(field.endsWith('_bps')&&/^\d+$/.test(String(value)))display=(Number(value)/100).toLocaleString(vi?'vi-VN':'en-GB')+'%';
 if(['deadline','expires_at','policy_expires_at','session_expires_at','oracle_valid_until','updated_at','timestamp'].includes(field)&&/^\d+$/.test(String(value)))display=new Date(Number(value)*1000).toLocaleString(vi?'vi-VN':'en-GB');
 const meanings:Record<string,[string,string]>={TOKEN_PAYMENT:['Thanh toán token','Token payment'],TOKEN_SWAP:['Hoán đổi token','Token swap'],PASS:['Đạt yêu cầu','Passed'],FAIL:['Không đạt yêu cầu','Failed'],APPROVE:['Cho phép chuyển sang ký','Approved for signing'],REJECT:['Từ chối','Rejected'],ALIGNED:['Khớp ý định','Aligned with intent'],UNCERTAIN:['Chưa đủ cơ sở xác minh','Uncertain'],VERIFIED:['Đã xác minh','Verified'],CONFIRMED:['Đã xác nhận','Confirmed'],SUCCESS:['Thành công','Successful'],REVERTED:['Giao dịch bị hoàn tác','Transaction reverted'],SYSTEM_RELAYER:['Relayer của hệ thống','System Relayer']};
 if(meanings[display])display=meanings[display][vi?0:1];
 return <span className={display.startsWith('0x')?'fact-hash':''}>{display}</span>;
}

function pick(value:Evidence|undefined,keys:string[]):Evidence{return Object.fromEntries(keys.filter(key=>value?.[key]!==undefined).map(key=>[key,value![key]]));}
const dependencies:Record<string,[string,string[]][]>={
 BUILD:[['AGENT_PROPOSAL',['typed_intent']]],
 SIMULATION:[['BUILD',['min_output','route']]],
 RISK:[['SIMULATION',['execution_status','deltas','received']],['OWNER_AUTHORITY',['proof_policy','oracle_valid_until']]],
 ITAG:[['AGENT_PROPOSAL',['typed_intent']],['BUILD',['min_output','route']]],
 PROOF:[['RISK',['result','reason_codes']],['ITAG',['verdict']],['OWNER_AUTHORITY',['price_intervals']]],
 SDE:[['RISK',['result','reason_codes']],['ITAG',['verdict']],['PROOF',['status']]],
 ATTESTATION:[['SDE',['verdict','expires_at']],['PROOF',['phi']]],
 EXACT_SIGNED_PREFLIGHT:[['ATTESTATION',['signer','nonce','deadline']]],
 OUTCOME:[['EXACT_SIGNED_PREFLIGHT',['execution_status','exact_signed_preflight']]],
 RECONCILIATION:[['OUTCOME',['tx_hash','status']]],
};
function ProofQueries({value,language}:{value:Json;language:Language}){
 const vi=language==='vi';if(!Array.isArray(value))return null;
 const names:Record<string,[string,string]>={feasible_prices:['Miền giá khả thi','Feasible price bounds'],check_mode:['Giới hạn tổn thất','Loss limits'],compile_mode:['Điều kiện bảo vệ đã biên dịch','Compiled protection conditions'],risk_bound:['Cận trên ngân sách rủi ro','Risk budget upper bound'],correlation:['Ràng buộc tương quan giá','Price correlation'],session_budget:['Ngân sách phiên','Session budget'],global_budget:['Ngân sách tổng','Global budget']};
 return <div className="proof-checks">{value.map((entry,index)=>{const query=object(entry),name=text(query.name),result=text(query.result),feasibility=name==='feasible_prices';return <div key={index}><div><strong>{names[name]?.[vi?0:1]??name.replaceAll('_',' ')}</strong><p>{result==='SAT'?(feasibility?(vi?'Có miền giá thỏa các giả định.':'The price assumptions are feasible.'):(vi?'Tìm thấy nghiệm cho truy vấn này; cần đọc nghĩa vụ kiểm tra.':'A satisfying assignment exists; review the obligation.')):result==='UNSAT'?(feasibility?(vi?'Miền giá giả định không khả thi.':'The price assumptions are infeasible.'):(vi?'Không có nghiệm thỏa truy vấn vi phạm trong miền giả định.':'No satisfying violation exists within the stated assumptions.')):(vi?'Chưa có kết luận xác minh.':'No verified conclusion.')}</p></div><span className="proof-result">{result}</span></div>})}</div>;
}
export function StageDetail({job,index,events,language}:{job?:Job;index:number;events:string[];language:Language}) {
 const vi=language==='vi',workflow=job?.workflow;
 const timeline=workflow?.timeline.filter(event=>events.includes(event.stage)||(events.includes('PROOF')&&event.stage==='PROOF_REJECTION'))??[];
 if(!timeline.length||!workflow)return null;
 const authority=stage(workflow,'OWNER_AUTHORITY');
 const context={...authority,input_token:workflow.intent.token_in,output_token:workflow.intent.token_out};
 const agent=events.includes('AGENT_PROPOSAL');
 const input=(dependencies[events[0]]??[]).map(([name,keys])=>({name,value:pick(stage(workflow,name),workflow.intent.operation==='TOKEN_SWAP'?keys.filter(key=>key!=='received'):keys)})).filter(item=>Object.keys(item.value).length);
 const recorded=job?.environment==='VERIFIED_REPLAY';
 return <div className="stage-detail-content" data-module={index}>
  <div className="evidence-provenance"><Database size={16}/><div><strong>{recorded?(vi?'Dữ liệu từ bản ghi thực thi':'Recorded execution data'):(vi?'Dữ liệu do backend ghi nhận':'Evidence recorded by the backend')}</strong><span>{workflow.workflow_id}</span></div></div>
  {agent&&workflow.intent.objective&&<section className="stage-input"><h4><FileInput size={16}/>{vi?'Đầu vào · Yêu cầu demo cố định':'Input · Fixed demo request'}<LockKeyhole size={13}/></h4><blockquote>{workflow.intent.objective}</blockquote><p className="request-caption">{vi?'Yêu cầu này cùng token, số lượng và người nhận được gửi vào bước lập kế hoạch AI. Demo dùng yêu cầu có sẵn, không nhận prompt tự do.':'This request, assets, amount and recipient feed AI planning. The demo uses a preset request.'}</p><Accordion type="single" collapsible className="technical-evidence"><AccordionItem value="terms" title={vi?'Điều khoản đi kèm yêu cầu':'Terms accompanying the request'}><Facts value={pick(object(stage(workflow,'AGENT_PROPOSAL')?.typed_intent),['operation','amount','token_in','token_out','recipient','deadline'])} language={language} context={context}/></AccordionItem></Accordion></section>}
  {!!input.length&&<section className="stage-input"><h4><FileInput size={16}/>{vi?'Đầu vào từ các bước trước':'Input from preceding steps'}</h4>{input.map(item=><div className="input-source" key={item.name}><span>{workflowNodes.find(node=>node.events.includes(item.name))?.label??item.name}</span><Facts value={item.value} language={language} context={context}/></div>)}</section>}
  {timeline.map((event,i)=>{
   const curated=agent?pick(event.evidence,['typed_intent','explanation']):pick(event.evidence,fields[event.stage]??Object.keys(event.evidence));
   if(workflow.intent.operation==='TOKEN_SWAP'){delete curated.received;delete curated.payee_received;}
   if(event.stage==='BUILD'&&curated.call)curated.call=pick(object(curated.call),['target','value']);
   const queries=curated.queries;delete curated.queries;
   if(agent)curated.typed_intent=pick(object(event.evidence.candidate_plan??event.evidence.typed_intent),['operation','amount','token_in','token_out','recipient']);
   const others=pick(event.evidence,Object.keys(event.evidence).filter(key=>!Object.keys(curated).includes(key)&&key!=='queries'&&!ignored.has(key)));
   if(event.stage==='BUILD'&&event.evidence.call)others.call=event.evidence.call;
   return <section className="stage-output" key={event.stage+'-'+i}>
    <h4><FileOutput size={16}/>{agent?(vi?'Đầu ra · Intent AI đề xuất':'Output · AI proposed intent'):(vi?'Đầu ra · Kết quả đã ghi nhận':'Output · Recorded result')}</h4>
    <div className="event-recorded"><Clock3 size={12}/><time dateTime={new Date(event.created_at*1000).toISOString()}>{new Date(event.created_at*1000).toLocaleString(vi?'vi-VN':'en-GB')}</time><span>{event.stage}</span></div>
    <Facts value={curated} language={language} context={context}/>
    {queries&&<ProofQueries value={queries} language={language}/>}
    {!!Object.keys(others).length&&<Accordion type="single" collapsible className="technical-evidence"><AccordionItem value="technical" title={vi?'Bằng chứng và thông số bổ sung':'Additional evidence and parameters'}><Facts value={others} language={language} context={context}/></AccordionItem></Accordion>}
   </section>;
  })}
  {job?.terminal&&job.active_stage&&workflowNodes[index].active.includes(job.active_stage)&&['FAILED','REJECTED','UNKNOWN','INTERRUPTED','UNAVAILABLE'].includes(job.status)&&<div className="module-stop"><ChevronRight size={15}/><span>{vi?'Lượt chạy dừng tại bước này. Mã backend: ':'The run stopped at this step. Backend code: '}{job.reason_code??workflow.reason_code??job.status}</span></div>}
 </div>;
}
