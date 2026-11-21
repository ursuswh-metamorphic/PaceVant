import {useMemo, useState} from 'react';
import {AnimatePresence, motion, useReducedMotion} from 'motion/react';
import {
  Activity,
  BarChart3,
  Clock3,
  Database,
  ExternalLink,
  FileCheck2,
  History,
  Link2,
  LoaderCircle,
  RotateCcw,
} from 'lucide-react';
import {date, publicExplorer, short, stage, units} from '@/lib/format';
import {PHASES, workflowProgress} from '@/lib/phases';
import {BlockReason} from './run-session';
import {CopyHash} from './evidence';
import {VerdictMark} from './illustrations';
import {stateIcons} from './pipeline-icons';
import {processingLabel} from '@/lib/run-feedback';
import {dictionary, type Language} from '@/lib/i18n';
import type {Job, SourceSnapshot} from '@/lib/types';

const copy = {
  vi: {
    status: 'Kết quả kiểm tra',
    statusHint: 'Tổng hợp kết quả bảo mật của giao dịch.',
    scenario: 'Kịch bản',
    details: 'Xem bằng chứng chi tiết',
    history: 'Bằng chứng thực thi',
    historyHint: 'Hồ sơ kiểm tra và bằng chứng bảo mật của từng lượt chạy, lấy trực tiếp từ backend.',
    refresh: 'Làm mới',
    time: 'Thời gian',
    operation: 'Kịch bản',
    environment: 'Môi trường',
    result: 'Kết quả',
    last: 'Bước ghi nhận cuối',
    transaction: 'Giao dịch',
    emptyHistory: 'Chưa có hồ sơ kiểm tra',
    emptyHistoryHint: 'Mỗi lượt chạy ở Live Demo sẽ được lưu tại đây cùng bằng chứng để đối soát.',
    emptyFilter: 'Không có lượt chạy nào khớp bộ lọc này.',
    demo: 'Chạy kịch bản đầu tiên',
    error: 'Không tải được lịch sử',
    errorHint: 'Hãy làm mới để tải lại dữ liệu từ backend.',
    pending: 'Đang tải hồ sơ…',
    payment: 'Thanh toán USDC',
    swap: 'Hoán đổi token',
    guard: 'Kiểm tra bảo mật',
    recorded: 'Bản ghi xác minh',
    noStage: 'Chưa ghi nhận',
    all: 'Tất cả',
    confirmedFilter: 'Đã xác nhận',
    blockedFilter: 'Bị chặn',
    otherFilter: 'Khác',
    CONFIRMED: 'Đã xác nhận',
    REJECTED: 'Bị chặn',
    UNKNOWN: 'Chưa xác định',
    INTERRUPTED: 'Bị gián đoạn',
    UNAVAILABLE: 'Chưa thể kiểm tra',
    FAILED: 'Không hoàn tất',
    RUNNING: 'Đang kiểm tra',
    QUEUED: 'Đang chuẩn bị',
  },
  en: {
    status: 'Verification result',
    statusHint: 'Security summary for this transaction.',
    scenario: 'Scenario',
    details: 'Inspect full evidence',
    history: 'Execution evidence',
    historyHint: 'Verification records and security evidence for every run, read directly from the backend.',
    refresh: 'Refresh',
    time: 'Time',
    operation: 'Scenario',
    environment: 'Environment',
    result: 'Result',
    last: 'Last recorded step',
    transaction: 'Transaction',
    emptyHistory: 'No verification records yet',
    emptyHistoryHint: 'Every Live Demo run is stored here with its evidence for review.',
    emptyFilter: 'No runs match this filter.',
    demo: 'Run the first scenario',
    error: 'History unavailable',
    errorHint: 'Refresh to reload records from the backend.',
    pending: 'Loading records…',
    payment: 'USDC Payment',
    swap: 'Token Swap',
    guard: 'Security Guard',
    recorded: 'Verified recording',
    noStage: 'Not recorded',
    all: 'All',
    confirmedFilter: 'Confirmed',
    blockedFilter: 'Blocked',
    otherFilter: 'Other',
    CONFIRMED: 'Confirmed',
    REJECTED: 'Blocked',
    UNKNOWN: 'Unknown',
    INTERRUPTED: 'Interrupted',
    UNAVAILABLE: 'Unavailable',
    FAILED: 'Not completed',
    RUNNING: 'Verifying',
    QUEUED: 'Preparing',
  },
} as const;

