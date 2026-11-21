import {Suspense, lazy, useEffect, useRef, useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {AnimatePresence, motion, useReducedMotion} from 'motion/react';
import {ArrowLeftRight, Banknote, CircleCheck, Layers3, LoaderCircle, Play, ShieldCheck, ShieldX} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Tabs, TabsContent, TabsList, TabsTrigger} from '@/components/ui/tabs';
import {EvidenceDrawer} from '@/components/evidence';
const Pipeline = lazy(() => import('@/components/pipeline').then(module => ({default: module.Pipeline})));
import {AttackSelect, AttackPreview} from '@/components/attack-select';
import {LanguageSwitcher, SiteFooter} from '@/components/site-chrome';
import {Overview} from '@/components/overview';
import {ExecutionStatus, ExecutionHistory} from '@/components/execution-panels';
import {RunSession} from '@/components/run-session';
import {AmbientRibbons} from '@/components/illustrations';
import {api, ApiError} from '@/lib/api';
import {
  beginAttempt,
  clearAttempt,
  loadAttempt,
  saveAttempt,
  loadViewedRun,
  saveViewedRun,
  clearViewedRun,
  type SavedAttempt,
} from '@/lib/recovery';
import {reason, units} from '@/lib/format';
import type {Job, ScenarioId} from '@/lib/types';
import {cn} from '@/lib/utils';
import {dictionary, type Language} from '@/lib/i18n';

const scenarioIcons = {payment: Banknote, swap: ArrowLeftRight, guard: ShieldX};

function savedState() {
  try {
    return {attempt: loadAttempt(), view: loadViewedRun(), error: ''};
  } catch (error) {
    return {attempt: null, view: null, error: (error as Error).message};
  }
}

