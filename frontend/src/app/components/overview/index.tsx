import {nodeTitle} from '@/lib/workflow-nodes';
import type {PointerEvent, ReactNode} from 'react';
import {motion, type Variants} from 'motion/react';
import {
  ArrowLeftRight,
  ArrowRight,
  Banknote,
  ChevronDown,
  FileSearch,
  Layers,
  PlayCircle,
  ShieldCheck,
  Sigma,
  Sparkles,
  Zap,
} from 'lucide-react';
import {overviewCopy} from '@/lib/overview-copy';
import {workflowNodes} from '@/lib/workflow-nodes';
import {PHASES, phaseMembers} from '@/lib/phases';
import type {Language} from '@/lib/i18n';
import {LayerStackArt} from '../illustrations';
import {moduleIcons} from '../pipeline-icons';
import {Showcase} from './showcase';
import './overview.css';

const EASE = [0.16, 1, 0.3, 1] as const;

/* Scroll choreography. Fires as soon as a panel's top edge is ~8% inside the
   viewport (so a slow scroll never waits on it) and runs short: 0.45s fade/rise,
   children 50ms apart, all transform/opacity only (no blur, no layout work).
   MotionConfig (reducedMotion="user") removes the movement for users who ask. */
const group: Variants = {
  hidden: {opacity: 0, y: 18},
  show: {opacity: 1, y: 0, transition: {duration: 0.45, ease: EASE, staggerChildren: 0.05}},
};
const item: Variants = {
  hidden: {opacity: 0, y: 14},
  show: {opacity: 1, y: 0, transition: {duration: 0.45, ease: EASE}},
};
const inView = {initial: 'hidden', whileInView: 'show', viewport: {once: true, amount: 0, margin: '0px 0px -8% 0px'}} as const;

/** One full-height panel: each part of the page reads as its own screen. */
function Panel({children, className, id, label}: {children: ReactNode; className: string; id?: string; label: string}) {
  return (
    <motion.section id={id} className={'ov-panel ' + className} aria-labelledby={label} variants={group} {...inView}>
      {children}
    </motion.section>
  );
}

/** Which real modules implement each of the four core layers (indices into workflowNodes). */
const LAYER_MODULES = [[0, 1, 5], [3, 4], [6], [7, 8, 9, 10, 11]];

/** Soft light that follows the pointer across glass cards (.spot). Purely visual. */
function trackSpotlight(event: PointerEvent<HTMLDivElement>) {
  const card = (event.target as HTMLElement).closest<HTMLElement>('.spot');
  if (!card) return;
  const rect = card.getBoundingClientRect();
  card.style.setProperty('--mx', `${event.clientX - rect.left}px`);
  card.style.setProperty('--my', `${event.clientY - rect.top}px`);
}