const stages: Record<string, [string, string]> = {
  PLANNING: ['Phân tích yêu cầu', 'Analyzing request'],
  BUILD: ['Dựng giao dịch', 'Building transaction'],
  SIMULATION: ['Mô phỏng EVM', 'EVM simulation'],
  ITAG: ['Kiểm tra ý định', 'Intent alignment'],
  RISK: ['Kiểm tra rủi ro', 'Risk verification'],
  PROOF: ['Xác minh Z3', 'Z3 verification'],
  SDE: ['Quyết định bảo mật', 'Security decision'],
  ATTESTATION: ['Ký EIP-712', 'EIP-712 attestation'],
  EXACT_SIGNED_PREFLIGHT: ['Kiểm tra trước thực thi', 'Exact preflight'],
  RELAY: ['Gửi giao dịch', 'Submitting transaction'],
  OUTCOME: ['Đối soát kết quả', 'Receipt reconciliation'],
  RECONCILIATION: ['Đối soát kết quả', 'Receipt reconciliation'],
  OWNER_AUTHORITY: ['Kiểm tra quyền hạn', 'Authority check'],
  AGENT_PROPOSAL: ['Đề xuất của AI', 'AI proposal'],
  PROOF_REJECTION: ['Xác minh Z3', 'Z3 verification'],
};

function stageLabel(value: string | undefined, language: Language) {
  return value ? (stages[value]?.[language === 'vi' ? 0 : 1] ?? value) : copy[language].noStage;
}

function networkLabel(environment: Job['environment'] | undefined, language: Language) {
  const vi = language === 'vi';
  switch (environment) {
    case 'REAL_FUJI_EXECUTION':
      return 'Avalanche Fuji';
    case 'ANVIL_FORK':
      return vi ? 'Fuji fork cô lập' : 'Isolated Fuji fork';
    case 'VERIFIED_REPLAY':
      return vi ? 'Bản ghi xác minh' : 'Verified replay';
    case 'LOCAL_TEST':
      return vi ? 'Kiểm thử cục bộ' : 'Local test';
    default:
      return vi ? 'Chưa xác định' : 'Not set';
  }
}

type Tone = 'idle' | 'running' | 'approved' | 'passed' | 'rejected' | 'failed' | 'unknown';

