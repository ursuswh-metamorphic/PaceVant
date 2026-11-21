import {bindingChain, bindingLabel, compareBinding, evidenceScope, publicEvidence, riskChecks} from '@/lib/security-evidence';
import {formatGasPaid, object, stage, text} from '@/lib/format';
import {checkTitle, statusText} from '@/lib/module-evidence';
import type {Job} from '@/lib/types';
import type {Language} from '@/lib/i18n';
import {Facts} from './evidence-facts';
import './security-evidence.css';

export function ScopeBadge({job}: {job?: Job}) {
  return <span className="evidence-scope" data-testid="evidence-scope">{evidenceScope(job)}</span>;
}

export function PublicRecord({value}: {value: unknown}) {
  return <pre className="evidence-json">{JSON.stringify(publicEvidence(value) ?? {status: 'Unavailable'}, null, 2)}</pre>;
}

export function BindingChain({job, language}: {job?: Job; language: Language}) {
  const vi = language === 'vi';
  return <section className="module-special security-binding">
    <h4>{vi ? 'Chuỗi ràng buộc bằng chứng' : 'Evidence binding chain'}</h4>
    <p className="module-note">{vi ? 'Đối chiếu các trường công khai do backend ghi nhận. Thiếu dữ liệu không có nghĩa là khớp. Không hiển thị chữ ký.' : 'Compare backend-recorded public commitments. Missing evidence never means a match. Signatures are excluded.'}</p>
    <ol className="security-chain">{bindingChain(job).map(link => <li key={link.id} data-binding={link.state}>
      <details><summary><strong>{link.labels[vi ? 0 : 1]}</strong><span>{bindingLabel(link.state, language)}</span><code>{text(link.expected ?? link.observed, vi ? 'Chưa có hash' : 'Hash unavailable')}</code></summary><PublicRecord value={link.raw}/></details>
    </li>)}</ol>
  </section>;
}

export function HistoricalProbeEvidence({job, language}: {job: Job; language: Language}) {
  const vi = language === 'vi', probe = job.attack_evidence;
  if (!probe) return null;
  const match = compareBinding(probe.expected_selector, probe.observed_selector);
  const verified = job.status === 'REJECTED' && probe.method === 'eth_call' && match === 'match' && probe.control === 'SUCCESS';
  const replay = probe.expected_error === 'NonceReplay()';
  return <section className="module-special probe-evidence" data-testid="probe-details">
    <h4>{vi ? 'Đối chứng → Biến đổi → Cơ chế chặn' : 'Control → Mutation → Enforcement'}</h4>
    <p className="module-note">HISTORICAL FUJI ETH_CALL · {vi ? 'Không có giao dịch mới. Các bước AI không chạy.' : 'No new transaction. AI stages do not run.'}</p>
    <div className="probe-verdict" data-binding={verified ? 'match' : match === 'missing' ? 'missing' : 'mismatch'}>{verified ? (vi ? 'Khớp lỗi dự kiến, đối chứng thành công' : 'Expected revert matched; control succeeded') : (vi ? 'Chưa xác nhận đầy đủ kết quả kiểm thử' : 'Test result not fully verified')}</div>
    <details><summary>{vi ? '1. Giao dịch gốc và đối chứng' : '1. Original transaction and control'}</summary><Facts value={{operation: job.workflow?.intent.operation ?? job.request?.operation ?? null, seed_tx_hash: probe.seed_tx_hash ?? null, source_block: probe.source_block ?? null, control_block: probe.control_block ?? null, control: probe.control ?? null, canonical_seed_receipt: probe.canonical_seed_receipt ?? null}} language={language}/></details>
    <details><summary>{vi ? '2. Trường thay đổi và chữ ký gốc' : '2. Mutation and original signature'}</summary><Facts value={{field: probe.field ?? null, original: probe.original ?? null, candidate: probe.candidate ?? null, same_original_signature: probe.same_original_signature ?? null}} language={language}/></details>
    <details><summary>{vi ? '3. Lỗi dự kiến và quan sát' : '3. Expected and observed revert'}</summary><Facts value={{expected_error: probe.expected_error ?? null, expected_selector: probe.expected_selector ?? null, observed_selector: probe.observed_selector ?? null}} language={language}/></details>
    <p className="module-note">{replay
      ? (vi ? 'NonceReplay chứng minh cơ chế chống phát lại trên trạng thái lịch sử.' : 'NonceReplay demonstrates nonce replay enforcement against historical state.')
      : (vi ? 'BadSignature chứng minh dữ liệu đã ký không thể bị sửa mà vẫn giữ chữ ký gốc. Kết quả này không chứng minh AI phát hiện tấn công, hay một cổng rủi ro chuyên biệt đã chạy.' : 'BadSignature demonstrates signed-data integrity. It does not establish AI attack detection or execution of a specialized risk gate.')}</p>
  </section>;
}