export function Overview({language, onDemo, active = true}: {language: Language; onDemo: () => void; active?: boolean}) {
  const t = overviewCopy[language];
  const vi = language === 'vi';
  const layerIcons = [ShieldCheck, Zap, Sigma, Layers];
  const proofIcons = [Banknote, ArrowLeftRight, FileSearch];
  const proofLabels = vi
    ? ['Chạy kịch bản này', 'Chạy kịch bản này', 'Mở Live Demo']
    : ['Run this scenario', 'Run this scenario', 'Open the Live Demo'];

  return (
    <div className="overview" onPointerMove={trackSpotlight}>
      {/* 1 · Hero — the only thing on the first screen */}
      <motion.section
        className="hero"
        aria-labelledby="overview-headline"
        initial="hidden"
        animate="show"
        variants={{show: {transition: {staggerChildren: 0.08, delayChildren: 0.05}}}}
      >
        <motion.p className="eyebrow-chip" variants={item}>
          <Sparkles size={14} aria-hidden="true" />
          {t.eyebrow}
        </motion.p>
        <motion.h1 id="overview-headline" variants={item}>
          <span className="h1-lead">{t.headline[0]}</span> <span className="hl">{t.headline[1]}</span>
        </motion.h1>
        <motion.p className="hero-lede" variants={item}>
          {t.description}
        </motion.p>
        <motion.div className="hero-actions" variants={item}>
          <button type="button" className="btn-primary" onClick={onDemo} data-testid="launch-demo">
            {t.cta}
            <ArrowRight size={18} className="arrow-nudge" aria-hidden="true" />
          </button>
          <a className="btn-ghost" href="#how-it-works">
            <PlayCircle size={18} aria-hidden="true" />
            {t.secondary}
          </a>
        </motion.div>
        <a className="scroll-cue" href="#showcase" aria-label={vi ? 'Cuộn xuống' : 'Scroll down'}>
          <ChevronDown size={18} aria-hidden="true" />
        </a>
      </motion.section>

      {/* 2 · Product showcase */}
      <Panel className="showcase-panel" id="showcase" label="showcase-heading">
        <h2 id="showcase-heading" className="sr-only">
          {t.showcase.label}
        </h2>
        <motion.div variants={item}>
          <Showcase language={language} onDemo={onDemo} enabled={active} />
        </motion.div>
      </Panel>

      {/* 3 · Core technology — hover a layer to swap its text for the modules behind it */}
      <Panel className="core" label="core-heading">
        <motion.div className="section-head" variants={item}>
          <p className="eyebrow">{t.coreEyebrow}</p>
          <h2 id="core-heading">{t.coreTitle}</h2>
          <p>{t.coreBody}</p>
        </motion.div>
        <div className="core-body">
          <motion.div className="core-art" variants={item}>
            <LayerStackArt labels={t.stack.map(([label, sub]) => [label, sub] as [string, string])} />
          </motion.div>
          <ul className="core-layers">
            {t.layers.map(([title, body], index) => {
              const Icon = layerIcons[index];
              return (
                <motion.li key={title} className="spot" tabIndex={0} variants={item}>
                  <span className="core-icon" aria-hidden="true">
                    <Icon size={20} strokeWidth={1.9} />
                  </span>
                  <h3>{title}</h3>
                  {/* Both faces share one grid cell: the card never changes height. */}
                  <div className="layer-swap">
                    <p className="layer-face">{body}</p>
                    <div className="layer-modules">
                      <span className="reveal-label">{vi ? 'Mô-đun thực hiện' : 'Implemented by'}</span>
                      <span className="module-chips">
                        {LAYER_MODULES[index].map(module => (
                          <span key={module}>{nodeTitle(module,language)}</span>
                        ))}
                      </span>
                    </div>
                  </div>
                </motion.li>
              );
            })}
          </ul>
        </div>
        <motion.dl className="facts-strip" variants={item}>
          {t.facts.map(([value, label]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </motion.dl>
      </Panel>

      {/* 4 · How it works — hover a module to read what it checks (floating, no reflow) */}
      <Panel className="journey-section" id="how-it-works" label="phases-heading">
        <motion.div className="section-head" variants={item}>
          <p className="eyebrow">{t.phasesEyebrow}</p>
          <h2 id="phases-heading">{t.phasesTitle}</h2>
        </motion.div>
        <ol className="journey">
          {PHASES.map((phase, index) => (
            <motion.li className="journey-card spot" data-phase={index} key={phase.title[1]} variants={item}>
              <div className="journey-head">
                <span className="journey-num">{String(index + 1).padStart(2, '0')}</span>
                <div>
                  <h3>{phase.title[vi ? 0 : 1]}</h3>
                  <p>{phase.description[vi ? 0 : 1]}</p>
                </div>
              </div>
              <ol className="journey-modules">
                {phaseMembers(index).map(member => {
                  const Icon = moduleIcons[member];
                  const node = workflowNodes[member];
                  return (
                    <li key={member} tabIndex={0}>
                      <span className="jm-icon" aria-hidden="true">
                        <Icon size={16} strokeWidth={1.9} />
                      </span>
                      <span className="jm-text">
                        <strong>{nodeTitle(member, language)}</strong>
                        <small>{node.description[vi ? 0 : 1]}</small>
                      </span>
                      <span className="jm-num" aria-hidden="true">
                        {String(member + 1).padStart(2, '0')}
                      </span>
                      <span className="jm-more" role="note">
                        {node.explanation[vi ? 0 : 1]}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </motion.li>
          ))}
        </ol>
      </Panel>

      {/* 5 · What is verifiable + closing call to action (one screen) */}
      <Panel className="proof" label="proof-heading">
        <motion.div className="section-head" variants={item}>
          <h2 id="proof-heading">{t.proofTitle}</h2>
        </motion.div>
        <ul className="proof-list">
          {t.proof.map(([title, body], index) => {
            const Icon = proofIcons[index];
            return (
              <motion.li key={title} className="spot" variants={item}>
                <span className="proof-icon" aria-hidden="true">
                  <Icon size={22} strokeWidth={1.8} />
                </span>
                <h3>{title}</h3>
                <p>{body}</p>
                <button type="button" className="proof-more" onClick={onDemo}>
                  {proofLabels[index]}
                  <ArrowRight size={15} aria-hidden="true" />
                </button>
              </motion.li>
            );
          })}
        </ul>
        <motion.div className="cta-band" variants={item}>
          <h2>{t.ctaTitle}</h2>
          <p>{t.ctaBody}</p>
          <div className="cta-actions">
            <button type="button" className="btn-light" onClick={onDemo}>
              {t.cta}
              <ArrowRight size={18} className="arrow-nudge" aria-hidden="true" />
            </button>
          </div>
        </motion.div>
      </Panel>
    </div>
  );
}
