import {nodeTitle} from '@/lib/workflow-nodes';
import {useEffect, useRef, useState, type KeyboardEvent} from 'react';
import {useReducedMotion} from 'motion/react';
import {ArrowLeftRight, Banknote, Clock3, Layers3, Pause, Play, ShieldX, Server} from 'lucide-react';
import {overviewCopy, recordedRuns, type ShowcaseId} from '@/lib/overview-copy';
import {workflowNodes, type ModuleState} from '@/lib/workflow-nodes';
import {PHASES, phaseMembers, summarizePhase} from '@/lib/phases';
import {dictionary, type Language} from '@/lib/i18n';
import {cn} from '@/lib/utils';
import {moduleIcons, stateIcons} from '../pipeline-icons';
import {VerdictMark} from '../illustrations';
import {BrandMark} from '../site-chrome';

const ORDER: ShowcaseId[] = ['payment', 'swap', 'guard'];
const TAB_ICONS = {payment: Banknote, swap: ArrowLeftRight, guard: ShieldX};
const STEP_MS = 280;
const HOLD_MS = 2000; // hold each finished scenario before moving to the next

/*
 * A miniature of the Live Demo that replays the three recorded runs in
 * fixtures/judge. It never calls the API and is labelled as a replay; the
 * outcome of each tab (all verified, or rejected at Trusted Builder) is the
 * outcome of the recording it names.
 */
