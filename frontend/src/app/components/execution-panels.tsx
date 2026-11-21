import {
  Activity,
  ArrowUpRight,
  Clock3,
  FileCheck2,
  History,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
  ShieldX,
  CircleHelp,
  ExternalLink,
} from 'lucide-react';
import {Button} from './ui/button';
import {date, publicExplorer, units} from '@/lib/format';
import {BlockReason} from './run-session';
import type {Job, ScenarioId} from '@/lib/types';
import type {Language} from '@/lib/i18n';

const copy = {
  vi: {
    status: 'Kết quả kiểm tra',
    empty: 'Chưa có lượt kiểm tra',
    emptyHint: 'Chọn kịch bản bên trái và nhấn Chạy kịch bản để bắt đầu quá trình kiểm tra bảo mật.',
    scenario: 'Kịch bản',
    stage: 'Bước xử lý',
    details: 'Xem bằng chứng chi tiết',
    history: 'Lịch sử kiểm tra',
    historyHint: 'Hồ sơ kiểm tra giao dịch và bằng chứng bảo mật của từng phiên chạy.',
    refresh: 'Làm mới',
    time: 'Thời gian',
    operation: 'Kịch bản',
    result: 'Kết quả',
    last: 'Bước ghi nhận cuối',
    emptyHistory: 'Chưa có hồ sơ kiểm tra',
    emptyHistoryHint: 'Các lượt chạy kiểm tra sẽ được tự động lưu lại đây để đối soát.',
    demo: 'Chạy kịch bản đầu tiên',
    error: 'Không tải được lịch sử',
    errorHint: 'Hãy thử làm mới để lấy lại dữ liệu từ server.',
    pending: 'Đang tải hồ sơ',
    payment: 'Thanh toán USDC',
    swap: 'Hoán đổi token',
    guard: 'Kiểm tra bảo mật',
    recorded: 'Bản ghi mẫu',
    check: 'Lượt kiểm tra',
    reason: 'Lý do',
    awaiting: 'Đang chuẩn bị',
    noStage: 'Chưa ghi nhận',
    CONFIRMED: 'Đã xác nhận',
    REJECTED: 'Bị từ chối',
    UNKNOWN: 'Chưa xác định',
    INTERRUPTED: 'Bị gián đoạn',
    UNAVAILABLE: 'Chưa thể kiểm tra',
    FAILED: 'Không hoàn tất',
    RUNNING: 'Đang kiểm tra',
    QUEUED: 'Đang chuẩn bị',
  },
  en: {
    status: 'Verification Result',
    empty: 'No verification yet',
    emptyHint: 'Select a scenario on the left and click Run Scenario to begin the security pipeline.',
    scenario: 'Scenario',
    stage: 'Processing step',
    details: 'Inspect full evidence',
    history: 'Verification History',
    historyHint: 'Verifiable records and cryptographic evidence for each execution run.',
    refresh: 'Refresh',
    time: 'Timestamp',
    operation: 'Scenario',
    result: 'Verdict',
    last: 'Final stage',
    emptyHistory: 'No verification records yet',
    emptyHistoryHint: 'Executed transactions and security evaluations will appear here.',
    demo: 'Run first scenario',
    error: 'History unavailable',
    errorHint: 'Try refreshing to reload records from the backend.',
    pending: 'Loading records',
    payment: 'USDC Payment',
    swap: 'Token Swap',
    guard: 'Security Guard',
    recorded: 'Recording',
    check: 'Live Verification',
    reason: 'Reason',
    awaiting: 'Preparing',
    noStage: 'Not recorded',
    CONFIRMED: 'Confirmed',
    REJECTED: 'Rejected',
    UNKNOWN: 'Unknown',
    INTERRUPTED: 'Interrupted',
    UNAVAILABLE: 'Unavailable',
    FAILED: 'Failed',
    RUNNING: 'Verifying',
    QUEUED: 'Preparing',
  },
} as const;

