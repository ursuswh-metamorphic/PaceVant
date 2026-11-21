import {Suspense, lazy, startTransition, useEffect, useRef, useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {motion, useReducedMotion} from 'motion/react';
import {LoaderCircle, Play} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Tabs, TabsContent} from '@/components/ui/tabs';
import {EvidenceDrawer} from '@/components/evidence';
const Pipeline = lazy(() => import('@/components/pipeline').then(module => ({default: module.Pipeline})));
import {AttackPreview} from '@/components/attack-select';
import {SiteFooter, SiteHeader, type BackendState} from '@/components/site-chrome';
import {Overview} from '@/components/overview';
import {RunComposer} from '@/components/live/run-composer';
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
import {describeReason} from '@/lib/run-feedback';
import type {Job, ScenarioId} from '@/lib/types';
import {dictionary, type Language} from '@/lib/i18n';

function savedState() {
  try {
    return {attempt: loadAttempt(), view: loadViewedRun(), error: ''};
  } catch (error) {
    return {attempt: null, view: null, error: (error as Error).message};
  }
}

export default function App() {
  const [initial] = useState(savedState);
  const [tab, setPageTab] = useState(initial.attempt || initial.view ? 'live' : 'overview');
  // The header (tabs, indicator, CTA) switches immediately; the page body renders as a
  // React transition that yields to the browser, so the header animation never stalls.
  const [navTab, setNavTab] = useState(tab);
  function setTab(value: string) {
    setNavTab(value);
    startTransition(() => setPageTab(value));
  }
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

  // Warm the graph bundle while the browser is idle, so opening Live Demo never
  // blocks the main thread on a network fetch + parse in the middle of the tab animation.
  useEffect(() => {
    const load = () => void import('@/components/pipeline');
    const idle = (window as Window & {requestIdleCallback?: (cb: () => void) => number}).requestIdleCallback;
    if (idle) idle(load);
    else window.setTimeout(load, 800);
  }, []);

  // A new page always opens at its top, so switching from deep in the Overview never lands mid-page.
  const firstTab = useRef(true);
  useEffect(() => {
    if (firstTab.current) {
      firstTab.current = false;
      return;
    }
    window.scrollTo({top: 0, left: 0, behavior: 'instant'});
  }, [tab]);

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
    enabled: config.isSuccess && tab === 'history',
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
          ? describeReason(error.code,language)
          : language==='vi'?'Phản hồi bị gián đoạn. Yêu cầu đã được lưu; dùng Tiếp tục để kiểm tra lại đúng phiên.':'The response was interrupted. Your exact request is saved; use Resume safely.',
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

  const ready = !!config.data?.configured && !config.data.busy && quota?.remaining_today !== 0;
  const vi = language === 'vi';
  const backend: BackendState = config.isError
    ? 'offline'
    : config.isPending
      ? 'pending'
      : config.data?.configured
        ? 'ready'
        : 'limited';
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
        <div className="ambient-grid" />
      </div>

      <Tabs value={navTab} onValueChange={setTab}>
        <SiteHeader
          tab={navTab}
          tabs={tabs}
          language={language}
          onLanguage={setLanguage}
          runActive={ownRunActive}
          runLabel={t.running}
          backend={backend}
          onDemo={() => setTab('live')}
        />

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

          {/* The next page mounts immediately and fades in: no blank frame, no page-height
              collapse, so the scrollbar and header never jump between tabs. */}
          <motion.div
              key={tab}
              initial={reduced ? false : {opacity: 0}}
              animate={{opacity: 1}}
              transition={{duration: 0.28, ease: [0.16, 1, 0.3, 1]}}
            >
              {tab === 'overview' && (
                <TabsContent value="overview" forceMount>
                  <Overview language={language} onDemo={() => setTab('live')} active={navTab === 'overview'} />
                </TabsContent>
              )}

              {tab === 'live' && (
                <TabsContent value="live" forceMount data-testid="live-demo-panel" className="live-page">
                  <h1 className="sr-only">PaceVant Live Demo</h1>

                  <RunComposer
                    language={language}
                    config={config.data}
                    loading={config.isPending}
                    scenario={baseScenario}
                    onScenario={id => {
                      setBaseScenario(id);
                      setAttackPreset('none');
                      setScenario(id);
                    }}
                    attack={attackPreset}
                    onAttack={setAttackPreset}
                    busy={liveBusy}
                    runDisabled={liveBusy || start.isPending || (attackPreset === 'none' && !ready)}
                    onRun={() => (attackPreset === 'none' ? void run(baseScenario) : setAttackPreview(true))}
                    onGuard={() => {setAttackPreset('none');void run('guard');}}
                    guardDisabled={liveBusy || start.isPending || !ready}
                    runIcon={
                      ownRunActive || restoring ? (
                        <LoaderCircle size={17} className="animate-spin" aria-hidden="true" />
                      ) : (
                        <Play size={16} fill="currentColor" aria-hidden="true" />
                      )
                    }
                    runLabel={
                      restoring
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
                              : 'Preview attack scenario'
                    }
                    hint={attackPreset === 'none' && !ready && !ownRunActive && !restoring ? t.busy : undefined}
                  />

                  <div className="workspace-grid">
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

                    {/* Right: run session + verdict. On desktop this column never sets the
                        row height (the graph does); it scrolls internally if needed. */}
                    <div className="status-slot">
                      <div className="status-slot-inner">
                        {session}
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
                    </div>
                  </div>
                </TabsContent>
              )}

              {tab === 'history' && (
                <TabsContent value="history" forceMount>
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
