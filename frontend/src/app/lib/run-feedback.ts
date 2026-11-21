import type {Language} from './i18n';
import type {Evidence, Job, Json} from './types';
import {nodeTitle,workflowNodes} from './workflow-nodes';

const phrases:Record<string,[string,string]>={
 ATTACK_BAD_SIGNATURE:['Contract chặn dữ liệu bị sửa vì chữ ký gốc không còn khớp. Không gửi giao dịch mới.','The contract rejected modified data because the original signature no longer matches. No new transaction was sent.'],
 ATTACK_NONCE_REPLAY:['Contract chặn nonce đã dùng, ngăn thanh toán lần hai. Không gửi giao dịch mới.','The contract rejected the used nonce, preventing duplicate payment. No new transaction was sent.'],
 ATTACK_NOT_BLOCKED_AS_EXPECTED:['Kết quả không khớp lỗi dự kiến; ca kiểm thử chưa đạt.','The result did not match the expected error; the security test did not pass.'],
 PUBLIC_RUN_INTERRUPTED_RECONCILE_REQUIRED:['Phiên bị gián đoạn; cần đối soát yêu cầu cũ trước khi thực hiện giao dịch tiếp theo.','The run was interrupted; reconcile the original request before another transaction.'],
 DEMO_NOT_CONFIGURED:['Chạy trực tiếp chưa được cấu hình. Bạn vẫn có thể xem các bản ghi đã xác minh ở Tổng quan.','Live execution is not configured. Verified recordings remain available in Overview.'],
 DEMO_BUSY:['Một lượt chạy khác đang xử lý. Hãy chờ hoàn tất rồi thử lại.','Another run is active. Wait for it to finish and retry.'],
 DEMO_RATE_LIMIT:['Đã đạt giới hạn lượt chạy của phiên hoặc địa chỉ kết nối.','The visitor or network request allowance has been reached.'],
 DEMO_DAILY_LIMIT:['Hệ thống đã đạt giới hạn lượt chạy trong ngày.','The system daily run allowance has been reached.'],
 INVALID_AGENT_PLAN:['Phản hồi của AI chưa đúng cấu trúc yêu cầu; hệ thống chưa cấp quyền ký.','The AI response did not match the required schema; signing is not authorized.'],
 STALE_REQUIRES_REEVALUATION:['Trạng thái đã thay đổi hoặc bằng chứng hết hiệu lực; cần kiểm tra lại trước khi ký hay gửi.','State changed or evidence expired; revalidation is required.'],
 PAYEE_NOT_ALLOWED:['Địa chỉ nhận không nằm trong danh sách được chủ ví cho phép.','The recipient is outside the owner-approved allowlist.'],
 MIN_OUTPUT_NOT_MET:['Lượng token đầu ra trong mô phỏng thấp hơn mức tối thiểu được bảo vệ.','Simulated output is below the protected minimum.'],
 PAYEE_RECEIPT_SHORTFALL:['Người nhận không nhận đủ số token tối thiểu được yêu cầu.','The payee receives less than the required minimum.'],
 UNEXPECTED_TRANSFER:['Mô phỏng phát hiện thay đổi tài sản không khớp số tiền hoặc token được cho phép.','Simulated asset changes do not match the authorized amount or assets.'],
 UNAUTHORIZED_APPROVAL:['Phát hiện quyền chi tiêu token không được phép.','An unauthorized token allowance was detected.'],
 UNVERIFIED_EFFECTS:['Không xác minh được kết quả mô phỏng với đúng giao dịch và trạng thái nguồn.','Simulation effects could not be verified against the transaction and source state.'],
 ORACLE_PRICE_DEVIATION:['Báo giá nằm ngoài biên giá hoặc giới hạn tổn thất được cho phép.','The quote exceeds the allowed price or loss bounds.'],
 STALE_EVIDENCE:['Bằng chứng đã quá hạn hoặc giao dịch đã hết thời gian hiệu lực.','The evidence or transaction validity window has expired.'],
 SYSTEM_GAS_REFERENCE_BUDGET:['Chi phí gas dự kiến vượt ngân sách thực thi của hệ thống.','Estimated gas costs exceed the system execution budget.'],
 ORACLE_WINDOW_UNAVAILABLE:['Giá tham chiếu không còn trong cửa sổ cho phép ký.','The reference price is outside the permitted signing window.'],
 FRESH_CHAINLINK_SIGNING_WINDOW_UNAVAILABLE:['Chưa có giá Chainlink đủ mới để ký an toàn. Hãy thử lại khi nguồn giá cập nhật.','A fresh Chainlink signing window is unavailable. Retry after the source updates.'],
 LFJ_UNSUPPORTED_ROUTE:['Đường hoán đổi do công cụ trả về nằm ngoài phạm vi LFJ được cho phép.','The proposed swap route is outside the approved LFJ scope.'],
 TASK_MISALIGNED:['Hành động được đề xuất không khớp yêu cầu đã được cấp quyền.','The proposed action does not match the authorized request.'],
 ITAG_SEMANTIC_DIVERGENCE:['Bộ kiểm tra ý định phát hiện hành động lệch mục tiêu hoặc mâu thuẫn với yêu cầu gốc.','Intent verification found goal drift or a conflict with the original request.'],
 ITAG_SEMANTIC_UNCERTAIN:['Chưa có đủ bằng chứng để xác nhận hành động phù hợp với ý định.','There is insufficient evidence to verify intent alignment.'],
 ITAG_INVALID_SEMANTIC_REFERENCES_OR_OUTPUT:['Bộ kiểm tra ý định trả về bằng chứng hoặc trích dẫn không hợp lệ. Đây không phải kết luận đã phát hiện tấn công.','Intent verification returned invalid evidence or citations. This is not a confirmed attack finding.'],
 ITAG_PROVIDER_UNAVAILABLE:['Dịch vụ kiểm tra ý định chưa trả về kết quả xác minh hợp lệ.','The intent verification provider did not return a valid result.'],
 ITAG_BUILD_MISMATCH:['Giao dịch được dựng không khớp intent hoặc policy đã xác thực.','The built transaction does not match the authenticated intent or policy.'],
 ITAG_ACTION_SCOPE_MISMATCH:['Nghiệp vụ nằm ngoài quyền được cấp cho phiên này.','The operation exceeds this session’s authority.'],
 ITAG_SESSION_EXHAUSTED:['Phiên đã chạm giới hạn hành động hoặc thời hạn cho phép.','The session has reached its action or validity limits.'],
 ITAG_UNRESOLVED_HISTORY:['Phiên còn giao dịch chưa được đối soát; chưa thể cấp quyền cho lượt tiếp theo.','The session has unresolved transaction history.'],
 ITAG_UPSTREAM_TASK_SHIELD_INTERVENTION:['Task Shield đã can thiệp vào một lời gọi trước đó vì không đáp ứng điều kiện bảo vệ.','Task Shield intervened in an earlier call that did not satisfy its protections.'],
 AGENT_PLAN_OUT_OF_SCOPE:['AI đề xuất thay đổi token, số lượng hoặc người nhận ngoài yêu cầu đã xác thực.','The AI proposed assets, amount or recipient outside the authenticated request.'],
 SECURITY_GATE_FAILED:['Một hoặc nhiều kiểm tra bảo mật chưa đạt yêu cầu.','One or more security checks did not pass.'],
 DECISION_NOT_APPROVED:['Quyết định bảo mật không cho phép chuyển sang ký giao dịch.','The security decision did not authorize signing.'],
 PAYMENT_SPENDING_LIMIT:['Khoản thanh toán vượt hạn mức chi tiêu được cấp.','The payment exceeds an authorized spending limit.'],
 SWAP_SPENDING_LIMIT:['Giao dịch hoán đổi vượt hạn mức chi tiêu được cấp.','The swap exceeds an authorized spending limit.'],
 CUMULATIVE_RISK_EXHAUSTED:['Ngân sách rủi ro còn lại không đủ cho giao dịch này.','The remaining risk budget is insufficient.'],
 NONCE_REPLAY:['Nonce đã được sử dụng; không được phép phát lại giao dịch.','The nonce has already been used; replay is not permitted.'],
 DEMO_TIMEOUT:['Lượt kiểm tra vượt thời gian chờ; chưa có kết quả thực thi được xác minh.','Verification timed out without a verified execution result.'],
 FORK_RUN_INTERRUPTED:['Lượt chạy bị gián đoạn và không được tự động gửi lại.','The run was interrupted and was not automatically resubmitted.'],
};
export function describeReason(code:string,language:Language){
 if(phrases[code])return phrases[code][language==='vi'?0:1];
 if(code.startsWith('PROOF_'))return language==='vi'?'Z3 chưa chứng minh được điều kiện an toàn yêu cầu.':'Z3 could not prove the required safety condition.';
 return language==='vi'?'Hệ thống dừng với mã kiểm tra '+code+'.':'The system stopped with verification code '+code+'.';
}
const phases:Record<string,[string,string]>={QUEUED:['Đang chờ xử lý','Queued'],PREPARING_FORK:['Chuẩn bị dữ liệu giao dịch','Preparing transaction data'],WAITING_FOR_ORACLE:['Chờ giá tham chiếu hợp lệ','Waiting for a valid reference price'],WORKFLOW_RUNNING:['Đang kiểm tra giao dịch','Verifying transaction']};
export function processingLabel(job:Job|undefined,language:Language){
 const node=workflowNodes.find(node=>node.active.includes(job?.active_stage??''));
 return (node?nodeTitle(workflowNodes.indexOf(node),language):undefined)??phases[job?.phase??'']?.[language==='vi'?0:1]??(language==='vi'?'Đang chuẩn bị lượt chạy':'Preparing the run');
}
function codes(value:Json|undefined){return Array.isArray(value)?value.filter((item):item is string=>typeof item==='string'):[];}
function record(value:Json|undefined):Evidence{return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}
export function runIssue(job:Job,language:Language='en'){
 if(!job.terminal||job.status==='CONFIRMED')return null;
 const timeline=job.workflow?.timeline??[],evidence=(name:string)=>timeline.slice().reverse().find(event=>event.stage===name)?.evidence;
 const reasons:string[]=[],stages:string[]=[];
 for(const [name,failed] of [['RISK',evidence('RISK')?.result==='FAIL'],['ITAG',!!evidence('ITAG')&&evidence('ITAG')?.verdict!=='PASS'],['PROOF_REJECTION',!!evidence('PROOF_REJECTION')],['SDE',evidence('SDE')?.verdict==='REJECT']] as const){
  if(!failed)continue;stages.push(name==='PROOF_REJECTION'?'PROOF':name);
  reasons.push(...codes(evidence(name)?.reason_codes));
  if(name==='ITAG')reasons.push(...codes(record(evidence(name)?.semantic).reason_codes));
 }
 const root=job.reason_code??job.workflow?.reason_code??evidence('REJECTION_OR_RECOVERY')?.code;
 const all=[...new Set([...reasons,...(typeof root==='string'?[root]:[])])];
 const specific=all.filter(code=>!['SECURITY_GATE_FAILED','DECISION_NOT_APPROVED'].includes(code));
 const displayCodes=specific.length?specific:all;
 const node=workflowNodes.find(node=>node.events.includes(stages[0]))??workflowNodes.find(node=>node.active.includes(job.active_stage??''));
 const semantic=record(evidence('ITAG')?.semantic),finding=record(semantic.finding);
 const explanation=['MISALIGNED','UNCERTAIN'].includes(String(semantic.verdict))&&typeof finding.reasoning_summary==='string'?finding.reasoning_summary:undefined;
 return {codes:all,reasons:displayCodes,stage:node?nodeTitle(workflowNodes.indexOf(node),language):undefined,explanation,
  unsigned:evidence('REJECTION_OR_RECOVERY')?.signed===false&&!evidence('ATTESTATION')&&!job.workflow?.outcome?.tx_hash};
}