const stages: Record<string, [string, string]> = {
  PLANNING: ['Phân tích yêu cầu', 'Analyzing request'],
  BUILD: ['Chuẩn bị giao dịch', 'Preparing transaction'],
  SIMULATION: ['Mô phỏng EVM', 'EVM simulation'],
  ITAG: ['Kiểm tra ý định', 'Intent alignment'],
  RISK: ['Kiểm tra rủi ro', 'Risk verification'],
  PROOF: ['Xác minh Z3', 'Z3 verification'],
  SDE: ['Quyết định bảo mật', 'Security decision'],
  ATTESTATION: ['Ký xác nhận EIP-712', 'EIP-712 Attestation'],
  EXACT_SIGNED_PREFLIGHT: ['Kiểm tra trước thực thi', 'Exact preflight'],
  RELAY: ['Thực thi giao dịch', 'Transaction execution'],
  OUTCOME: ['Đối soát kết quả', 'Receipt reconciliation'],
  OWNER_AUTHORITY: ['Kiểm tra quyền hạn', 'Authority check'],
  AGENT_PROPOSAL: ['Đề xuất của AI', 'AI proposal'],
};

function stageLabel(value: string | undefined, language: Language) {
  return value
    ? stages[value]?.[language === 'vi' ? 0 : 1] ?? value
    : copy[language].noStage;
}

const phases: Record<string, [string, string]> = {
  QUEUED: ['Đang chờ xử lý', 'Queued'],
  PREPARING_FORK: ['Chuẩn bị dữ liệu giao dịch', 'Preparing transaction data'],
  WAITING_FOR_ORACLE: ['Chờ giá tham chiếu hợp lệ', 'Waiting for valid oracle price'],
  WORKFLOW_RUNNING: ['Đang kiểm tra giao dịch', 'Verifying transaction'],
};

function ToneIcon({job}: {job: Job}) {
  const Icon =
    job.status === 'CONFIRMED'
      ? ShieldCheck
      : job.status === 'REJECTED'
        ? ShieldX
        : !job.terminal
          ? LoaderCircle
          : CircleHelp;

  return (
    <Icon
      size={22}
      strokeWidth={2}
      className={!job.terminal ? 'animate-spin' : ''}
    />
  );
}

export function ExecutionStatus({
  job,
  language,
  onEvidence,
}: {
  job?: Job;
  language: Language;
  onEvidence: () => void;
}) {
  const t = copy[language];
  const explorer = job ? publicExplorer(job) : null;

  return (
    <aside className="workspace-card status-panel">
      <div className="panel-title">
        <Activity size={18} strokeWidth={2.2} />
        <h2>{t.status}</h2>
      </div>

      {!job ? (
        <div className="status-empty">
          <span className="empty-symbol">
            <ShieldCheck size={28} strokeWidth={1.5} />
          </span>
          <h3>{t.empty}</h3>
          <p>{t.emptyHint}</p>
        </div>
      ) : (
        <>
          <div
            className={'decision-box decision-' + job.status.toLowerCase()}
            role="status"
          >
            <ToneIcon job={job} />
            <div>
              <strong>{t[job.status]}</strong>
              <span>
                {job.environment === 'VERIFIED_REPLAY' ? t.recorded : t.check}
              </span>
            </div>
          </div>

          <dl className="execution-facts">
            <div>
              <dt>{t.scenario}</dt>
              <dd>{t[job.scenario]}</dd>
            </div>
            <div>
              <dt>{t.stage}</dt>
              <dd>
                {job.terminal && job.status === 'CONFIRMED'
                  ? stageLabel('OUTCOME', language)
                  : job.active_stage
                    ? stageLabel(job.active_stage, language)
                    : phases[job.phase ?? '']?.[language === 'vi' ? 0 : 1] ??
                      t.awaiting}
              </dd>
            </div>
            {job.workflow?.outcome &&
              ['CONFIRMED', 'REVERTED'].includes(job.workflow.outcome.status) &&
              job.workflow.outcome.system_gas_expense?.actual_cost_wei && (
                <div>
                  <dt>
                    {job.environment === 'REAL_FUJI_EXECUTION'
                      ? language === 'vi'
                        ? 'Gas đã trả'
                        : 'Gas paid'
                      : 'Gas EVM'}
                  </dt>
                  <dd>
                    {units(job.workflow.outcome.system_gas_expense.actual_cost_wei, 18, 18)}{' '}
                    AVAX
                  </dd>
                </div>
              )}
          </dl>

          <BlockReason job={job} language={language} />

          {explorer && (
            <Button variant="outline" asChild className="evidence-open">
              <a href={explorer} target="_blank" rel="noreferrer">
                {language === 'vi' ? 'Xem giao dịch trên Fuji' : 'View transaction on Fuji'}
                <ExternalLink size={14} />
              </a>
            </Button>
          )}

          <Button variant="outline" className="evidence-open" onClick={onEvidence}>
            <FileCheck2 size={15} />
            {t.details}
            <ArrowUpRight size={13} />
          </Button>
        </>
      )}
    </aside>
  );
}

