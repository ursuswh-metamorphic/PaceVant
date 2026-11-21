import {object, stage} from './format';
import {nodeTitle, workflowNodes} from './workflow-nodes';
import type {ActivityEvent, Evidence, Job, Json} from './types';
import type {Language} from './i18n';

export function pick(value: Evidence | undefined, keys: string[]): Evidence {
 return Object.fromEntries(keys.filter(key=>value?.[key]!==undefined).map(key=>[key,value![key]]));
}
export function stepEvents(job: Job | undefined,index: number): ActivityEvent[] {
 const node=workflowNodes[index];
 const names=index===11?['RECONCILIATION']:index===10?['RELAY']: [...node.events,...node.active];
 return job?.workflow?.activity?.filter(event=>names.includes(event.stage))??[];
}
export function sourceTitle(name:string,language:Language){
 const index=workflowNodes.findIndex(node=>node.events.includes(name)||node.active.includes(name));
 if(index>=0)return nodeTitle(index,language);
 return name==='INTENT'?(language==='vi'?'Yêu cầu giao dịch đã xác thực':'Authenticated transaction request'):name;
}
const inputs: [string,string[]][][] = [
 [['INTENT',['chain_id','treasury','session_id','operation','token_in','token_out','amount','recipient']]],
 [['INTENT',['objective','operation','amount','token_in','token_out','recipient','chain_id','treasury','session_id','deadline']],['OWNER_AUTHORITY',['authority','recipient_allowlist','token_allowlist']]],
 [['INTENT',['operation','amount','token_in','token_out','recipient','deadline','slippage_bps']],['OWNER_AUTHORITY',['block_number','block_hash','adapter','authority','balances','proof_policy','recipient_allowlist','max_payment_usdc','payment_spend_remaining_usdc','max_slippage_bps']]],
 [['BUILD',['build_id','call','operation','min_output','route','context_hash']],['OWNER_AUTHORITY',['block_number','block_hash','balances','treasury']]],
 [['SIMULATION',['execution_status','before','after','deltas','received','allowances','gas_used','build_hash','source_block_hash']],['BUILD',['min_output','quote']],['OWNER_AUTHORITY',['proof_policy','price_intervals','oracle','oracle_valid_until','max_daily_execution_cost_usd_e8']]],
 [['AGENT_PROPOSAL',['typed_intent','candidate_plan']],['BUILD',['operation','call','min_output','route']],['OWNER_AUTHORITY',['authority','session_expires_at','policy_hash']]],
 [['INTENT',['operation','amount','token_in','token_out','recipient']],['BUILD',['operation','call','min_output','context_hash']],['SIMULATION',['before','deltas','received','allowances','gas_used','source_block_hash']],['OWNER_AUTHORITY',['price_intervals','proof_policy','risk_remaining','global_risk_remaining','max_wavax_exposure_bps']],['RISK',['result','reason_codes']],['ITAG',['verdict','reason_codes']]],
 [['RISK',['result','reason_codes','effects_hash']],['ITAG',['verdict','reason_codes','intent_hash','graph_hash','history_hash']],['PROOF',['status','intent_hash','build_hash','evidence_root','proof_hash','phi_hash','assumptions']]],
 [['INTENT',['operation','chain_id','treasury','session_id','amount','token_in','token_out','recipient','deadline']],['SDE',['verdict','expires_at','intent_hash','build_hash','evidence_root','proof_hash','policy_hash','risk_hash','temporal_hash']],['PROOF',['phi','phi_hash','risk_debit_usd_e8','spend_debit_usd_e8']],['OWNER_AUTHORITY',['attestor','relayer','policy_version']]],
 [['ATTESTATION',['signed_fields','typed_data_hash','constraints_hash','signer','nonce','deadline','verifying_contract','chain_id']],['PROOF',['phi']],['BUILD',['build_id','call','context_hash']],['OWNER_AUTHORITY',['block_number','block_hash']]],
 [['EXACT_SIGNED_PREFLIGHT',['execution_status','exact_signed_preflight','build_hash','source_block_hash','gas_used']],['ATTESTATION',['typed_data_hash','constraints_hash','nonce','deadline','verifying_contract']],['OWNER_AUTHORITY',['relayer','max_gas_price_wei','max_tx_fee_wei','max_daily_execution_cost_usd_e8','gas_spent_or_reserved_wei']]],
 [['INTENT',['operation','amount','token_in','token_out','recipient']],['ATTESTATION',['nonce','constraints_hash','typed_data_hash']],['PROOF',['phi','proof_hash','evidence_root']],['OUTCOME',['tx_hash','environment','public_chain_receipt']]],
];
export function stepInputs(job:Job|undefined,index:number){
 const workflow=job?.workflow;
 if(!workflow)return job?.request?[{source:'INTENT',value:pick(job.request,['operation','amount','token_in','token_out','recipient_label','scope'])}]:[];
 return inputs[index].map(([source,keys])=>({source,value:pick(source==='INTENT'?workflow.intent as unknown as Evidence:stage(workflow,source),keys)}))
  .filter(item=>Object.keys(item.value).length);
}
export function latestChecks(events: ActivityEvent[]) {
 const checks=new Map<string,ActivityEvent>();
 for(const event of events)if(event.kind==='check')checks.set(`${event.stage}:${event.check_ref??event.check_id}`,event);
 return [...checks.values()];
}
export const checkNames: Record<string,[string,string]>={
 AI_MODEL:['Gọi mô hình và nhận phản hồi','Call model and receive response'],
 CALL_DECODED:['Giải mã phương thức và tham số lệnh gọi','Decode exact call method and arguments'],
 BUILDER_SCOPE:['Chuỗi, quỹ, phiên và nghiệp vụ đúng quyền','Chain, vault, session and operation scope'],LFJ_QUOTE:['Đối chiếu báo giá LFJ với dự trữ pool','Verify LFJ quote against pool reserves'],INDEPENDENT_ORACLE_QUOTE:['Đối chiếu báo giá với giá Chainlink độc lập','Compare quote with independent Chainlink prices'],PAYMENT_ALLOWLIST:['Đối chiếu người nhận và hạn mức thanh toán','Recipient allowlist and payment limits'],PROOF_BUDGETS:['Đối chiếu ngân sách và tỷ trọng tài sản','Verify budgets and asset exposure'],
 OWNER_CONTEXT:['Đọc và xác minh quyền chủ ví','Verify owner authority'],EXACT_INTENT:['Đối chiếu đề xuất với yêu cầu gốc','Compare exact authorized terms'],FIXED_CALL:['Dựng lệnh gọi từ danh mục được duyệt','Build from the approved registry'],SIMULATED_EFFECTS:['Đo tác động trên EVM','Measure EVM effects'],
 STALE_EVIDENCE:['Hiệu lực yêu cầu và dữ liệu nguồn','Request and context freshness'],UNVERIFIED_EFFECTS:['Ràng buộc mô phỏng với giao dịch và block','Bind effects to transaction and block'],UNAUTHORIZED_APPROVAL:['Không để lại quyền chi tiêu ngoài phạm vi','No unauthorized allowances'],UNEXPECTED_TRANSFER:['Chỉ trừ đúng tài sản và số lượng','Exact authorized outflow'],PAYEE_RECEIPT_SHORTFALL:['Người nhận nhận đủ USDC','Full USDC recipient receipt'],MIN_OUTPUT_NOT_MET:['Đầu ra đạt mức tối thiểu','Minimum output satisfied'],SYSTEM_GAS_REFERENCE_BUDGET:['Chi phí trong ngân sách hệ thống','System expense budget'],ORACLE_WINDOW_UNAVAILABLE:['Giá còn trong cửa sổ cho phép ký','Valid oracle signing window'],
 SHIELD_TOOL_CALL:['Shield kiểm tra lời gọi công cụ','Shield tool call check'],SHIELD_ASSISTANT:['Shield kiểm tra nội dung AI','Shield assistant check'],SHIELD_TOOL:['Shield kiểm tra dữ liệu công cụ trả về','Shield tool output check'],ITAG_AUTHORITY_HISTORY:['Đối chiếu quyền, ngân sách và lịch sử','Authority and history checks'],ITAG_GRAPH:['Dựng đồ thị nguồn gốc ý định','Build intent provenance graph'],ITAG_SEMANTIC:['Đánh giá ngữ nghĩa và trích dẫn','Semantic and citation verification'],
 Z3_FEASIBLE_PRICES:['Z3: miền giả định giá khả thi','Z3: feasible price assumptions'],Z3_CHECK_MODE:['Z3: tìm trường hợp vi phạm tổn thất','Z3: loss violation search'],Z3_COMPILE_MODE:['Z3: kiểm tra điều kiện Phi đã biên dịch','Z3: compiled Phi verification'],Z3_RISK_BOUND:['Z3: kiểm tra cận trên rủi ro','Z3: risk upper bound'],CONJUNCTIVE_DECISION:['Tổng hợp các điều kiện bắt buộc','Conjunctive security decision'],STATE_REVALIDATION:['Đọc lại trạng thái và kiểm tra bằng chứng','Revalidate state and evidence'],SIGN_ONCE:['Giữ chỗ và ký duy nhất cho yêu cầu','Durable sign-once reservation'],ATTESTOR_BINDINGS:['Kiểm tra ràng buộc dữ liệu trước ký','Verify attestation bindings'],PROOF_REVALIDATION:['Chạy lại proof trước khi ký','Recompute proof before signing'],EXACT_SIGNED_TRANSACTION:['Mô phỏng đúng giao dịch đã ký','Exact signed preflight'],
 RELAYER_AUTHORITY:['Xác minh người ký và bên gửi','Verify signer and relayer'],IDEMPOTENT_SUBMISSION:['Khôi phục đúng giao dịch đã lưu','Recover the same submission'],GAS_GUARD:['Kiểm tra gas, giá gas và khả năng chi trả','Gas, fee and funding guards'],JOURNAL_RESERVED:['Ghi nhật ký và giữ ngân sách phí nguyên tử','Atomic journal and fee reservation'],BROADCAST:['Gửi giao dịch đã lưu','Submit journaled transaction'],BROADCAST_RESULT:['Theo dõi kết quả gửi','Observe submission result'],RECEIPT_LOOKUP:['Đọc biên nhận giao dịch','Read transaction receipt'],CANONICAL_BLOCK:['Xác minh block vẫn thuộc chuỗi chính','Verify canonical block'],VAULT_EXECUTION:['Kết quả thực thi hợp đồng','Vault execution result'],RECEIPT_BINDINGS:['Đối chiếu bên gửi, đích và lệnh gọi','Verify receipt transaction bindings'],VAULT_EFFECTS:['Đối chiếu sự kiện và tác động với Phi','Verify effects against Phi'],GAS_SETTLEMENT:['Đối soát phí thực tế do hệ thống trả','Settle actual system gas expense'],CONFIRMATIONS:['Kiểm tra số xác nhận','Verify confirmations'],STAGE_STOP:['Lý do dừng bước xử lý','Stage stop reason'],
};
export function checkTitle(id:string|undefined,language:Language){return checkNames[id??'']?.[language==='vi'?0:1]??(language==='vi'?'Kiểm tra kỹ thuật: ':'Technical check: ')+(id??'');}
export function statusText(status:string,language:Language,terminal=false){
 const vi=language==='vi';
 if(status==='RUNNING'&&terminal)return vi?'Chưa có kết quả':'No result recorded';
 return ({PASS:vi?'Đạt':'Passed',FAIL:vi?'Không đạt':'Failed',RUNNING:vi?'Đang xử lý':'Running',UNKNOWN:vi?'Chưa xác định':'Unknown',UNCERTAIN:vi?'Chưa đủ bằng chứng':'Uncertain',UNAVAILABLE:vi?'Chưa khả dụng':'Unavailable'})[status]??status;
}
export function publicGraph(job:Job|undefined):Evidence{
 const stored=object(stage(job?.workflow,'ITAG')?.graph);
 if(Array.isArray(stored.nodes))return stored;
 const check=job?.workflow?.activity?.filter(event=>event.check_id==='ITAG_GRAPH').at(-1);
 return object(check?.observed);
}
export function jsonRows(value:Json|undefined){return Array.isArray(value)?value.map(object):[];}
