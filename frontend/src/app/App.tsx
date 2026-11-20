import {useEffect, useRef, useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {AnimatePresence, motion, useReducedMotion} from 'motion/react';
import {ArrowLeftRight, Banknote, Check, ChevronRight, CircleHelp, ExternalLink, FileCheck2, History, Layers3, LoaderCircle, LockKeyhole, Play, Radio, RotateCcw, Shield, ShieldCheck, ShieldX, Wallet} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Tabs, TabsContent, TabsList, TabsTrigger} from '@/components/ui/tabs';
import {EvidenceDrawer, EvidenceSections, RawEvidence} from '@/components/evidence';
import {Pipeline} from '@/components/pipeline';
import {Result} from '@/components/result';
import {api, ApiError} from '@/lib/api';
import {beginAttempt, clearAttempt, loadAttempt, saveAttempt, type SavedAttempt} from '@/lib/recovery';
import {date, environment, intentAmount, object, reason, short, stage, text, units} from '@/lib/format';
import type {Job, ScenarioId} from '@/lib/types';
import {cn} from '@/lib/utils';

const scenarioIcons = {payment:Banknote, swap:ArrowLeftRight, guard:ShieldX};
const scenarioColors = {payment:'blue', swap:'violet', guard:'red'};
function savedState() {try {return {attempt:loadAttempt(), error:''};} catch (error) {return {attempt:null, error:(error as Error).message};}}

