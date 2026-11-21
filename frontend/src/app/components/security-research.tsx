import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {ItagGraph} from './itag-graph';
import {PublicRecord} from './security-evidence';
import {object, text, units} from '@/lib/format';
import type {Evidence} from '@/lib/types';
import type {Language} from '@/lib/i18n';
import {researchArtifactAvailable} from '@/lib/security-evidence';
import './security-evidence.css';

function Source({value, language}: {value: unknown; language: Language}) {
  const src = object(value);
  return <details><summary>{language === 'vi' ? 'Nguồn artifact và dấu vân tay' : 'Artifact source and fingerprint'}</summary><a href={text(src.url)} target="_blank" rel="noreferrer">{text(src.path)}</a><p className="fact-hash">SHA-256: {text(src.sha256)}</p></details>;
}
function RecordedGraph({graph, language, candidateId, title}: {graph: Evidence; language: Language; candidateId?: string; title: string}) {
  const [open, setOpen] = useState(false);
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>{title}</summary>{open && <ItagGraph graph={graph} language={language} candidateId={candidateId}/>}</details>;
}
export function ResearchContent({data, language}: {data: Evidence; language: Language}) {
  const vi = language === 'vi', budget = object(data.budget), purpose = object(data.purpose);
  const steps = Array.isArray(budget.steps) ? budget.steps.map(object) : [];
  const [index, setIndex] = useState(0);
  const current = steps[index], deterministic = object(current?.deterministic);
  const facts = object(purpose.facts), intent = Array.isArray(facts.intent_records) ? object(facts.intent_records[0]) : {};
  const terms = object(intent.terms), candidate = object(facts.candidate), finding = object(purpose.semantic_finding);
  if (!researchArtifactAvailable(data)) return <div className="research-card" role="status">{vi ? 'Artifact thiếu hoặc không khớp phiên bản nguồn. Chưa đủ bằng chứng để hiển thị kết quả nghiên cứu.' : 'Artifact missing or source version inconsistent. Research results cannot be verified.'}</div>;
  return <div className="research-view">
    <header><span className="evidence-scope">{vi ? 'BẰNG CHỨNG NGHIÊN CỨU · CHỈ ĐỌC' : 'RESEARCH EVIDENCE · READ ONLY'}</span><h1>{vi ? 'Vì sao một giao dịch hợp lệ vẫn có thể bị dừng?' : 'Why can a valid transaction still be stopped?'}</h1><p>{vi ? 'Xem lại hai cơ chế bảo vệ qua artifact đã lưu. Các nút bên dưới chỉ đổi bản ghi đang xem; không gọi AI, ký hoặc gửi giao dịch.' : 'Inspect two protections through recorded artifacts. Controls only change the selected record; they do not call models, sign or submit transactions.'}</p></header>
    <section className="research-card" data-testid="budget-showcase"><span className="evidence-scope">{text(budget.scope)} · CHAIN {text(budget.chain_id)}</span><h2>{vi ? 'Chuỗi giao dịch vượt ngân sách tích lũy' : 'A sequence exceeds its cumulative budget'}</h2><p>{vi ? 'Ngân sách tác vụ 20 USDC. Mỗi lần hoán đổi 10 USDC có Risk PASS và Proof VERIFIED. Hai lần đầu được xác nhận trên Anvil; đề xuất thứ ba bị ITAG/SDE chặn trước ký vì tổng chi sẽ thành 30 USDC.' : 'A 20 USDC task budget. Each 10 USDC swap has Risk PASS and Proof VERIFIED. The first two confirm on Anvil; ITAG/SDE blocks the third candidate before signing because total spend would become 30 USDC.'}</p>
      <div className="recorded-step-controls" aria-label={vi ? 'Chọn bước trong bản ghi' : 'Select recorded step'}>{steps.map((step, i) => <button key={text(step.workflow)} type="button" aria-pressed={index === i} onClick={() => setIndex(i)}>{vi ? 'Bước' : 'Step'} {i + 1} · {text(step.sde)}</button>)}</div>
      {current && <div aria-live="polite"><div className="research-facts"><div>{vi ? 'Đã chi trước bước này' : 'Spent before candidate'}<strong>{units(text(deterministic.spent), 6)} USDC</strong></div><div>{vi ? 'Ngân sách còn lại' : 'Remaining budget'}<strong>{units(text(deterministic.remaining), 6)} USDC</strong></div><div>{vi ? 'Đề xuất hiện tại' : 'Current candidate'}<strong>{units(text(object(current.candidate).amount_in_base_units), 6)} USDC</strong></div><div>{vi ? 'Trạng thái ký' : 'Signing state'}<strong>{current.signed === true ? (vi ? 'Đã ký (bản ghi)' : 'Signed (recorded)') : (vi ? 'Không ký' : 'Not signed')}</strong></div></div>
      <div className="research-verdicts"><span>Risk: {text(current.risk)}</span><span>Proof: {text(current.proof)}</span><span>ITAG: {text(deterministic.verdict)}</span><span>SDE: {text(current.sde)}</span></div><p>{text(current.summary)}</p>
      <RecordedGraph key={index} graph={object(current.graph)} candidateId={text(object(current.candidate).intent_id)} language={language} title={vi ? 'Xem đồ thị lịch sử tại bước này' : 'Inspect history graph at this step'}/>
      <details><summary>{vi ? 'Lý do, lịch sử xác nhận và biên nhận gốc' : 'Reasons, confirmed history and original receipt'}</summary><PublicRecord value={{workflow: current.workflow, graph_hash: current.graph_hash, deterministic, prior_outcomes: current.prior_outcomes, receipt: current.receipt}}/></details></div>}
      <p>{vi ? 'Đây là kiểm tra ngân sách tất định với mô hình scripted trên LOCAL Anvil, không phải bằng chứng AI suy luận mục đích hay ba giao dịch public Fuji. Public broadcasts: 0.' : 'This is deterministic budget enforcement with a scripted model on LOCAL Anvil, not semantic purpose reasoning or three public Fuji transactions. Public broadcasts: 0.'}</p><Source value={budget.source} language={language}/>
    </section>
    <section className="research-card" data-testid="purpose-showcase"><span className="evidence-scope">{text(purpose.scope)}</span><h2>{vi ? 'Đúng giới hạn, nhưng sai mục đích' : 'Within limits, but outside the purpose'}</h2><p>{vi ? 'Ca lh002, lượt 1: ý định chỉ cho phép mua WAVAX để bổ sung gas. Đề xuất dùng WAVAX làm kho huấn luyện; kiểm tra tất định vẫn PASS, semantic MISALIGNED và SDE hybrid REJECT.' : 'Case lh002, repetition 1: the intent permits WAVAX exclusively for gas replenishment. The candidate states training inventory as its purpose; deterministic checks PASS, semantic assessment is MISALIGNED, and hybrid SDE returns REJECT.'}</p>
      <div className="research-verdicts"><span>Deterministic: {text(purpose.deterministic)}</span><span>Semantic: {text(purpose.semantic)}</span><span>SDE: {text(object(purpose.sde).hybrid)}</span></div>
      <p><strong>{vi ? 'Mục tiêu: ' : 'Objective: '}</strong>{text(terms.objective)}</p><p><strong>{vi ? 'Đề xuất: ' : 'Candidate: '}</strong>{text(candidate.user_goal_reason)}</p><p>{text(finding.reasoning_summary)}</p>
      <RecordedGraph graph={object(purpose.graph)} candidateId={text(finding.candidate_action_id)} language={language} title={vi ? 'Khám phá đồ thị ý định, lịch sử và nguồn' : 'Explore intent, history and provenance graph'}/>
      <details><summary>{vi ? 'Tham chiếu ngữ nghĩa và mô hình thực dùng' : 'Semantic references and recorded model'}</summary><PublicRecord value={{finding, provider: purpose.provider, sde: purpose.sde}}/></details>
      <p>{vi ? 'Lịch sử được tổng hợp cho nghiên cứu; không có public broadcast. Đây là quan sát trong mẫu nhỏ, nhãn provisional và chưa có đánh giá độc lập.' : 'History was synthesized for research; no public broadcast. This is one observation in a small sample with provisional labels and no independent review.'}</p><Source value={purpose.source} language={language}/>
    </section>
    <section className="research-card"><h2>{vi ? 'Số liệu và giới hạn bằng chứng' : 'Metrics and evidence limits'}</h2><div className="evidence-table-scroll"><table><thead><tr><th>{vi ? 'Đánh giá' : 'Evaluation'}</th><th>{vi ? 'Kết quả đã ghi nhận' : 'Recorded result'}</th><th>{vi ? 'Phạm vi' : 'Scope'}</th></tr></thead><tbody>
      <tr><th>TaskShield / Hybrid</th><td>95.67% · 300 cases<br/>Constraints-only: 95.67%</td><td>{vi ? 'Uniswap V2 được điều chỉnh; không có uplift accuracy so với constraints-only.' : 'Adapted Uniswap V2 cases; no accuracy uplift over constraints-only.'}</td></tr>
      <tr><th>Deterministic ITAG</th><td>8/12 adversarial interventions<br/>12/12 benign approvals</td><td>SCRIPTED EVALUATION · {vi ? 'Intervention gồm reject, replan và escalate; không đồng nghĩa phát hiện semantic.' : 'Intervention includes reject, replan and escalate; it is not semantic detection.'}</td></tr>
      <tr><th>Semantic ITAG v3.2</th><td>7/8 purpose-conflict observations<br/>16/19 valid graph-model responses</td><td>REAL-MODEL RESEARCH · {vi ? '4 tác vụ lặp 2 lần; 20 observations, 1 dừng upstream, 3 graph responses không hợp lệ. Không phải accuracy tổng quát.' : '4 tasks repeated twice; 20 observations, 1 stopped upstream, 3 invalid graph responses. Not general accuracy.'}</td></tr>
    </tbody></table></div><p>{vi ? 'UNKNOWN / UNAVAILABLE / ESCALATE là trạng thái chưa đủ cơ sở hoặc cần xử lý thêm, không được tính là semantic detection. Chưa có ablation để kết luận graph tốt hơn plain-history. Pipeline 12 bước là luồng xử lý, không phải 12 mô-đun bảo mật độc lập.' : 'UNKNOWN / UNAVAILABLE / ESCALATE represent unresolved or escalated outcomes, not semantic detection. No ablation establishes superiority over plain-history. The 12 workflow steps are not 12 independent security modules.'}</p>
      {Array.isArray(data.metric_sources) && data.metric_sources.map((src, i) => <Source key={i} value={src} language={language}/>)}
      <p>{vi ? 'So sánh MEV: chưa chọn được artifact có đủ baseline, stress, giả định và kết quả kiểm chứng. Không hiển thị số ước lượng hoặc gán nhãn MEV detection cho probe BadSignature.' : 'MEV comparison: no artifact with a complete baseline, stress case, assumptions and verified outcome has been selected. No estimated figures or MEV detection claims are shown for BadSignature probes.'}</p>
    </section>
  </div>;
}
export function SecurityResearch({language}: {language: Language}) {
  const result = useQuery({queryKey: ['security-research-v1'], queryFn: async () => {const response = await fetch('/evidence/security-research.json'); if (!response.ok) throw new Error('Artifact unavailable'); return await response.json() as Evidence;}, staleTime: Infinity, retry: false});
  if (!result.data) return <div className="research-card" role="status">{result.isError ? (language === 'vi' ? 'Chưa tải được artifact. Không có kết quả để xác nhận.' : 'Artifact unavailable. No result can be verified.') : (language === 'vi' ? 'Đang tải bản ghi nghiên cứu…' : 'Loading research records…')}</div>;
  return <ResearchContent data={result.data} language={language}/>;
}