export function Showcase({language, onDemo, enabled = true}: {language: Language; onDemo: () => void; enabled?: boolean}) {
  const t = overviewCopy[language].showcase;
  const states = dictionary[language];
  const vi = language === 'vi';
  const reduced = useReducedMotion();
  const [active, setActive] = useState<ShowcaseId>('payment');
  const [round, setRound] = useState(0);
  const [step, setStep] = useState(0);
  const [visible, setVisible] = useState(false);
  const [paused, setPaused] = useState(false);
  const [hovering, setHovering] = useState(false);
  const rootRef = useRef<HTMLElement>(null);
  const tabRefs = useRef<Record<ShowcaseId, HTMLButtonElement | null>>({payment: null, swap: null, guard: null});

  const run = recordedRuns[active];
  const resolveCount = run.rejectAt !== undefined ? run.rejectAt + 1 : workflowNodes.length;
  const done = step >= resolveCount;

  // Start the replay only once the window is actually on screen.
  useEffect(() => {
    const node = rootRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }
    // Keep observing: the tour only runs while the showcase is on screen.
    const observer = new IntersectionObserver(entries => {
      setVisible(entries.some(entry => entry.isIntersecting));
    }, {threshold: 0, rootMargin: '0px 0px -60px 0px'});
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (reduced) {
      setStep(resolveCount);
      return;
    }
    setStep(0);
    // Stop ticking as soon as the user leaves the Overview, so the next page's render is never interrupted.
    if (!visible || !enabled) return;
    let current = 0;
    const timer = window.setInterval(() => {
      current += 1;
      setStep(current);
      if (current >= resolveCount) window.clearInterval(timer);
    }, STEP_MS);
    return () => window.clearInterval(timer);
  }, [active, round, reduced, resolveCount, visible, enabled]);

  // Continuous tour: hold the finished scenario, then move to the next one.
  // Stops while paused, hovered, off screen, or when reduced motion is requested.
  const autoplay = !reduced && !paused && !hovering && visible && enabled;
  useEffect(() => {
    if (!done || !autoplay) return;
    const timer = window.setTimeout(() => {
      setActive(current => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length]);
    }, HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [done, autoplay, active, round]);

  const stateOf = (index: number): ModuleState => {
    if (index < step) return run.rejectAt === index ? 'rejected' : 'passed';
    if (index === step && !done) return 'running';
    return done ? 'skipped' : 'idle';
  };
  const nodeStates = workflowNodes.map((_, index) => stateOf(index));
  const passed = nodeStates.filter(state => state === 'passed').length;
  const tone = !done ? 'running' : run.rejectAt !== undefined ? 'rejected' : 'passed';
  const verdict = !done ? t.verdict.running : t.verdict[active];

  function onTabKey(event: KeyboardEvent<HTMLButtonElement>) {
    const index = ORDER.indexOf(active);
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % ORDER.length;
    else if (event.key === 'ArrowLeft') next = (index + ORDER.length - 1) % ORDER.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = ORDER.length - 1;
    else return;
    event.preventDefault();
    setActive(ORDER[next]);
    tabRefs.current[ORDER[next]]?.focus();
  }

  return (
    <section className="showcase" ref={rootRef} aria-label={t.label}>
      <div className="showcase-bar">
        <div className="showcase-tabs" role="tablist" aria-label={t.label}>
          {ORDER.map(id => {
            const Icon = TAB_ICONS[id];
            const selected = id === active;
            return (
              <button
                key={id}
                ref={node => {
                  tabRefs.current[id] = node;
                }}
                type="button"
                role="tab"
                id={`showcase-tab-${id}`}
                aria-selected={selected}
                aria-controls="showcase-panel"
                tabIndex={selected ? 0 : -1}
                onKeyDown={onTabKey}
                onClick={() => {
                  if (selected) setRound(value => value + 1);
                  setActive(id);
                }}
                className={cn('showcase-tab', selected && 'is-active', id === 'guard' && 'is-guard')}
              >
                <Icon size={15} aria-hidden="true" />
                {t.tabs[id]}
              </button>
            );
          })}
        </div>
      </div>

      <div className="showcase-stage">
        <div
          className="showcase-window"
          id="showcase-panel"
          role="tabpanel"
          aria-labelledby={`showcase-tab-${active}`}
          onPointerEnter={() => setHovering(true)}
          onPointerLeave={() => setHovering(false)}
        >
          <div className="sw-titlebar">
            <BrandMark size={22} />
            <strong>{t.window}</strong>
            <span className={cn('chip', 'tone-' + (tone === 'running' ? 'running' : tone))}>
              {!done ? <span className="live-dot" aria-hidden="true" /> : null}
              {verdict[0]}
            </span>
            <span className="sw-badge">{t.badge}</span>
            {!reduced && (
              <button
                type="button"
                className="sw-pause"
                aria-pressed={paused}
                aria-label={paused ? (vi ? 'Tiếp tục tự chạy' : 'Resume autoplay') : vi ? 'Tạm dừng tự chạy' : 'Pause autoplay'}
                title={paused ? (vi ? 'Tiếp tục tự chạy' : 'Resume autoplay') : vi ? 'Tạm dừng tự chạy' : 'Pause autoplay'}
                onClick={() => setPaused(value => !value)}
              >
                {paused ? (
                  <Play size={12} fill="currentColor" aria-hidden="true" />
                ) : (
                  <Pause size={12} fill="currentColor" aria-hidden="true" />
                )}
              </button>
            )}
          </div>

          <div className="sw-body">
            <aside className="sw-side">
              <p className="sw-kicker">{vi ? 'Kịch bản' : 'Scenario'}</p>
              <strong className="sw-scenario">{t.scenario[active][0]}</strong>
              <p className="sw-terms">{t.scenario[active][1]}</p>
              <dl className="sw-facts">
                <div>
                  <dt>
                    <Layers3 size={13} aria-hidden="true" />
                    {t.facts[0]}
                  </dt>
                  <dd>{run.stages}</dd>
                </div>
                <div>
                  <dt>
                    <Clock3 size={13} aria-hidden="true" />
                    {t.facts[1]}
                  </dt>
                  <dd>{run.seconds} s</dd>
                </div>
                <div>
                  <dt>
                    <Server size={13} aria-hidden="true" />
                    {t.facts[2]}
                  </dt>
                  <dd>{t.env}</dd>
                </div>
              </dl>
            </aside>

            <ol className="sw-phases">
              {PHASES.map((phase, phaseIndex) => {
                const members = phaseMembers(phaseIndex);
                const summary = summarizePhase(members.map(index => nodeStates[index]), done);
                return (
                  <li className="sw-phase" key={phase.title[1]}>
                    <div className="sw-phase-head">
                      <span className="sw-phase-num">{String(phaseIndex + 1).padStart(2, '0')}</span>
                      <strong>{phase.title[vi ? 0 : 1]}</strong>
                      <span className="sw-phase-desc">{phase.description[vi ? 0 : 1]}</span>
                      <span className={cn('sw-phase-state', 'tone-' + summary)}>{states[summary]}</span>
                    </div>
                    <ol className="sw-nodes">
                      {members.map(index => {
                        const state = nodeStates[index];
                        const Icon = moduleIcons[index];
                        const Glyph = stateIcons[state];
                        return (
                          <li key={index} className={cn('sw-node', 'state-' + state)}>
                            <span className="sw-node-icon" aria-hidden="true">
                              <Icon size={15} strokeWidth={1.9} />
                            </span>
                            <span className="sw-node-label">{nodeTitle(index, language)}</span>
                            <span className="sw-tip" aria-hidden="true">
                              {workflowNodes[index].description[vi ? 0 : 1]}
                            </span>
                            <span className="sw-node-state" aria-label={states[state]}>
                              <Glyph size={11} strokeWidth={3} aria-hidden="true" className={state === 'running' ? 'spin' : undefined} />
                            </span>
                          </li>
                        );
                      })}
                    </ol>
                  </li>
                );
              })}
            </ol>

            <aside className="sw-verdict" data-tone={tone} aria-live="polite">
              <VerdictMark tone={tone} />
              <strong>{verdict[0]}</strong>
              <p>{verdict[1]}</p>
              {done && run.reason && <code className="sw-reason">{run.reason}</code>}
              <div className="sw-progress" aria-hidden="true">
                <span style={{width: `${(passed / workflowNodes.length) * 100}%`}} />
              </div>
              <small className="sw-progress-label">
                {passed}/{workflowNodes.length} {t.modules}
              </small>
              <button type="button" className="sw-open" onClick={onDemo}>
                <Play size={13} fill="currentColor" aria-hidden="true" />
                {vi ? 'Chạy thật trong Live Demo' : 'Run it live'}
              </button>
            </aside>
          </div>
        </div>
      </div>
    </section>
  );
}