export function ExecutionHistory({
  jobs,
  language,
  pending,
  error,
  onRefresh,
  onOpen,
  onDemo,
}: {
  jobs: Job[];
  language: Language;
  pending: boolean;
  error: boolean;
  onRefresh: () => void;
  onOpen: (job: Job) => void;
  onDemo: () => void;
}) {
  const t = copy[language];
  const vi = language === 'vi';

  return (
    <section className="execution-history" data-testid="history-panel">
      <div className="history-page-heading">
        <div>
          <span className="history-kicker">
            <History size={14} />
            {vi ? 'HỒ SƠ KIỂM TRA BẢO MẬT' : 'CRYPTOGRAPHIC VERIFICATION RECORDS'}
          </span>
          <h1>{t.history}</h1>
          <p>{t.historyHint}</p>
        </div>
        <Button variant="outline" onClick={onRefresh} disabled={pending}>
          <RotateCcw size={14} className={pending ? 'animate-spin' : ''} />
          {t.refresh}
        </Button>
      </div>

      <div className="history-surface">
        {!!jobs.length && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {[t.time, t.operation, t.result, t.last, ''].map((label, i) => (
                    <th key={i}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <tr key={job.job_id}>
                    <td>
                      <span className="history-time">
                        <Clock3 size={13} />
                        {date(job.created_at)}
                      </span>
                    </td>
                    <td>
                      <strong>{t[job.scenario]}</strong>
                      {job.environment === 'VERIFIED_REPLAY' && (
                        <small className="block text-slate-400 text-xs mt-0.5">
                          {t.recorded}
                        </small>
                      )}
                    </td>
                    <td>
                      <span
                        className={'result-chip result-' + job.status.toLowerCase()}
                      >
                        <span className="chip-dot" />
                        {t[job.status]}
                      </span>
                    </td>
                    <td className="text-slate-500 text-xs">
                      {stageLabel(
                        job.workflow?.timeline
                          .filter(e => e.stage !== 'REJECTION_OR_RECOVERY')
                          .at(-1)?.stage,
                        language,
                      )}
                    </td>
                    <td className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`${t.details}: ${t[job.scenario]}`}
                        onClick={() => onOpen(job)}
                      >
                        <FileCheck2 size={14} />
                        {t.details}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!jobs.length && (
          <div className="history-empty-state">
            <span className="empty-symbol">
              {pending ? (
                <LoaderCircle size={26} className="animate-spin text-primary" />
              ) : (
                <History size={26} strokeWidth={1.5} />
              )}
            </span>
            <h2>{pending ? t.pending : error ? t.error : t.emptyHistory}</h2>
            <p>{pending ? '' : error ? t.errorHint : t.emptyHistoryHint}</p>
            {!pending && (
              <Button variant="outline" onClick={error ? onRefresh : onDemo}>
                {error ? t.refresh : t.demo}
                <ArrowUpRight size={14} />
              </Button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
