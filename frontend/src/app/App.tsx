import {Suspense, lazy, useEffect, useRef, useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {AnimatePresence, motion, useReducedMotion} from 'motion/react';
import {ArrowLeftRight, Banknote, Check, LoaderCircle, Play, Shield, ShieldX} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Tabs, TabsContent, TabsList, TabsTrigger} from '@/components/ui/tabs';
import {EvidenceDrawer} from '@/components/evidence';
const Pipeline = lazy(() => import('@/components/pipeline').then(module => ({default: module.Pipeline})));
import {AttackSelect, AttackPreview} from '@/components/attack-select';
import {LanguageSwitcher, SiteFooter} from '@/components/site-chrome';
import {Overview} from '@/components/overview';
import {ExecutionStatus, ExecutionHistory} from '@/components/execution-panels';
import {RunSession} from '@/components/run-session';
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
import {reason} from '@/lib/format';
import type {Job, ScenarioId} from '@/lib/types';
import {cn} from '@/lib/utils';
import {dictionary, type Language} from '@/lib/i18n';

const scenarioIcons = {payment: Banknote, swap: ArrowLeftRight, guard: ShieldX};
const scenarioColors = {payment: 'blue', swap: 'violet', guard: 'red'};

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

  return (
    <div className="app-shell">
      <Tabs value={tab} onValueChange={setTab}>
        {/* Floating Liquid Glass Header */}
        <header className="site-header">
          <div className="header-inner">
            <a href="/" className="brand">
              <span className="brand-icon">
                <Shield size={18} strokeWidth={2.4} />
              </span>
              PaceVant
              <span className="brand-divider" />
              <span className="brand-subtitle">AI Agent Security</span>
            </a>

            <TabsList className="main-nav" aria-label="Navigation">
              <TabsTrigger value="overview">{t.overview}</TabsTrigger>
              <TabsTrigger value="live" data-testid="tab-live">
                {t.demo}
                {ownRunActive && <span className="nav-run-dot" aria-label={t.running} />}
              </TabsTrigger>
              <TabsTrigger value="history" data-testid="tab-history">
                {t.evidence}
              </TabsTrigger>
            </TabsList>

            <div className="header-status">
              <LanguageSwitcher language={language} onChange={setLanguage} />
            </div>
          </div>
        </header>

        <main className="page-container new-page">
          {config.isPending && (
            <div className="page-loading" role="status" aria-label={t.processing}>
              <LoaderCircle size={22} className="animate-spin text-primary" />
              <span>{t.processing}</span>
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
                  onClick={() =>
                    saved.job_id
                      ? void job.refetch()
                      : void run(saved.body.scenario)
                  }
                >
                  {t.retry}
                </Button>
              )}
            </div>
          )}

          {(saved || activeId) && (
            <RunSession
              job={current}
              scenario={saved?.body.scenario ?? current?.scenario ?? scenario}
              restoring={
                restoring ||
                (!!saved && !saved.job_id && !start.isPending && !recovered.isError)
              }
              disconnected={
                job.isError ||
                (recovered.isError &&
                  !(
                    recovered.error instanceof ApiError &&
                    recovered.error.code === 'JUDGE_REQUEST_NOT_FOUND'
                  ))
              }
              needsResume={!!saved && !saved.job_id && recovered.isError && !start.isPending}
              pending={start.isPending}
              onResume={() =>
                saved && !saved.job_id ? void run(saved.body.scenario) : void job.refetch()
              }
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
          )}

          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={reduced ? false : {opacity: 0, filter: 'blur(6px)', y: 6}}
              animate={{opacity: 1, filter: 'blur(0px)', y: 0}}
              exit={{opacity: 0, filter: reduced ? 'blur(0px)' : 'blur(4px)'}}
              transition={{duration: 0.22, ease: [0.16, 1, 0.3, 1]}}
            >
              {tab === 'overview' && (
                <TabsContent value="overview">
                  <Overview language={language} onDemo={() => setTab('live')} />
                </TabsContent>
              )}

              {tab === 'live' && (
                <TabsContent value="live" data-testid="live-demo-panel">
                  <div className="workspace-grid">
                    {/* Left Sidebar: Scenario Selector & Attack Configuration */}
                    <aside className="workspace-card scenario-panel">
                      <div className="workspace-section-title">
                        <h2>{t.choose}</h2>
                      </div>

                      <div className="compact-scenarios">
                        {config.isPending
                          ? [0, 1].map(i => (
                              <div key={i} className="skeleton scenario-skeleton" />
                            ))
                          : config.data?.scenarios
                              .filter(value => value.id !== 'guard')
                              .map(value => {
                                const Icon = scenarioIcons[value.id];
                                return (
                                  <button
                                    key={value.id}
                                    data-testid={'scenario-' + value.id}
                                    aria-pressed={baseScenario === value.id}
                                    disabled={liveBusy}
                                    onClick={() => {
                                      setBaseScenario(value.id);
                                      setAttackPreset('none');
                                      setScenario(value.id);
                                    }}
                                    className={cn(
                                      'compact-scenario',
                                      baseScenario === value.id && 'selected',
                                    )}
                                  >
                                    <span
                                      className={
                                        'scenario-icon scenario-' +
                                        scenarioColors[value.id]
                                      }
                                    >
                                      <Icon size={18} strokeWidth={2} />
                                    </span>
                                    <span>
                                      <strong>{names[value.id]}</strong>
                                      <small>{descriptions[value.id]}</small>
                                    </span>
                                    {baseScenario === value.id && (
                                      <Check size={16} strokeWidth={2.4} />
                                    )}
                                  </button>
                                );
                              })}
                      </div>

                      <AttackSelect
                        value={attackPreset}
                        onChange={setAttackPreset}
                        disabled={liveBusy}
                        language={language}
                        scenario={baseScenario}
                      />

                      <div className="run-action">
                        <Button
                          className="w-full"
                          disabled={
                            liveBusy ||
                            start.isPending ||
                            (attackPreset === 'none' && !ready)
                          }
                          onClick={() =>
                            attackPreset === 'none'
                              ? void run(scenario)
                              : setAttackPreview(true)
                          }
                          data-testid="run-scenario"
                        >
                          {ownRunActive || restoring ? (
                            <LoaderCircle size={16} className="animate-spin" />
                          ) : (
                            <Play size={16} fill="currentColor" />
                          )}
                          {restoring
                            ? language === 'vi'
                              ? 'Đang khôi phục phiên'
                              : 'Restoring run'
                            : ownRunActive
                              ? language === 'vi'
                                ? 'Đang xử lý kịch bản'
                                : 'Scenario running'
                              : attackPreset === 'none'
                                ? t.run
                                : language === 'vi'
                                  ? 'Xem kịch bản tấn công'
                                  : 'Preview attack scenario'}
                        </Button>
                        {attackPreset === 'none' &&
                          !ready &&
                          !ownRunActive &&
                          !restoring && <p className="mode-hint">{t.busy}</p>}
                      </div>
                    </aside>

                    {/* Center Workspace: 3-Row Security Pipeline Graph */}
                    <section className="workspace-card graph-panel">
                      <Suspense
                        fallback={
                          <div className="flow-placeholder" aria-busy="true">
                            <LoaderCircle size={22} className="animate-spin text-primary" />
                            {t.processing}
                          </div>
                        }
                      >
                        <Pipeline job={current} language={language} />
                      </Suspense>
                    </section>

                    {/* Right Sidebar: Security Verdict & Results Panel */}
                    <ExecutionStatus
                      job={current}
                      language={language}
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
                    onRefresh={() => void history.refetch()}
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

      <EvidenceDrawer
        job={historyJob ?? current}
        open={drawer}
        onOpenChange={setDrawer}
        language={language}
      />
    </div>
  );
}