/** The headline verdict, derived only from fields the backend reports. */
function verdictFor(job: Job | undefined, language: Language): {tone: Tone; title: string; detail: string} {
  const vi = language === 'vi';
  if (!job)
    return {
      tone: 'idle',
      title: vi ? 'Chưa bắt đầu' : 'Not started',
      detail: vi
        ? 'Chọn kịch bản bên trái và nhấn Chạy kịch bản để bắt đầu kiểm tra.'
        : 'Choose a scenario on the left and select Run scenario to begin.',
    };
  const outcome = job.workflow?.outcome;
  const sde = stage(job.workflow, 'SDE');
  if (!job.terminal) {
    if (job.status === 'QUEUED')
      return {tone: 'running', title: vi ? 'Đang chuẩn bị' : 'Preparing', detail: processingLabel(job, language)};
    if (job.active_stage === 'RELAY')
      return {
        tone: 'approved',
        title: vi ? 'Đang gửi giao dịch' : 'Submitting transaction',
        detail: vi
          ? 'Relayer đang gửi giao dịch đã ký; PolicyVault sẽ kiểm tra lại khi thực thi.'
          : 'The Relayer is submitting the signed transaction; PolicyVault re-enforces at execution.',
      };
    if (sde?.verdict === 'APPROVE')
      return {
        tone: 'approved',
        title: vi ? 'Đã duyệt để thực thi' : 'Approved for execution',
        detail: vi
          ? 'Quyết định bảo mật cho phép ký; trạng thái vẫn được kiểm tra lại trước khi gửi.'
          : 'The security decision allows signing; state is revalidated again before submission.',
      };
    return {tone: 'running', title: vi ? 'Đang xác minh' : 'Verifying', detail: processingLabel(job, language)};
  }
  if (job.status === 'CONFIRMED') {
    const onChain = job.environment === 'REAL_FUJI_EXECUTION';
    return {
      tone: 'passed',
      title: onChain
        ? vi ? 'Đã xác nhận on-chain' : 'Confirmed on-chain'
        : job.environment === 'VERIFIED_REPLAY'
          ? vi ? 'Bản ghi đã xác nhận' : 'Recorded confirmation'
          : vi ? 'Đã xác nhận trên fork' : 'Confirmed on fork',
      detail: onChain
        ? vi ? 'Receipt đã được đọc và đối soát trên Avalanche Fuji.' : 'The receipt was read and reconciled on Avalanche Fuji.'
        : vi ? 'Kết quả và bằng chứng đã được ghi nhận.' : 'The result and evidence have been recorded.',
    };
  }
  if (job.status === 'REJECTED')
    return {
      tone: 'rejected',
      title: vi ? 'Bị chặn bởi policy' : 'Rejected by policy',
      detail: vi ? 'Một lớp kiểm tra đã từ chối giao dịch. Xem lý do bên dưới.' : 'A security layer rejected the transaction. See the reason below.',
    };
  if (outcome && !['CONFIRMED', 'REVERTED'].includes(outcome.status))
    return {
      tone: 'unknown',
      title: vi ? 'Đã gửi, chưa xác nhận' : 'Submitted, not confirmed',
      detail: vi ? 'Giao dịch đã được gửi nhưng chưa có receipt xác nhận.' : 'The transaction was submitted but no confirming receipt is recorded.',
    };
  if (job.status === 'UNKNOWN' || job.status === 'INTERRUPTED')
    return {
      tone: 'unknown',
      title: job.status === 'INTERRUPTED' ? (vi ? 'Bị gián đoạn' : 'Interrupted') : vi ? 'Chưa xác định' : 'Unresolved',
      detail: vi ? 'Kết quả được giữ ở trạng thái chưa xác định, không tự coi là thành công.' : 'The outcome stays unresolved; it is never assumed successful.',
    };
  return {
    tone: 'failed',
    title: vi ? 'Không hoàn tất' : 'Failed',
    detail: vi ? 'Lượt chạy dừng trước khi có kết quả được xác minh.' : 'The run stopped before a verified result.',
  };
}

function chainStatus(job: Job | undefined, language: Language) {
  const vi = language === 'vi';
  const outcome = job?.workflow?.outcome;
  if (outcome?.status === 'CONFIRMED') return {tone: 'passed', label: vi ? 'Đã xác nhận' : 'Confirmed'};
  if (outcome?.status === 'REVERTED') return {tone: 'rejected', label: vi ? 'Bị hoàn tác' : 'Reverted'};
  if (outcome) return {tone: 'unknown', label: vi ? 'Chưa xác nhận' : 'Unconfirmed'};
  if (job && !job.terminal && job.active_stage === 'RELAY') return {tone: 'running', label: vi ? 'Đang gửi' : 'Submitting'};
  return {tone: 'idle', label: vi ? 'Chưa gửi' : 'Not submitted'};
}