export function RiskComparison({job, language}: {job?: Job; language: Language}) {
  const vi = language === 'vi', checks = riskChecks(job);
  return <details className="module-special risk-comparison"><summary>{vi ? 'Điều kiện rủi ro: yêu cầu và quan sát' : 'Risk conditions: expected and observed'}</summary>
    <p className="module-note">{vi ? 'Tiền thanh toán, tổn thất giao dịch và gas được hạch toán riêng. Chỉ hiển thị những phép kiểm tra có dữ liệu nguồn.' : 'Payment principal, trading loss and gas are tracked separately. Only checks with recorded evidence appear below.'}</p>
    {checks.length ? <div className="evidence-table-scroll"><table><thead><tr>{(vi ? ['Kiểm tra', 'Điều kiện', 'Quan sát', 'Kết quả'] : ['Check', 'Expected', 'Observed', 'Verdict']).map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{checks.map(check => <tr key={check.check_ref ?? check.check_id}><th>{checkTitle(check.check_id, language)}</th><td><Facts value={check.expected!} language={language}/></td><td><Facts value={check.observed!} language={language}/></td><td>{statusText(check.status, language, job?.terminal)}</td></tr>)}</tbody></table></div> : <p>{vi ? 'Chưa có cặp điều kiện / quan sát được ghi nhận.' : 'No expected / observed comparison is recorded.'}</p>}
  </details>;
}

export function FormalScope({job, language}: {job?: Job; language: Language}) {
  const vi = language === 'vi', proof = stage(job?.workflow, 'PROOF') ?? stage(job?.workflow, 'PROOF_REJECTION');
  if (!proof) return null;
  return <section className="module-special"><h4>{vi ? 'Phạm vi chứng minh Z3 và Φ' : 'Z3 and Φ proof scope'}</h4>
    <p className="module-note">{vi ? 'SAT: miền giả định có nghiệm. UNSAT ở truy vấn vi phạm: không tìm thấy vi phạm trong miền đã định. UNKNOWN không cho phép ký. Bảo đảm chỉ áp dụng với các giả định và điều kiện Φ đã ghi nhận.' : 'SAT: assumptions are satisfiable. UNSAT for a violation query: no violation exists within the bounded domain. UNKNOWN cannot authorize signing. Guarantees depend on the recorded assumptions and Φ.'}</p>
    <Facts value={{assumptions: proof.assumptions ?? null, phi_hash: proof.phi_hash ?? null, proof_hash: proof.proof_hash ?? null}} language={language}/>
    <details><summary>{vi ? 'Xem điều kiện Φ đã biên dịch' : 'Inspect compiled Φ'}</summary><PublicRecord value={proof.phi}/></details>
  </section>;
}

export function ReceiptGas({job, language}: {job?: Job; language: Language}) {
  const outcome = job?.workflow?.outcome;
  if (!outcome || !['CONFIRMED', 'REVERTED'].includes(outcome.status)) return null;
  return <dl className="fact-rows"><div><dt>{language === 'vi' ? 'Gas thực tế từ biên nhận' : 'Actual receipt gas'}</dt><dd>{formatGasPaid(object(outcome.system_gas_expense).actual_cost_wei, language)}</dd></div><div><dt>Tx hash</dt><dd className="fact-hash">{text(outcome.tx_hash)}</dd></div></dl>;
}
