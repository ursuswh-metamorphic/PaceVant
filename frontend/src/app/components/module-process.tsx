import {lazy, Suspense, useState} from 'react';
import {Activity, CheckCircle2, CircleAlert, XCircle, ChevronDown, Clock3, GitBranch, Link2, LoaderCircle} from 'lucide-react';
import {Accordion, AccordionItem} from './ui/accordion';
import {Facts} from './evidence-facts';
import {checkTitle, jsonRows, latestChecks, publicGraph, statusText, stepEvents} from '@/lib/module-evidence';
import {object, stage, text, units} from '@/lib/format';
import type {Evidence, Job} from '@/lib/types';
import type {Language} from '@/lib/i18n';

import {BindingChain} from './security-evidence';
const InteractiveGraph = lazy(() => import('./itag-graph').then(module => ({default: module.ItagGraph})));

const at=(seconds:number,language:Language)=>new Date(seconds*1000).toLocaleTimeString(language==='vi'?'vi-VN':'en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour12:false});
export function ProcessLog({job,index,language,context}:{job:Job;index:number;language:Language;context:Evidence}){
 const vi=language==='vi',events=stepEvents(job,index),checks=latestChecks(events),last=events.filter(e=>e.kind==='completed').at(-1),started=events.find(e=>e.kind==='started');
 const [allOpen,setAllOpen]=useState(false);
 const emptyMessage=job.workflow?.activity?.length
  ?(vi?'Bước này chưa được thực hiện; quy trình đã dừng hoặc chưa chuyển tới đây.':'This stage has not run; execution stopped earlier or has not reached it.')
  :job.workflow?.timeline.length
   ?(vi?'Bản ghi này chưa có nhật ký kiểm tra con. Các kết quả và bằng chứng gốc được giữ ở phần đầu ra.':'This record has no detailed process log. Original results remain in the output below.')
   :(vi?'Chưa bắt đầu kiểm tra ở bước này. Thông tin sẽ cập nhật khi backend xác minh xong dữ liệu nguồn.':'This stage has not started. Updates follow backend source verification.');
 return <section className="module-process" aria-label={vi?'Nhật ký xử lý thực tế':'Actual processing log'}>
  <div className="process-heading"><h4><Activity size={16}/>{vi?'Quá trình xử lý thực tế':'Actual processing'}</h4>{last?.duration_ms!==undefined&&<span><Clock3 size={12}/>{(last.duration_ms/1000).toLocaleString(vi?'vi-VN':'en-GB',{maximumFractionDigits:3})} {vi?'giây':'seconds'}</span>}</div>
  {started&&<p className="process-time-range">{vi?'Bắt đầu: ':'Started: '}{at(started.created_at,language)}{last?' · '+(vi?'Kết thúc: ':'Finished: ')+at(last.created_at,language):''} · UTC+7</p>}
  {!events.length?<p className="module-note">{emptyMessage}</p>:<>
   <p className="module-note">{vi?'Thời điểm, thời gian xử lý và kết quả dưới đây do backend ghi nhận.':'Times, durations and results below are recorded by the backend.'}</p>
   {!!checks.length&&<button type="button" className="process-expand" aria-pressed={allOpen} onClick={()=>setAllOpen(!allOpen)}>{allOpen?(vi?'Thu gọn thông số kiểm tra':'Collapse check parameters'):(vi?'Mở thông số các kiểm tra':'Expand check parameters')}</button>}
   <ol className="process-checks">{checks.map(check=>{
    const running=check.status==='RUNNING'&&!job.terminal;
    const Mark=running?LoaderCircle:check.status==='PASS'?CheckCircle2:check.status==='FAIL'?XCircle:CircleAlert;
    return <li key={`${check.stage}:${check.check_ref??check.check_id}`} data-status={running?'RUNNING':check.status==='RUNNING'?'UNKNOWN':check.status}>
     <details open={allOpen}>
      <summary><span className="process-state-icon" aria-hidden="true"><Mark size={15} className={running?'animate-spin':''}/></span><span className="process-check-name">{checkTitle(check.check_id,language)}<small>{at(check.created_at,language)} · UTC+7{check.duration_ms!==undefined?' · '+check.duration_ms.toLocaleString(vi?'vi-VN':'en-GB')+' ms':''}</small></span><span className="process-state-label">{statusText(check.status,language,job.terminal)}</span><ChevronDown size={14}/></summary>
      <div className="check-comparison"><div><h5>{vi?'Điều kiện cần đạt':'Expected condition'}</h5>{check.expected==null?<p>{vi?'Xem phạm vi kiểm tra và bằng chứng gốc.':'See check scope and original evidence.'}</p>:<Facts value={check.expected} language={language} context={context}/>}</div><div><h5>{vi?'Dữ liệu / kết quả quan sát':'Observed data / result'}</h5>{check.observed==null?<p>{running?(vi?'Đang chờ kết quả từ backend.':'Waiting for backend result.'):(vi?'Backend chưa cung cấp dữ liệu bổ sung.':'No additional data was recorded.')} </p>:<Facts value={check.observed} language={language} context={context}/>}</div></div>
      <p className="process-reference">{check.check_id}{check.check_ref?' · '+check.check_ref:''}</p>
     </details>
    </li>;
   })}</ol>
   {!checks.length&&<p className="module-note">{vi?'Backend đã ghi nhận bắt đầu bước này; chưa có kết quả kiểm tra con.':'The backend recorded this stage starting; no check results yet.'}</p>}
  </>}
 </section>;
}
export function IntentGraph({job,language,context}:{job:Job;language:Language;context:Evidence}){
 const vi=language==='vi',graph=publicGraph(job),nodes=jsonRows(graph.nodes),edges=jsonRows(graph.edges);
 if(!nodes.length)return null;
 const kind:Record<string,[string,string]>={AUTHENTICATED_USER_INTENT:['Yêu cầu đã xác thực','Authenticated request'],AGENT_ACTION:['Hành động do AI đề xuất','AI-proposed action'],MANDATE:['Quyền do chủ ví cấp','Owner authority'],TRANSACTION_OUTCOME:['Giao dịch trong lịch sử','Historical transaction']};
 const trust:Record<string,[string,string]>={AUTHENTICATED:['Đã xác thực nguồn','Authenticated source'],UNTRUSTED:['Cần được kiểm tra','Untrusted proposal'],VERIFIED_RECORD:['Bản ghi đã xác minh','Verified record']};
 const name=(id:string)=>{const n=nodes.find(n=>n.node_id===id);return n?(kind[text(n.kind)]?.[vi?0:1]??text(n.kind)):id;};
 return <section className="module-special"><h4><GitBranch size={16}/>{vi?'Đồ thị ý định và nguồn gốc bằng chứng':'Intent and provenance graph'}</h4><p className="module-note">{vi?'Các nút và quan hệ được backend ghi nhận; đề xuất của AI luôn tách khỏi quyền chủ ví.':'Backend-recorded nodes and relationships keep AI proposals separate from owner authority.'}</p>
  <Suspense fallback={<p>{vi?'Đang tải đồ thị…':'Loading ITAG…'}</p>}><InteractiveGraph graph={graph} language={language}/></Suspense><details><summary>{vi?'Danh sách nguồn dữ liệu':'Source record list'}</summary><ol className="provenance-nodes">{nodes.map((node,index)=><li key={text(node.node_id)}><span className="provenance-number">{index+1}</span><div><strong>{name(text(node.node_id))}</strong><span className="provenance-trust">{trust[text(node.trust)]?.[vi?0:1]??text(node.trust)}</span><code>{text(node.node_id)}</code><Accordion type="single" collapsible><AccordionItem value="node" title={vi?'Nguồn dữ liệu và tham chiếu':'Source data and references'}><Facts value={{evidence_refs:node.evidence_refs??[],...object(node.data)}} language={language} context={context}/></AccordionItem></Accordion></div></li>)}</ol></details>
  {!!edges.length&&<ul className="provenance-links">{edges.map((edge,index)=><li key={index}><Link2 size={14}/><span>{name(text(edge.source))} <span aria-hidden="true">→</span> {name(text(edge.target))}<small>{edge.kind==='AUTHORIZES'?(vi?'Quan hệ cấp quyền đã ghi nhận':'Recorded authorization relationship'):text(edge.kind)} · {text(edge.provenance)}</small></span></li>)}</ul>}
  {!!stage(job.workflow,'ITAG')?.graph_hash&&<div className="binding-hash"><span>{vi?'Dấu vân tay đồ thị':'Graph hash'}</span><code>{text(stage(job.workflow,'ITAG')?.graph_hash)}</code></div>}
 </section>;
}
export function OracleEvidence({job,language,context}:{job:Job;language:Language;context:Evidence}){
 const vi=language==='vi',oracle=object(context.oracle),feeds=jsonRows(oracle.oracle_feeds);
 if(!feeds.length)return null;
 const observed=Number(context.server_time??context.timestamp);
 return <section className="module-special"><h4><Activity size={16}/>{vi?'Nguồn giá Chainlink độc lập':'Independent Chainlink reference'}</h4><p className="module-note">{vi?'Giá Chainlink được kiểm tra độc lập với báo giá LFJ. Tuổi giá tính tại thời điểm backend đọc dữ liệu, không phải lúc xem lại.':'Chainlink is verified independently of LFJ. Age is measured at the backend observation time.'}</p><div className="oracle-observations">{feeds.map(feed=><div key={text(feed.feed)}><strong>{text(feed.description)}</strong><span className="oracle-price">{units(text(feed.answer_raw),Number(feed.decimals),8)} USD</span><dl><div><dt>{vi?'Tuổi giá khi quan sát':'Age at observation'}</dt><dd>{Number.isFinite(observed)&&feed.updated_at!==undefined?Math.max(0,observed-Number(feed.updated_at))+' '+(vi?'giây':'seconds'):'—'}</dd></div><div><dt>{vi?'Tuổi tối đa của nguồn':'Feed age limit'}</dt><dd>{text(feed.max_age_seconds)} {vi?'giây':'seconds'}</dd></div><div><dt>{vi?'Vòng cập nhật':'Round'}</dt><dd>{text(feed.round_id)}</dd></div></dl></div>)}</div><Facts value={{oracle_valid_until:context.oracle_valid_until??null,max_oracle_age:object(context.proof_policy).max_oracle_age??null,price_intervals:context.price_intervals??null}} language={language} context={context}/></section>;
}
export function EvidenceBindings({job,language}:{job:Job;language:Language}){
 return <BindingChain job={job} language={language}/>;
}

export function ModelMetrics({job,language,context}:{job:Job;language:Language;context:Evidence}){
 const vi=language==='vi',metrics=job.runtime_metrics,inference=object(metrics?.inference);
 if(!metrics)return null;
 return <section className="module-special"><h4><Clock3 size={16}/>{vi?'Tài nguyên và thời gian đã đo':'Measured time and resources'}</h4><p className="module-note">{vi?'Thời gian gồm cả chuẩn bị môi trường và chờ nguồn dữ liệu. Token do nhà cung cấp báo cáo, không phải hóa đơn USD.':'Time includes setup and source waiting. Tokens are provider-reported usage, not a USD invoice.'}</p><Facts value={{worker_wall_seconds:metrics.worker_wall_seconds??null,call_count:inference.call_count??null,reported_token_usage:inference.reported_token_usage??null}} language={language} context={context}/><Accordion type="single" collapsible className="technical-evidence"><AccordionItem value="calls" title={vi?'Xem từng lời gọi mô hình':'Inspect model calls'}><Facts value={inference.calls??[]} language={language} context={context}/></AccordionItem></Accordion></section>;
}
