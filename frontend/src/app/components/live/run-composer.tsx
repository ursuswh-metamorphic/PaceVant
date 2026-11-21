import type {ReactNode} from 'react';
import {ArrowLeftRight, Banknote, CircleCheck, ShieldX} from 'lucide-react';
import {AttackSelect} from '@/components/attack-select';
import {units} from '@/lib/format';
import {dictionary, type Language} from '@/lib/i18n';
import type {JudgeConfig, ScenarioId} from '@/lib/types';
import {cn} from '@/lib/utils';

const scenarioIcons = {payment: Banknote, swap: ArrowLeftRight, guard: ShieldX};

/*
 * Run composer: the three decisions a judge makes, in reading order —
 * 1 scenario, 2 optional attack simulation, 3 run. Pure presentation: every
 * value and handler comes from App, which owns run/recovery state.
 */
export function RunComposer({
  language,
  config,
  loading,
  scenario,
  onScenario,
  attack,
  onAttack,
  busy,
  runDisabled,
  runIcon,
  runLabel,
  onRun,
  onGuard,
  guardDisabled,
  hint,
}: {
  language: Language;
  config?: JudgeConfig;
  loading: boolean;
  scenario: ScenarioId;
  onScenario: (id: ScenarioId) => void;
  attack: string;
  onAttack: (value: string) => void;
  busy: boolean;
  runDisabled: boolean;
  runIcon: ReactNode;
  runLabel: string;
  onRun: () => void;
  onGuard: () => void;
  guardDisabled: boolean;
  hint?: string;
}) {
  const t = dictionary[language];
  const vi = language === 'vi';
  const names = {payment: t.payment, swap: t.swap, guard: t.guard};
  const descriptions = {payment: t.payDesc, swap: t.swapDesc, guard: t.guardDesc};

  return (
    <section className="composer" aria-label={vi ? 'Thiết lập lượt chạy' : 'Run setup'}>
      <div className="composer-step composer-scenarios">
        <h2 className="composer-label">
          <span className="step-num" aria-hidden="true">1</span>
          {t.choose}
        </h2>
        <div className="compact-scenarios" role="group" aria-label={t.choose}>
          {loading
            ? [0, 1].map(i => <div key={i} className="skeleton scenario-skeleton" />)
            : config?.scenarios
                .filter(value => value.id !== 'guard')
                .map(value => {
                  const Icon = scenarioIcons[value.id];
                  const active = scenario === value.id;
                  return (
                    <button
                      key={value.id}
                      type="button"
                      data-testid={'scenario-' + value.id}
                      aria-pressed={active}
                      disabled={busy}
                      onClick={() => onScenario(value.id)}
                      className={cn('compact-scenario', active && 'selected')}
                    >
                      <span className="scenario-icon" aria-hidden="true">
                        <Icon size={18} strokeWidth={1.9} />
                      </span>
                      <span className="scenario-copy">
                        <strong>{names[value.id]}</strong>
                        <small>{descriptions[value.id]}</small>
                        <span className="scenario-terms" aria-label={vi ? 'Điều khoản giao dịch' : 'Transaction terms'}>
                          <span className="mono">
                            {units(value.amount, value.input_decimals, value.input_decimals)} {value.token_in}
                          </span>
                          <span aria-hidden="true">→</span>
                          <span title={value.recipient_label}>
                            {value.token_in === value.token_out ? (vi?'Người nhận được chủ ví duyệt':value.recipient_label) : value.token_out}
                          </span>
                        </span>
                      </span>
                      {active ? <CircleCheck size={18} className="scenario-check" aria-hidden="true" /> : <span />}
                    </button>
                  );
                })}
        </div>
      </div>

      <div className="composer-step composer-attack">
        <h2 className="composer-label">
          <span className="step-num" aria-hidden="true">2</span>
          {vi ? 'Mô phỏng tình huống bất lợi' : 'Adversarial security test'}
          <small>{vi ? 'Tuỳ chọn' : 'Optional'}</small>
        </h2>
        <AttackSelect value={attack} onChange={onAttack} disabled={busy} language={language} scenario={scenario} />
      </div>

      <div className="composer-step composer-run">
        <h2 className="composer-label">
          <span className="step-num" aria-hidden="true">3</span>
          {vi ? 'Chạy & theo dõi' : 'Run & watch'}
        </h2>
        <button type="button" className="btn-primary run-button" disabled={runDisabled} onClick={onRun} data-testid="run-scenario">
          {runIcon}
          {runLabel}
        </button>
        {/* Always rendered so the panel height never changes when the hint comes and goes. */}
        <p className="mode-hint">{hint ?? (attack !== 'none' ? (vi ? 'Kiểm tra contract trên trạng thái Fuji lịch sử; không gửi giao dịch mới.' : 'Contract check against historical Fuji state; no new transaction.') : undefined)}</p>
        <button type="button" className="guard-run-action" disabled={guardDisabled} onClick={onGuard} data-testid="run-real-guard" title={vi?'Chạy tình huống cố định do máy chủ chọn, riêng với các bản mô tả ở mục 2. Kết quả dựa trên bằng chứng thực.':'Run the fixed server-selected security case, separate from the descriptions in step 2.'}>{vi?'Chạy kiểm tra bảo mật thực tế':'Run a real security check'}</button>
      </div>
    </section>
  );
}
