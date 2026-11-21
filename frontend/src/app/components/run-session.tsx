import {CircleAlert, CheckCircle2, LoaderCircle, Radio, ShieldX, ArrowRight} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Accordion, AccordionItem} from '@/components/ui/accordion';
import {describeReason, processingLabel, runIssue} from '@/lib/run-feedback';
import type {Job,ScenarioId} from '@/lib/types';
import type {Language} from '@/lib/i18n';
import {dictionary} from '@/lib/i18n';

export function BlockReason({job,language}:{job:Job;language:Language}){
 const issue=runIssue(job),vi=language==='vi';if(!issue)return null;
 return <section className="run-block-reason" data-testid="run-block-reason">
  <h3><ShieldX size={16}/>{vi?'Vì sao lượt chạy dừng?':'Why did the run stop?'}</h3>
  <p className="block-stage">{vi?'Bước kiểm tra: ':'Verification step: '}<strong>{issue.stage??processingLabel(job,language)}</strong></p>
  {issue.reasons.length?<ul>{issue.reasons.map(code=><li key={code}>{describeReason(code,language)}</li>)}</ul>:<p>{vi?'Backend chưa cung cấp nguyên nhân cụ thể. Xem bằng chứng để kiểm tra trạng thái đã ghi nhận.':'The backend has not supplied a specific reason. Inspect the recorded evidence.'}</p>}
  {issue.unsigned&&<p className="block-unsigned"><CheckCircle2 size={14}/>{vi?'Lượt chạy dừng trước khi ký giao dịch.':'The run stopped before transaction signing.'}</p>}
  {issue.explanation&&<blockquote className="block-explanation">{issue.explanation}</blockquote>}
  {!!issue.codes.length&&<Accordion type="single" collapsible><AccordionItem value="codes" title={vi?'Mã kiểm tra từ hệ thống':'Backend verification codes'}><ul className="block-codes">{issue.codes.map(code=><li key={code}>{code}</li>)}</ul></AccordionItem></Accordion>}
 </section>;
}
export function RunSession({job,scenario,restoring,disconnected,needsResume,pending,onResume,onDemo,onClear,language,showDemo}:{job?:Job;scenario:ScenarioId;restoring:boolean;disconnected:boolean;needsResume:boolean;pending:boolean;onResume:()=>void;onDemo:()=>void;onClear?:()=>void;language:Language;showDemo:boolean}){
 const vi=language==='vi',t=dictionary[language],terminal=!!job?.terminal,issue=job?runIssue(job):null;
 const Icon=disconnected?CircleAlert:!terminal?LoaderCircle:job?.status==='CONFIRMED'?CheckCircle2:CircleAlert;
 const title=disconnected?(vi?'Tạm mất kết nối lượt chạy':'Run updates disconnected'):needsResume?(vi?'Yêu cầu của bạn đã được lưu':'Your request is saved'):restoring?(vi?'Đang khôi phục phiên của bạn':'Restoring your run'):!terminal?(vi?'Kịch bản đang được xử lý':'Your scenario is running'):job?.status==='CONFIRMED'?(vi?'Kịch bản đã hoàn tất':'Scenario completed'):job?.status==='REJECTED'?(vi?'Giao dịch đã bị chặn':'Transaction blocked'):(vi?'Lượt chạy chưa được xác nhận thành công':'Run has no confirmed success');
 const detail=disconnected?(vi?'Đang giữ dữ liệu gần nhất. Kết nối lại để kiểm tra đúng phiên này.':'Keeping the last recorded data. Reconnect to this same run.'):needsResume?(vi?'Chưa xác nhận được job. Tiếp tục để kiểm tra lại yêu cầu đã lưu; không tạo yêu cầu khác.':'The job is not confirmed yet. Resume the saved request to check its status safely.'):restoring?(vi?'Đang lấy trạng thái đã lưu từ hệ thống; không gửi thêm giao dịch.':'Retrieving the saved run; no new transaction is submitted.'):issue?.reasons[0]?describeReason(issue.reasons[0],language):terminal?(vi?'Kết quả và bằng chứng đã được ghi nhận.':'The result and evidence have been recorded.'):processingLabel(job,language);
 return <section className={'run-session '+(disconnected?'run-session-warning':terminal?job?.status==='CONFIRMED'?'run-session-success':job?.status==='REJECTED'?'run-session-blocked':'run-session-warning':'run-session-active')} data-testid="run-session" role="status" aria-live="polite" aria-atomic="true">
  <span className="run-session-icon"><Icon size={21} className={!terminal&&!disconnected&&!needsResume?'animate-spin':''}/></span>
  <div className="run-session-copy"><div><strong>{title}</strong><span className="run-scenario-name">{t[scenario]}{job?.environment==='REAL_FUJI_EXECUTION'?' · Avalanche Fuji':''}</span></div><p>{detail}</p></div>
  <div className="run-session-actions">{job&&<span className="run-session-id" title={job.job_id}><Radio size={12}/>{vi?'Phiên ':'Run '}{job.job_id.slice(-8)}</span>}{(needsResume||disconnected)&&!onClear&&<Button variant="outline" size="sm" onClick={onResume} disabled={pending}>{needsResume?(vi?'Tiếp tục yêu cầu':'Resume request'):(vi?'Kết nối lại':'Reconnect')}</Button>}{onClear&&<Button variant="outline" size="sm" onClick={onClear}>{vi?'Về chọn kịch bản':'Back to scenarios'}</Button>}{showDemo&&<Button variant="ghost" size="sm" onClick={onDemo}>{terminal?(vi?'Xem kết quả':'View result'):(vi?'Về lượt chạy':'View run')}<ArrowRight size={14}/></Button>}</div>
 </section>;
}