export function ExecutionStatus({
  job,
  language,
  mode,
  onEvidence,
}: {
  job?: Job;
  language: Language;
  mode?: Job['environment'];
  onEvidence: () => void;
}) {
  const t = copy[language];
  const d = dictionary[language];
  const vi = language === 'vi';
  const reduced = useReducedMotion();
  const explorer = job ? publicExplorer(job) : null;
  const verdict = verdictFor(job, language);
  const progress = workflowProgress(job);
  const chain = chainStatus(job, language);
  const risk = stage(job?.workflow, 'RISK');
  const outcome = job?.workflow?.outcome;
  const percent = Math.round((progress.passed / progress.total) * 100);
  const fillTone = verdict.tone === 'rejected' || verdict.tone === 'failed' ? verdict.tone : verdict.tone === 'passed' ? 'passed' : 'running';

  return (
    <aside className="panel status-panel" data-testid="status-panel" aria-label={t.status}>
      <div className="panel-head">
        <span className="panel-head-icon" aria-hidden="true">
          <Activity size={17} />
        </span>
        <div>
          <h2>{t.status}</h2>
          <p>{t.statusHint}</p>
        </div>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={verdict.tone + verdict.title}
          className="verdict"
          data-tone={verdict.tone}
          role="status"
          aria-live="polite"
          initial={reduced ? false : {opacity: 0, y: 4}}
          animate={{opacity: 1, y: 0}}
          exit={reduced ? undefined : {opacity: 0, y: -4}}
          transition={{duration: 0.22, ease: [0.16, 1, 0.3, 1]}}
        >
          <VerdictMark tone={verdict.tone} />
          <div>
            <strong>{verdict.title}</strong>
            <p>{verdict.detail}</p>
          </div>
        </motion.div>
      </AnimatePresence>

      <section className="panel-section" style={{borderTop: 0}} aria-label={vi ? 'Tiến độ kiểm tra' : 'Verification progress'}>
        <div className="progress-head">
          {vi ? 'Tiến độ kiểm tra' : 'Verification progress'}
          <span>
            {progress.passed}/{progress.total} {vi ? 'module' : 'modules'}
          </span>
        </div>
        <div
          className="progress-track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={progress.total}
          aria-valuenow={progress.passed}
          aria-label={vi ? 'Số module đã xác minh' : 'Modules verified'}
        >
          <div className="progress-fill" data-tone={fillTone} style={{width: percent + '%'}} />
        </div>
        <ol className="phase-progress">
          {PHASES.map((phase, index) => {
            const state = progress.phases[index];
            const Icon = stateIcons[state];
            return (
              <li key={phase.title[1]} data-state={state}>
                <span className="state-glyph" data-state={state} aria-hidden="true">
                  {state !== 'idle' && state !== 'skipped' && (
                    <Icon size={11} strokeWidth={3} className={state === 'running' ? 'animate-spin' : ''} />
                  )}
                </span>
                <span>{phase.title[vi ? 0 : 1]}</span>
                <span>{state === 'passed' ? (vi ? 'Hoàn thành' : 'Complete') : d[state]}</span>
              </li>
            );
          })}
        </ol>
      </section>

      {risk && (
        <section className="panel-section">
          <div className="panel-label">
            <span>
              <BarChart3 size={15} aria-hidden="true" />
              {vi ? 'Đánh giá rủi ro' : 'Economic risk'}
            </span>
            <span className={'chip tone-' + (risk.result === 'FAIL' ? 'rejected' : risk.result === 'PASS' ? 'passed' : 'unknown')}>
              {risk.result === 'FAIL' ? (vi ? 'Không đạt' : 'Failed') : risk.result === 'PASS' ? (vi ? 'Đạt' : 'Passed') : String(risk.result ?? '—')}
            </span>
          </div>
          <p className="risk-summary">
            {risk.result === 'PASS'
              ? vi
                ? 'Tác động mô phỏng nằm trong giới hạn tổn thất và chi phí của Owner.'
                : "Simulated effects stay within the Owner's loss and cost limits."
              : vi
                ? 'Tác động mô phỏng vượt giới hạn được cho phép.'
                : 'Simulated effects exceed the permitted limits.'}
          </p>
        </section>
      )}

      {job && <BlockReason job={job} language={language} />}

      <section className="panel-section">
        <div className="panel-label">
          <span>
            <Link2 size={15} aria-hidden="true" />
            {vi ? 'Trạng thái on-chain' : 'On-chain status'}
          </span>
        </div>
        <dl className="fact-rows">
          <div>
            <dt>{vi ? 'Mạng' : 'Network'}</dt>
            <dd>{networkLabel(job?.environment ?? mode, language)}</dd>
          </div>
          <div>
            <dt>{vi ? 'Trạng thái' : 'Status'}</dt>
            <dd>
              <span className={'chip tone-' + chain.tone}>{chain.label}</span>
            </dd>
          </div>
          <div>
            <dt>Tx hash</dt>
            <dd>{outcome?.tx_hash ? <CopyHash value={outcome.tx_hash} /> : <span className="hash-empty">—</span>}</dd>
          </div>
          {outcome &&
            ['CONFIRMED', 'REVERTED'].includes(outcome.status) &&
            outcome.system_gas_expense?.actual_cost_wei && (
              <div>
                <dt>{job?.environment === 'REAL_FUJI_EXECUTION' ? (vi ? 'Gas đã trả' : 'Gas paid') : 'Gas EVM'}</dt>
                <dd>{units(outcome.system_gas_expense.actual_cost_wei, 18, 6)} AVAX</dd>
              </div>
            )}
        </dl>
      </section>

      <div className="panel-actions">
        {explorer ? (
          <a className="action-btn is-accent" href={explorer} target="_blank" rel="noreferrer">
            <ExternalLink size={14} aria-hidden="true" />
            {vi ? 'Xem trên Snowtrace' : 'View on Snowtrace'}
          </a>
        ) : (
          <button type="button" className="action-btn" disabled>
            <ExternalLink size={14} aria-hidden="true" />
            {vi ? 'Xem trên Explorer' : 'View on Explorer'}
          </button>
        )}
        {job && (
          <button type="button" className="action-btn" onClick={onEvidence} data-testid="open-evidence">
            <FileCheck2 size={14} aria-hidden="true" />
            {t.details}
          </button>
        )}
        {!explorer && (
          <p className="action-note">
            {job?.environment === 'ANVIL_FORK' || job?.environment === 'VERIFIED_REPLAY'
              ? vi
                ? 'Hash trên fork hoặc bản ghi không có trên explorer công khai.'
                : 'Fork and replay hashes are not on the public explorer.'
              : vi
                ? 'Liên kết explorer xuất hiện khi có receipt công khai.'
                : 'An explorer link appears once a public receipt exists.'}
          </p>
        )}
      </div>
    </aside>
  );
}