export default function App() {
  const [initial] = useState(savedState);
  const [tab, setTab] = useState(initial.attempt || initial.view ? 'live' : 'overview');
  const [language, setLanguage] = useState<Language>(() => {
    try {
      return localStorage.getItem('pacevant.language') === 'en' ? 'en' : 'vi';
    } catch {
      return 'vi';
    }
  });
  const t = dictionary[language];

  useEffect(() => {
    try {
      localStorage.setItem('pacevant.language', language);
    } catch {}
    document.documentElement.lang = language;
  }, [language]);

  const [scenario, setScenario] = useState<ScenarioId>(
    initial.attempt?.body.scenario ?? initial.view?.scenario ?? 'payment',
  );
  const [attackPreset, setAttackPreset] = useState('none');
  const [attackPreview, setAttackPreview] = useState(false);
  const [baseScenario, setBaseScenario] = useState<ScenarioId>(
    scenario === 'guard' ? 'payment' : scenario,
  );
  const [saved, setSaved] = useState<SavedAttempt | null>(initial.attempt);
  const savedRef = useRef(saved);
  const inFlight = useRef(false);
  const [activeId, setActiveId] = useState<string | undefined>(
    initial.attempt ? initial.attempt.job_id : initial.view?.job_id,
  );
  const [message, setMessage] = useState(initial.error);
  const [drawer, setDrawer] = useState(false);
  const [historyJob, setHistoryJob] = useState<Job>();
  const [opening, setOpening] = useState(false);
  const [storageBlocked] = useState(Boolean(initial.error));
  const queryClient = useQueryClient();
  const reduced = useReducedMotion();

  const config = useQuery({
    queryKey: ['judge-config'],
    queryFn: api.config,
    refetchInterval: 30000,
    retry: 1,
  });

  const history = useQuery({
    queryKey: ['history'],
    queryFn: api.history,
    enabled: config.isSuccess,
    refetchInterval: 30000,
    retry: 1,
  });

  const job = useQuery({
    queryKey: ['job', activeId],
    queryFn: () => api.job(activeId!),
    enabled: config.isSuccess && !!activeId,
    refetchInterval: query => (query.state.data?.terminal ? false : 1000),
    retry: 1,
  });

  // Read-only on-chain context for the Evidence page (contract addresses, policy, oracle).
  const source = useQuery({
    queryKey: ['judge-source'],
    queryFn: api.snapshot,
    enabled: config.isSuccess && tab === 'history',
    refetchInterval: 60000,
    retry: 1,
  });

  const recovered = useQuery({
    queryKey: ['request', saved?.key],
    queryFn: () => api.byKey(saved!.key),
    enabled: config.isSuccess && !!saved && !saved.job_id,
    refetchInterval: 5000,
    retry: false,
  });

  const current = job.data;

  useEffect(() => {
    const active = saved?.body.scenario ?? current?.scenario;
    if (active === 'payment' || active === 'swap') {
      setBaseScenario(active);
      setScenario(active);
      setAttackPreset('none');
    }
  }, [saved?.body.scenario, current?.job_id]);

  const quota = config.data?.quota;
  const ownRunActive = !!saved || (!!current && !current.terminal);
  const restoring = !!activeId && !current && !job.isError;
  const liveBusy = storageBlocked || ownRunActive || restoring || (!!activeId && !current) || opening;

  function retain(value: SavedAttempt | null) {
    savedRef.current = value;
    setSaved(value);
  }

  function accept(value: Job, attempt: SavedAttempt) {
    if (value.job_id !== attempt.job_id && attempt.job_id) {
      throw new Error('Recovered workflow identity mismatch');
    }
    setActiveId(value.job_id);
    queryClient.setQueryData(['job', value.job_id], value);
    saveAttempt({...attempt, job_id: value.job_id});
    retain({...attempt, job_id: value.job_id});
    saveViewedRun({job_id: value.job_id, scenario: value.scenario});
  }

  useEffect(() => {
    if (recovered.data && savedRef.current) accept(recovered.data, savedRef.current);
  }, [recovered.data]);

  useEffect(() => {
    if (job.data?.terminal && savedRef.current?.job_id === job.data.job_id) {
      saveViewedRun({job_id: job.data.job_id, scenario: job.data.scenario});
      clearAttempt();
      retain(null);
      void queryClient.invalidateQueries({queryKey: ['history']});
      void queryClient.invalidateQueries({queryKey: ['judge-config']});
    }
  }, [job.data?.terminal, job.data?.job_id]);

  const start = useMutation({
    mutationFn: async (id: ScenarioId) => {
      const attempt = savedRef.current ?? beginAttempt(id);
      retain(attempt);
      setScenario(attempt.body.scenario);
      setMessage('');
      if (!attempt.job_id) setActiveId(undefined);

      if (attempt.job_id) return {value: await api.job(attempt.job_id), attempt};
      try {
        const value = await api.byKey(attempt.key);
        return {value, attempt};
      } catch (error) {
        if (!(error instanceof ApiError) || error.code !== 'JUDGE_REQUEST_NOT_FOUND') {
          throw error;
        }
      }
      return {value: await api.start(attempt.body.scenario, attempt.key), attempt};
    },
    onSuccess: ({value, attempt}) => accept(value, attempt),
    onError: error =>
      setMessage(
        error instanceof ApiError
          ? reason(error.code)
          : 'The response was interrupted. Your exact request is saved; use Resume safely.',
      ),
  });

  async function run(id: ScenarioId) {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      await start.mutateAsync(id);
    } catch {
      // The saved identity is deliberately retained.
    } finally {
      inFlight.current = false;
    }
  }

  async function openHistory(value: Job) {
    setOpening(true);
    try {
      setHistoryJob(await api.job(value.job_id));
      setDrawer(true);
    } catch {
      setMessage('The selected execution record could not be loaded.');
    } finally {
      setOpening(false);
    }
  }

  const names = {payment: t.payment, swap: t.swap, guard: t.guard};
  const descriptions = {payment: t.payDesc, swap: t.swapDesc, guard: t.guardDesc};
  const ready = !!config.data?.configured && !config.data.busy && quota?.remaining_today !== 0;
  const vi = language === 'vi';
  const selectedScenario = config.data?.scenarios.find(value => value.id === baseScenario);
  const tabs = [
    {value: 'overview', label: t.overview, testId: undefined},
    {value: 'live', label: t.demo, testId: 'tab-live'},
    {value: 'history', label: t.evidence, testId: 'tab-history'},
  ];

  const session = (saved || activeId) && (
    <RunSession
      job={current}
      scenario={saved?.body.scenario ?? current?.scenario ?? scenario}
      restoring={restoring || (!!saved && !saved.job_id && !start.isPending && !recovered.isError)}
      disconnected={
        job.isError ||
        (recovered.isError &&
          !(recovered.error instanceof ApiError && recovered.error.code === 'JUDGE_REQUEST_NOT_FOUND'))
      }
      needsResume={!!saved && !saved.job_id && recovered.isError && !start.isPending}
      pending={start.isPending}
      onResume={() => (saved && !saved.job_id ? void run(saved.body.scenario) : void job.refetch())}
      onDemo={() => setTab('live')}
      onClear={
        !saved && job.error instanceof ApiError && job.error.status === 404
          ? () => {
              clearViewedRun();
              setActiveId(undefined);
            }
          : undefined
      }
      showDemo={tab !== 'live'}
      language={language}
            />
  );

  return (
    <div className="app-shell" data-tab={tab}>
      <a className="skip-link" href="#main-content">
        {vi ? 'Bỏ qua đến nội dung' : 'Skip to content'}
      </a>
      <div className="ambient" aria-hidden="true">
        <AmbientRibbons />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        {/* Floating Liquid Glass navigation */}
        <header className="site-header">
          <div className="header-inner glass">
            <a href="/" className="brand chrome-layer" aria-label="PaceVant">
              <span className="brand-mark" aria-hidden="true">
                <ShieldCheck size={22} strokeWidth={2.1} />
              </span>
              <span className="brand-name-full">PaceVant</span>
            </a>

            <TabsList className="main-nav chrome-layer" aria-label={vi ? 'Điều hướng chính' : 'Main navigation'}>
              {tabs.map(item => (
                <TabsTrigger key={item.value} value={item.value} data-testid={item.testId}>
                  {tab === item.value && (
                    <motion.span
                      layoutId="nav-pill"
                      className="nav-pill"
                      transition={reduced ? {duration: 0} : {type: 'spring', stiffness: 520, damping: 42}}
                    />
                  )}
                  {item.label}
                  {item.value === 'live' && ownRunActive && <span className="nav-run-dot" aria-label={t.running} />}
                </TabsTrigger>
              ))}
            </TabsList>

            <div className="header-status chrome-layer">
              <LanguageSwitcher language={language} onChange={setLanguage} />
            </div>
          </div>
        </header>

        <main id="main-content" className="page-container" data-wide={tab === 'live'}>
          {config.isPending && (
            <div className="page-loading" role="status">
              <LoaderCircle size={20} className="animate-spin text-primary" aria-hidden="true" />
              <span>{t.processing}…</span>
            </div>
          )}

          {config.isError && (
            <div className="notice notice-warning" role="alert">
              {t.connection}
              <Button variant="outline" size="sm" onClick={() => void config.refetch()}>
                {t.reconnect}
              </Button>
            </div>
          )}

          {message && (
            <div className="notice notice-warning" role="alert">
              {message}
              {saved && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={start.isPending}
                  onClick={() => (saved.job_id ? void job.refetch() : void run(saved.body.scenario))}
                >
                  {t.retry}
                </Button>
              )}
            </div>
          )}

          {tab !== 'live' && session}

          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={reduced ? false : {opacity: 0, y: 6}}
              animate={{opacity: 1, y: 0}}
              exit={reduced ? undefined : {opacity: 0}}
              transition={{duration: 0.22, ease: [0.16, 1, 0.3, 1]}}
            >
              {tab === 'overview' && (
                <TabsContent value="overview">
                  <Overview language={language} onDemo={() => setTab('live')} onEvidence={() => setTab('history')} />
                </TabsContent>
              )}

              {tab === 'live' && (
                <TabsContent value="live" data-testid="live-demo-panel">
                  <div className="page-head">
                    <div>
                      <h1>
                        <em>PaceVant</em> Live Demo
                      </h1>
                      <p>
                        {vi
                          ? 'Chạy một giao dịch do AI đề xuất và theo dõi từng lớp bảo mật ra quyết định trên Avalanche Fuji.'
                          : 'Run an AI-proposed transaction and watch each security layer decide on Avalanche Fuji.'}
                      </p>
                    </div>
                    {session}
                  </div>

                  <div className="workspace-grid">
                    {/* Left: scenario & security-check configuration */}
                    <aside className="panel scenario-panel" aria-label={t.choose}>
                      <div className="panel-head">
                        <span className="panel-head-icon" aria-hidden="true">
                          <Layers3 size={17} />
                        </span>
                        <div>
                          <h2>{t.choose}</h2>
                          <p>{vi ? 'Chọn luồng giao dịch để kiểm tra.' : 'Choose the transaction flow to verify.'}</p>
                        </div>
                      </div>

                      <div className="compact-scenarios" role="group" aria-label={t.choose}>
                        {config.isPending
                          ? [0, 1].map(i => <div key={i} className="skeleton scenario-skeleton" />)
                          : config.data?.scenarios
                              .filter(value => value.id !== 'guard')
                              .map(value => {
                                const Icon = scenarioIcons[value.id];
                                const active = baseScenario === value.id;
                                return (
                                  <button
                                    key={value.id}
                                    type="button"
                                    data-testid={'scenario-' + value.id}
                                    aria-pressed={active}
                                    disabled={liveBusy}
                                    onClick={() => {
                                      setBaseScenario(value.id);
                                      setAttackPreset('none');
                                      setScenario(value.id);
                                    }}
                                    className={cn('compact-scenario', active && 'selected')}
                                  >
                                    <span className="scenario-icon" aria-hidden="true">
                                      <Icon size={18} strokeWidth={1.9} />
                                    </span>
                                    <span>
                                      <strong>{names[value.id]}</strong>
                                      <small>{descriptions[value.id]}</small>
                                    </span>
                                    {active ? (
                                      <CircleCheck size={18} className="scenario-check" aria-hidden="true" />
                                    ) : (
                                      <span />
                                    )}
                                  </button>
                                );
                              })}
                      </div>

                      {selectedScenario && (
                        <div className="scenario-terms" aria-label={vi ? 'Điều khoản giao dịch' : 'Transaction terms'}>
                          <dl className="fact-rows">
                            <div>
                              <dt>{t.amount}</dt>
                              <dd className="mono">
                                {units(selectedScenario.amount, selectedScenario.input_decimals, selectedScenario.input_decimals)}{' '}
                                {selectedScenario.token_in}
                              </dd>
                            </div>
                            <div>
                              <dt>{vi ? 'Tài sản' : 'Assets'}</dt>
                              <dd>
                                {selectedScenario.token_in === selectedScenario.token_out
                                  ? selectedScenario.token_in
                                  : selectedScenario.token_in + ' → ' + selectedScenario.token_out}
                              </dd>
                            </div>
                            <div>
                              <dt>{vi ? 'Người nhận' : 'Recipient'}</dt>
                              <dd title={selectedScenario.recipient_label}>{selectedScenario.recipient_label}</dd>
                            </div>
                          </dl>
                        </div>
                      )}

                      <AttackSelect
                        value={attackPreset}
                        onChange={setAttackPreset}
                        disabled={liveBusy}
                        language={language}
                        scenario={baseScenario}
                      />

                      <div className="run-action">
                        <button
                          type="button"
                          className="btn-primary"
                          disabled={liveBusy || start.isPending || (attackPreset === 'none' && !ready)}
                          onClick={() => (attackPreset === 'none' ? void run(scenario) : setAttackPreview(true))}
                          data-testid="run-scenario"
                        >
                          {ownRunActive || restoring ? (
                            <LoaderCircle size={17} className="animate-spin" aria-hidden="true" />
                          ) : (
                            <Play size={16} fill="currentColor" aria-hidden="true" />
                          )}
                          {restoring
                            ? vi
                              ? 'Đang khôi phục phiên'
                              : 'Restoring run'
                            : ownRunActive
                              ? vi
                                ? 'Đang xử lý kịch bản'
                                : 'Scenario running'
                              : attackPreset === 'none'
                                ? t.run
                                : vi
                                  ? 'Xem kịch bản tấn công'
                                  : 'Preview attack scenario'}
                        </button>
                        {attackPreset === 'none' && !ready && !ownRunActive && !restoring && (
                          <p className="mode-hint">{t.busy}</p>
                        )}
                      </div>

                      {quota && (
                        <div className="sidebar-foot">
                          <div className="quota-meter">
                            <span>{vi ? 'Lượt chạy còn lại hôm nay' : 'Runs left today'}</span>
                            <span>
                              {quota.remaining_today}/{quota.daily_limit}
                            </span>
                          </div>
                          {t.noWallet}
                        </div>
                      )}
                    </aside>

                    {/* Center: three stacked phase rows */}
                    <section className="panel graph-panel" aria-label={t.graph}>
                      <Suspense
                        fallback={
                          <div className="flow-placeholder" aria-busy="true">
                            <LoaderCircle size={20} className="animate-spin text-primary" aria-hidden="true" />
                            {t.processing}…
                          </div>
                        }
                      >
                        <Pipeline job={current} language={language} />
                      </Suspense>
                    </section>

                    {/* Right: verdict & evidence */}
                    <ExecutionStatus
                      job={current}
                      language={language}
                      mode={config.data?.mode}
                      onEvidence={() => {
                        setHistoryJob(current);
                        setDrawer(true);
                      }}
                    />
                  </div>
                </TabsContent>
              )}

              {tab === 'history' && (
                <TabsContent value="history">
                  <ExecutionHistory
                    jobs={history.data?.jobs ?? []}
                    language={language}
                    pending={history.isPending}
                    error={history.isError}
                    source={{data: source.data, pending: source.isPending, error: source.isError}}
                    onRefresh={() => {
                      void history.refetch();
                      void source.refetch();
                    }}
                    onOpen={value => void openHistory(value)}
                    onDemo={() => setTab('live')}
                  />
                </TabsContent>
              )}
            </motion.div>
          </AnimatePresence>
        </main>

        <SiteFooter language={language} />
      </Tabs>

      <AttackPreview
        scenario={baseScenario}
        value={attackPreset}
        open={attackPreview}
        onOpenChange={setAttackPreview}
        language={language}
      />

      <EvidenceDrawer job={historyJob ?? current} open={drawer} onOpenChange={setDrawer} language={language} />
    </div>
  );
}