export default function App() {
  const [initial] = useState(savedState);
  const [tab, setTab] = useState('live');
  const [scenario, setScenario] = useState<ScenarioId>('payment');
  const [saved, setSaved] = useState<SavedAttempt | null>(initial.attempt);
  const savedRef = useRef(saved);
  const inFlight = useRef(false);
  const [activeId, setActiveId] = useState<string | undefined>(saved?.job_id);
  const [replay, setReplay] = useState<Job>();
  const [message, setMessage] = useState(initial.error);
  const [drawer, setDrawer] = useState(false);
  const [historyJob, setHistoryJob] = useState<Job>();
  const [opening, setOpening] = useState(false);
  const [storageBlocked] = useState(Boolean(initial.error));
  const queryClient = useQueryClient();
  const reduced = useReducedMotion();
  const config = useQuery({queryKey:['judge-config'], queryFn:api.config, refetchInterval:30000, retry:1});
  // Bootstrap the HttpOnly visitor cookie before parallel reads: competing
  // first responses must not replace the visitor identity during job creation.
  const source = useQuery({queryKey:['source'], queryFn:api.snapshot, enabled:config.isSuccess, staleTime:60000, refetchInterval:60000, retry:1});
  const history = useQuery({queryKey:['history'], queryFn:api.history, enabled:config.isSuccess, refetchInterval:30000, retry:1});
  const job = useQuery({queryKey:['job',activeId], queryFn:() => api.job(activeId!), enabled:!!activeId,
    refetchInterval:query => query.state.data?.terminal ? false : 2500, retry:1});
  const recovered = useQuery({queryKey:['request',saved?.key], queryFn:() => api.byKey(saved!.key),
    enabled:config.isSuccess && !!saved && !saved.job_id, refetchInterval:5000, retry:false});
  const current = replay ?? job.data;
  const selected = config.data?.scenarios.find(value => value.id === scenario);
  const context = stage(current?.workflow, 'OWNER_AUTHORITY');
  const policy = object(context?.proof_policy);
  const proposal = stage(current?.workflow, 'AGENT_PROPOSAL');
  const quota = config.data?.quota;
  const liveBusy = storageBlocked || !!saved || !!current && !current.terminal || opening;

  function retain(value: SavedAttempt | null) {savedRef.current = value; setSaved(value);}
  function accept(value: Job, attempt: SavedAttempt) {
    if (value.job_id !== attempt.job_id && attempt.job_id) throw new Error('Recovered workflow identity mismatch');
    setActiveId(value.job_id); setReplay(undefined);
    queryClient.setQueryData(['job', value.job_id], value);
    saveAttempt({...attempt, job_id:value.job_id}); retain({...attempt, job_id:value.job_id});
  }
  useEffect(() => {
    if (recovered.data && savedRef.current) accept(recovered.data, savedRef.current);
  }, [recovered.data]);
  useEffect(() => {
    if (job.data?.terminal && savedRef.current?.job_id === job.data.job_id) {
      clearAttempt(); retain(null);
      void queryClient.invalidateQueries({queryKey:['history']});
      void queryClient.invalidateQueries({queryKey:['judge-config']});
    }
  }, [job.data?.terminal, job.data?.job_id]);

  const start = useMutation({mutationFn:async (id:ScenarioId) => {
    const attempt = savedRef.current ?? beginAttempt(id);
    retain(attempt); setScenario(attempt.body.scenario); setMessage(''); setReplay(undefined);
    if (!attempt.job_id) setActiveId(undefined);
    try {const value = await api.byKey(attempt.key); return {value, attempt};}
    catch (error) {if (!(error instanceof ApiError) || error.code !== 'JUDGE_REQUEST_NOT_FOUND') throw error;}
    return {value:await api.start(attempt.body.scenario, attempt.key), attempt};
  }, onSuccess:({value,attempt}) => accept(value,attempt), onError:(error) => setMessage(error instanceof ApiError ? reason(error.code) : 'The response was interrupted. Your exact request is saved; use Resume safely.')});

  async function run(id:ScenarioId) {
    if (inFlight.current) return;
    inFlight.current = true;
    try {await start.mutateAsync(id);} catch {/* The saved identity is deliberately retained. */}
    finally {inFlight.current = false;}
  }
  async function showReplay(id:ScenarioId) {
    setOpening(true); setMessage('');
    try {setReplay(await api.replay(id)); setScenario(id); setTab('live');}
    catch (error) {setMessage(error instanceof ApiError ? reason(error.code) : 'Recorded evidence could not be loaded.');}
    finally {setOpening(false);}
  }
  async function openHistory(value:Job) {
    setOpening(true);
    try {setHistoryJob(await api.job(value.job_id)); setDrawer(true);}
    catch {setMessage('The selected execution record could not be loaded.');}
    finally {setOpening(false);}
  }
  const mode = environment(current?.environment ?? 'ANVIL_FORK');
  const activeBalances = Array.isArray(context?.balances) ? context.balances.map(String) : null;
  const treasuryUsdc = activeBalances?.[0] ?? source.data?.balances?.usdc;
  const treasuryWavax = activeBalances?.[1] ?? source.data?.balances?.wavax;
  const lossBps = policy.max_relative_loss_bps ?? source.data?.policy?.max_relative_loss_bps;
  const oracle = object(context?.oracle);
  const observed = text(current?.source_block ?? context?.block_number ?? source.data?.block_number, 'Unavailable');
  const overview = <div className="overview-grid" data-testid="system-overview">
    <div className="overview-item"><span className="metric-icon"><Wallet size={18}/></span><div><p className="metric-label">{context ? 'Isolated run treasury' : 'Source treasury snapshot'}</p><strong>{units(treasuryUsdc)} <span>USDC</span></strong><small>{units(treasuryWavax,18,8)} WAVAX · {context ? 'Verified pre-execution state' : source.data?.status === 'VERIFIED_READ' ? 'Public on-chain read' : 'Recorded observation'}</small></div></div>
    <div className="overview-item"><span className="metric-icon"><ShieldCheck size={18}/></span><div><p className="metric-label">Economic policy</p><strong>{lossBps !== undefined ? Number(lossBps)/100 + '%' : 'Unavailable'} <span>loss bound</span></strong><small>{context ? 'Owner-defined fork policy' : source.data?.status === 'VERIFIED_READ' ? 'Observed source policy' : 'Recorded source policy'} · never relaxed</small></div></div>
    <div className="overview-item"><span className="metric-icon"><Radio size={18}/></span><div><p className="metric-label">Oracle reference</p><strong>{context && oracle.price_source ? 'Chainlink' : source.data?.oracle?.status === 'FRESH' ? 'Fresh round observed' : source.data?.oracle?.status === 'STALE_FOR_OWNER_WINDOW' ? 'Waiting for a round' : 'Recorded / unverified'}</strong><small>{context ? 'Pinned round data in evidence' : source.data?.oracle?.age_seconds !== undefined ? source.data.oracle.age_seconds + ' seconds old at source block' : 'Freshness checked for every new run'}</small></div></div>
    <div className="overview-item"><span className="metric-icon"><Layers3 size={18}/></span><div><p className="metric-label">Execution source</p><strong className="font-mono text-base!">{observed === 'Unavailable' ? observed : '#' + observed}</strong><small>{context ? 'Actual fork source / pinned block' : 'Historical snapshot · not live readiness'}</small></div></div>
  </div>;

  return <div className="app-shell"><Tabs value={tab} onValueChange={setTab}>
    <header className="site-header"><div className="header-inner"><a href="/" className="brand" aria-label="PaceVant home"><span className="brand-icon"><Shield size={23} strokeWidth={2}/></span>PaceVant<span className="brand-divider"/><span className="brand-subtitle">AI Treasury</span></a>
      <TabsList className="main-nav" aria-label="Main navigation"><TabsTrigger value="live" data-testid="tab-live"><Play size={14}/>Live Demo</TabsTrigger><TabsTrigger value="security" data-testid="tab-security"><ShieldCheck size={15}/>Security & Policies</TabsTrigger><TabsTrigger value="history" data-testid="tab-history"><History size={15}/>History</TabsTrigger></TabsList>
      <div className="header-status"><span className="network-chip"><span className="network-mark">A</span>{mode}</span><a href="/judge/documentation" target="_blank" rel="noreferrer" aria-label="Open documentation"><CircleHelp size={18}/></a></div></div></header>
    <main className="page-container"><section className="page-heading"><div><p className="eyebrow"><span className="tiny-blue-line"/> POLICY-ATTESTED CONTRACT EXECUTION</p><h1>Secure AI agent execution.</h1><p className="page-subtitle">AI-powered transactions protected by simulation, formal verification, and on-chain policy enforcement.</p></div><div className="readiness-label"><span className={cn('status-dot', config.data?.configured && !config.data.busy ? 'dot-green' : 'dot-amber')}/>{config.isPending ? 'Connecting to backend' : !config.data?.configured ? 'Live fork unavailable' : config.data.busy ? 'A verification is in progress' : 'Fork worker available'}<small>Isolated execution · no public treasury spending</small></div></section>
      {config.data?.semantic_scope?.startsWith('SCRIPTED') && <div className="notice">LOCAL TEST: scripted semantic responses. This is not a real-model run.</div>}
      {config.isError && <div className="notice notice-warning" role="alert">The demo API is unavailable. No transaction was requested.<Button size="sm" variant="outline" onClick={() => void config.refetch()}>Reconnect</Button></div>}
      {message && <div className="notice notice-warning" role="alert">{message}{saved && <Button variant="outline" size="sm" disabled={start.isPending} onClick={() => void run(saved.body.scenario)}><RotateCcw size={13}/>Resume saved request</Button>}</div>}
      {saved && !message && <div className="notice"><LoaderCircle size={15} className={cn(!reduced && 'animate-spin')}/>{saved.job_id ? 'Your isolated run is in progress. Refreshing does not restart it.' : 'An unacknowledged request is saved in this tab.'}{!saved.job_id && <Button variant="outline" size="sm" onClick={() => void run(saved.body.scenario)}>Resume safely</Button>}</div>}
      <AnimatePresence mode="wait"><motion.div key={tab} initial={reduced ? false : {opacity:0,y:5}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-3}} transition={{duration:.16}}>
      {tab === 'live' && <TabsContent value="live" data-testid="live-demo-panel">{overview}<div className="demo-grid">
        <div className="scenario-column"><div className="section-heading"><h2>Choose a scenario</h2><span>{quota ? quota.remaining_today + ' of ' + quota.daily_limit + ' runs left today' : 'Server-enforced limits'}</span></div>
          <div className="scenario-list">{config.isPending ? [0,1,2].map(index => <div key={index} className="skeleton scenario-skeleton"/>) : config.data?.scenarios.map(value => {
            const Icon = scenarioIcons[value.id], active = scenario === value.id;
            return <motion.article key={value.id} whileHover={reduced ? undefined : {y:-2}} className={cn('scenario-card', 'scenario-' + scenarioColors[value.id], active && 'scenario-selected')} data-testid={'scenario-' + value.id}>
              <div className="scenario-top"><span className="scenario-icon"><Icon size={21}/></span><div><h3><button className="text-left" aria-label={'Select ' + value.title} aria-pressed={active} disabled={liveBusy} onClick={() => setScenario(value.id)}>{value.title}</button></h3><span className="scenario-type">{value.id === 'guard' ? 'SECURITY SCENARIO' : value.operation}</span></div>{active && <span className="selected-mark"><Check size={12}/></span>}</div>
              <p>{value.description}</p><div className="scenario-bottom"><span>{units(value.amount,value.input_decimals,8)} {value.token_in}{value.id === 'swap' && <span className="text-slate-400"> / WAVAX</span>}</span><Button size="sm" variant={active ? 'default' : 'outline'} disabled={liveBusy || start.isPending || !config.data?.configured || config.data.busy || quota?.remaining_today === 0} onClick={() => {setScenario(value.id); void run(value.id);}} data-testid={'run-' + value.id}><Play size={11} fill="currentColor"/>{value.id === 'payment' ? 'Run Payment Demo' : value.id === 'swap' ? 'Run Swap Demo' : 'Test Security Guard'}</Button></div>
            </motion.article>;
          })}</div>
          <div className="replay-card"><span><FileCheck2 size={17}/></span><div><h3>A verified recording is always honest.</h3><p>Review real saved evidence when a live dependency is unavailable.</p><button onClick={() => void showReplay(scenario)} disabled={opening || !config.data?.replay_available.includes(scenario)} data-testid="view-replay">View verified demo <ChevronRight size={13}/></button></div></div>
          <p className="small-note"><LockKeyhole size={12}/>No wallet, credentials or test tokens needed. One isolated fork at a time.</p>
        </div>
        <div className="workflow-card"><div className="workflow-heading"><div><span className="eyebrow">EXECUTION WORKSPACE</span><h2>Trust is checked. Not assumed.</h2></div><span className="environment-pill">{mode}</span></div>
          <div className="transaction-strip"><div><span>Requested operation</span><strong>{current?.workflow?.intent.operation === 'TOKEN_PAYMENT' ? 'USDC Payment' : current?.workflow ? 'Exact-input Swap' : selected?.id === 'payment' ? 'USDC Payment' : 'Exact-input Swap'}</strong></div><div><span>Exact input</span><strong>{current?.workflow ? units(current.workflow.intent.amount,current.workflow.intent.token_in === text(context?.wavax) ? 18 : 6,8) : selected ? units(selected.amount,selected.input_decimals,8) : 'Unavailable'} <span className="text-slate-400">{current?.workflow?.intent.token_in === text(context?.wavax) ? 'WAVAX' : selected?.token_in ?? 'USDC'}</span></strong></div><div><span>Recipient</span><strong className="font-mono text-xs!">{current?.workflow ? short(current.workflow.intent.recipient) : selected?.id === 'payment' ? 'Approved fork EOA' : 'PolicyVault'}</strong></div></div>
          {current?.environment === 'VERIFIED_REPLAY' && <div className="replay-banner"><History size={13}/>RECORDED EVIDENCE · {date(current.recorded_at)} · No new execution</div>}
          {start.isPending && !current && <p className="requesting-state"><LoaderCircle size={13} className={cn(!reduced && 'animate-spin')}/>Submitting the saved request. No stage has been reported yet.</p>}
          <Pipeline job={current}/><Result job={current} onEvidence={() => {setHistoryJob(current); setDrawer(true);}}/>
        </div>
      </div>
      <div className="proposal-panel"><span className="proposal-icon"><Layers3 size={18}/></span><div className="min-w-0 flex-1"><div className="flex gap-3 items-center mb-1"><h3>Bounded AI proposal</h3><span className="text-xs text-slate-400">The model proposes. Owner policy authorizes.</span></div><p>{proposal ? text(proposal.explanation) : 'The actual model explanation and structured terms appear here after the proposal is validated.'}</p>{proposal && <details className="mt-2"><summary className="text-xs text-primary cursor-pointer">Authorized objective & structured proposal</summary><RawEvidence value={{objective:current?.workflow?.intent.objective, proposal:proposal.candidate_plan}}/></details>}</div><ShieldCheck size={18} className="text-slate-300"/></div>
      </TabsContent>}
      {tab === 'security' && <TabsContent value="security" className="security-layout" data-testid="security-panel"><div className="security-intro"><span className="section-icon"><ShieldCheck size={22}/></span><h2>Security you can inspect.</h2><p>Every claim is tied to recorded workflow evidence. Expand the policy, effects, proof and attestation for the selected run.</p><div className="security-principles"><div><Check size={15}/>Exact intent & calldata binding</div><div><Check size={15}/>Independent oracle reference</div><div><Check size={15}/>Atomic actual-effect enforcement</div><div><Check size={15}/>Nonce, expiry & spending limits</div></div><p className="small-note">Z3 runs off-chain. Its certificate is conditional on the disclosed price bands and trusted components; it is not a zero-knowledge proof.</p><span className="operator-note"><LockKeyhole size={14}/>{config.data?.operator.enabled ? 'Authenticated operator API is separately enabled.' : 'Public Fuji operator mode: not activated.'}</span></div><div className="panel px-6"><div className="section-heading pt-5"><h3>Policy & verification details</h3><span>{current ? environment(current.environment) : 'No run selected'}</span></div><EvidenceSections job={current}/></div></TabsContent>}
      {tab === 'history' && <TabsContent value="history" className="panel history-panel" data-testid="history-panel"><div className="section-heading"><div><h2>Execution history</h2><p className="text-sm text-muted-foreground mt-1">Your actual isolated runs. No example transactions.</p></div><Button variant="outline" size="sm" onClick={() => void history.refetch()}><RotateCcw size={13}/>Refresh</Button></div>
        {history.data?.jobs.length ? <div className="table-wrap"><table><thead><tr>{['Time','Operation','Amount','Environment','Status','Evidence'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{history.data.jobs.map(value => <tr key={value.job_id}><td>{date(value.created_at)}</td><td><span className="font-medium">{value.scenario === 'payment' ? 'USDC Payment' : value.scenario === 'guard' ? 'Security guard' : 'Exact-input Swap'}</span><small>{short(value.job_id)}</small></td><td>{value.workflow ? intentAmount(value.workflow) : 'Pending'}</td><td><span className="environment-pill">{environment(value.environment)}</span></td><td><span className={cn('status-badge', value.status === 'CONFIRMED' ? 'badge-green' : value.status === 'REJECTED' ? 'badge-red' : 'badge-amber')}>{value.status}</span></td><td><Button variant="ghost" size="sm" onClick={() => void openHistory(value)}><FileCheck2 size={14}/>Details</Button></td></tr>)}</tbody></table></div>
          : <div className="history-empty"><span><History size={27}/></span><h3>{history.isError ? 'History is temporarily unavailable' : 'A clean execution history starts here.'}</h3><p>Run a scenario to create a real verification record, or open a clearly labeled recording.</p><Button variant="outline" onClick={() => setTab('live')}>Explore Live Demo</Button></div>}
      </TabsContent>}
      </motion.div></AnimatePresence>
      <footer><span><Shield size={12}/>PaceVant · Policy-Attested Contract Execution</span><span>Fuji testnet source · Isolated fork execution · No investment or profit claims</span><a href="/judge/documentation" target="_blank" rel="noreferrer">Documentation<ExternalLink size={11}/></a></footer>
    </main>
  </Tabs><EvidenceDrawer job={historyJob ?? current} open={drawer} onOpenChange={setDrawer}/></div>;
}