/* ==========================================================================
   Evidence page
   ========================================================================== */

type Filter = 'all' | 'confirmed' | 'blocked' | 'other';

function filterOf(job: Job): Exclude<Filter, 'all'> {
  if (job.status === 'CONFIRMED') return 'confirmed';
  if (job.status === 'REJECTED') return 'blocked';
  return 'other';
}

function toneOf(job: Job) {
  if (job.status === 'CONFIRMED') return 'passed';
  if (job.status === 'REJECTED') return 'rejected';
  if (!job.terminal) return 'running';
  if (job.status === 'UNKNOWN' || job.status === 'INTERRUPTED') return 'unknown';
  return 'failed';
}

export function ExecutionHistory({
  jobs,
  language,
  pending,
  error,
  source,
  onRefresh,
  onOpen,
  onDemo,
}: {
  jobs: Job[];
  language: Language;
  pending: boolean;
  error: boolean;
  source?: {data?: SourceSnapshot; pending: boolean; error: boolean};
  onRefresh: () => void;
  onOpen: (job: Job) => void;
  onDemo: () => void;
}) {
  const t = copy[language];
  const vi = language === 'vi';
  const [filter, setFilter] = useState<Filter>('all');
  const counts = useMemo(() => {
    const value = {all: jobs.length, confirmed: 0, blocked: 0, other: 0};
    for (const job of jobs) value[filterOf(job)] += 1;
    return value;
  }, [jobs]);
  const visible = filter === 'all' ? jobs : jobs.filter(job => filterOf(job) === filter);
  const filters: [Filter, string][] = [
    ['all', t.all],
    ['confirmed', t.confirmedFilter],
    ['blocked', t.blockedFilter],
    ['other', t.otherFilter],
  ];

  return (
    <section className="execution-history" data-testid="history-panel">
      <div className="page-head">
        <div>
          <h1>{t.history}</h1>
          <p>{t.historyHint}</p>
        </div>
        <div className="page-head-meta">
          <button type="button" className="link-btn" onClick={onRefresh} disabled={pending}>
            <RotateCcw size={14} className={pending ? 'animate-spin' : ''} aria-hidden="true" />
            {t.refresh}
          </button>
        </div>
      </div>

      <div className="evidence-layout">
        <div className="panel history-surface">
          <div className="history-toolbar">
            <div className="segmented" role="group" aria-label={vi ? 'Lọc theo kết quả' : 'Filter by result'}>
              {filters.map(([value, label]) => (
                <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>
                  {label}
                  <span className="count">{counts[value]}</span>
                </button>
              ))}
            </div>
          </div>

          {!!visible.length && (
            <div className="table-wrap">
              <table className="evidence-table">
                <thead>
                  <tr>
                    <th scope="col">{t.time}</th>
                    <th scope="col">{t.operation}</th>
                    <th scope="col">{t.result}</th>
                    <th scope="col">{t.last}</th>
                    <th scope="col">{t.transaction}</th>
                    <th scope="col">
                      <span className="sr-only">{t.details}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map(job => {
                    const explorer = publicExplorer(job);
                    const hash = job.workflow?.outcome?.tx_hash;
                    return (
                      <tr key={job.job_id}>
                        <td data-label={t.time}>
                          <span className="history-time">
                            <Clock3 size={13} aria-hidden="true" />
                            {date(job.created_at)}
                          </span>
                        </td>
                        <td data-label={t.operation}>
                          <span>
                            <strong>{t[job.scenario]}</strong>
                            <span className="cell-sub">{networkLabel(job.environment, language)}</span>
                          </span>
                        </td>
                        <td data-label={t.result}>
                          <span className={'chip tone-' + toneOf(job)}>
                            <span className="chip-dot" aria-hidden="true" />
                            {t[job.status]}
                          </span>
                        </td>
                        <td data-label={t.last}>
                          <span className="cell-sub" style={{marginTop: 0}}>
                            {stageLabel(
                              job.workflow?.timeline.filter(event => event.stage !== 'REJECTION_OR_RECOVERY').at(-1)?.stage,
                              language,
                            )}
                          </span>
                        </td>
                        <td data-label={t.transaction}>
                          {hash ? (
                            <span style={{display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>
                              <CopyHash value={hash} />
                              {explorer && (
                                <a className="explorer-link" href={explorer} target="_blank" rel="noreferrer">
                                  Snowtrace <ExternalLink size={12} aria-hidden="true" />
                                </a>
                              )}
                            </span>
                          ) : (
                            <span className="hash-empty">—</span>
                          )}
                        </td>
                        <td style={{textAlign: 'right'}}>
                          <button
                            type="button"
                            className="link-btn"
                            aria-label={`${t.details}: ${t[job.scenario]} ${date(job.created_at)}`}
                            onClick={() => onOpen(job)}
                          >
                            <FileCheck2 size={14} aria-hidden="true" />
                            {vi ? 'Bằng chứng' : 'Evidence'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {!visible.length && (
            <div className="history-empty-state">
              <span className="empty-symbol" aria-hidden="true">
                {pending ? <LoaderCircle size={24} className="animate-spin" /> : <History size={24} strokeWidth={1.7} />}
              </span>
              <h2>{pending ? t.pending : error ? t.error : jobs.length ? t.emptyFilter : t.emptyHistory}</h2>
              {!pending && !jobs.length && <p>{error ? t.errorHint : t.emptyHistoryHint}</p>}
              {!pending && !jobs.length && (
                <button type="button" className="link-btn" onClick={error ? onRefresh : onDemo}>
                  {error ? t.refresh : t.demo}
                </button>
              )}
            </div>
          )}
        </div>

        <SourcePanel source={source} language={language} />
      </div>
    </section>
  );
}

const EXPLORER = 'https://testnet.snowtrace.io/address/';

function SourcePanel({source, language}: {source?: {data?: SourceSnapshot; pending: boolean; error: boolean}; language: Language}) {
  const vi = language === 'vi';
  const data = source?.data;
  const status = data?.status;
  const addresses = Object.entries(data?.addresses ?? {}).filter(([, value]) => /^0x[0-9a-fA-F]{40}$/.test(value));
  const roles: Record<string, [string, string]> = {
    treasury: ['PolicyVault', 'PolicyVault'],
    owner: ['Owner', 'Owner'],
    attestor: ['Attestor', 'Attestor'],
    relayer: ['Relayer', 'Relayer'],
  };

  return (
    <aside className="panel source-panel" aria-label={vi ? 'Nguồn dữ liệu on-chain' : 'On-chain source'}>
      <div className="panel-head">
        <span className="panel-head-icon" aria-hidden="true">
          <Database size={17} />
        </span>
        <div>
          <h2>{vi ? 'Hợp đồng & nguồn dữ liệu' : 'Contracts & source data'}</h2>
          <p>{vi ? 'Đọc trực tiếp từ Avalanche Fuji qua backend.' : 'Read from Avalanche Fuji through the backend.'}</p>
        </div>
      </div>

      {source?.pending && !data ? (
        <div className="source-status">
          <span className="chip tone-idle">
            <LoaderCircle size={11} className="animate-spin" aria-hidden="true" />
            {vi ? 'Đang đọc…' : 'Reading…'}
          </span>
        </div>
      ) : !data || status === 'UNAVAILABLE' ? (
        <p className="source-note" style={{borderTop: 0}}>
          {vi ? 'Chưa đọc được dữ liệu nguồn on-chain.' : 'On-chain source data is not available right now.'}
          {data?.reason_code ? ` (${data.reason_code})` : ''}
        </p>
      ) : (
        <>
          <div className="source-status">
            <span className={'chip ' + (status === 'VERIFIED_READ' ? 'tone-passed' : 'tone-unknown')}>
              {status === 'VERIFIED_READ' ? (vi ? 'Đọc trực tiếp' : 'Live read') : vi ? 'Ảnh chụp đã ghi' : 'Recorded snapshot'}
            </span>
            {data.oracle?.status && (
              <span className={'chip ' + (data.oracle.status === 'FRESH' ? 'tone-passed' : 'tone-unknown')}>
                Oracle {data.oracle.status === 'FRESH' ? (vi ? 'mới' : 'fresh') : data.oracle.status.replaceAll('_', ' ').toLowerCase()}
                {typeof data.oracle.age_seconds === 'number' ? ` · ${data.oracle.age_seconds}s` : ''}
              </span>
            )}
          </div>
          <dl className="fact-rows">
            {data.block_number !== undefined && (
              <div>
                <dt>{vi ? 'Block' : 'Block'}</dt>
                <dd className="mono">{data.block_number.toLocaleString('en-US')}</dd>
              </div>
            )}
            {data.policy && (
              <>
                <div>
                  <dt>Policy</dt>
                  <dd>
                    <span className={'chip ' + (data.policy.active && !data.policy.paused ? 'tone-passed' : 'tone-rejected')}>
                      {data.policy.paused ? (vi ? 'Tạm dừng' : 'Paused') : data.policy.active ? (vi ? 'Hiệu lực' : 'Active') : vi ? 'Không hiệu lực' : 'Inactive'}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>{vi ? 'Tổn thất tối đa' : 'Max relative loss'}</dt>
                  <dd>{(data.policy.max_relative_loss_bps / 100).toLocaleString('en-US')}%</dd>
                </div>
                <div>
                  <dt>{vi ? 'Biên oracle' : 'Oracle band'}</dt>
                  <dd>{(data.policy.oracle_band_bps / 100).toLocaleString('en-US')}%</dd>
                </div>
              </>
            )}
            {data.balances && (
              <div>
                <dt>{vi ? 'Số dư vault' : 'Vault balance'}</dt>
                <dd className="stacked-values">
                  <span>{units(data.balances.usdc, 6, 6)} USDC</span>
                  <span>{units(data.balances.wavax, 18, 6)} WAVAX</span>
                </dd>
              </div>
            )}
          </dl>
          {!!addresses.length && (
            <>
              <div className="panel-section" style={{paddingBottom: 6}}>
                <div className="panel-label" style={{marginBottom: 0}}>
                  <span>{vi ? 'Địa chỉ trên Fuji' : 'Addresses on Fuji'}</span>
                </div>
              </div>
              <ul className="address-list">
                {addresses.map(([role, address]) => (
                  <li key={role}>
                    <span className="role">{roles[role]?.[vi ? 0 : 1] ?? role}</span>
                    <CopyHash value={address} />
                    <a
                      className="address-ext"
                      href={EXPLORER + address}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`${roles[role]?.[1] ?? role} ${short(address)} on Snowtrace`}
                    >
                      <ExternalLink size={13} aria-hidden="true" />
                    </a>
                  </li>
                ))}
              </ul>
            </>
          )}
          {data.observed_at && (
            <p className="source-note">
              {vi ? 'Quan sát lúc ' : 'Observed '}
              {new Intl.DateTimeFormat(vi ? 'vi-VN' : 'en-GB', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh'}).format(new Date(data.observed_at))}
              {' (UTC+7)'}
            </p>
          )}
        </>
      )}
    </aside>
  );
}
