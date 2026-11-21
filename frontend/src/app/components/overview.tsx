import {motion, useReducedMotion} from 'motion/react';
import {
  ArrowRight,
  BarChart3,
  BadgeCheck,
  ChevronRight,
  FileSearch,
  Layers,
  Link2,
  PlayCircle,
  Settings2,
  ShieldCheck,
  Sparkles,
  Workflow,
  Zap,
  ArrowLeftRight,
  Banknote,
} from 'lucide-react';
import {overviewCopy} from '@/lib/overview-copy';
import {workflowNodes} from '@/lib/workflow-nodes';
import {PHASES, phaseMembers} from '@/lib/phases';
import type {Language} from '@/lib/i18n';
import {ChainPlatformArt, ChecklistArt, ShieldOrbitArt, ShieldStackArt} from './illustrations';

const EASE = [0.16, 1, 0.3, 1] as const;

export function Overview({
  language,
  onDemo,
  onEvidence,
}: {
  language: Language;
  onDemo: () => void;
  onEvidence: () => void;
}) {
  const t = overviewCopy[language];
  const vi = language === 'vi';
  const reduced = useReducedMotion();
  const storyArt = [ShieldOrbitArt, ChecklistArt, ChainPlatformArt];
  const featureIcons = [ShieldCheck, Layers, Link2, Zap];
  const proofIcons = [Banknote, ArrowLeftRight, FileSearch];

  // The single authored moment on this page: the preview pipeline lights up once, left to right.
  const tile = (step: number) =>
    reduced
      ? {}
      : {
          initial: {opacity: 0, y: 8},
          animate: {opacity: 1, y: 0},
          transition: {duration: 0.42, delay: 0.25 + step * 0.16, ease: EASE},
        };

  return (
    <div className="overview">
      <section className="hero" aria-labelledby="overview-headline">
        <div className="hero-copy">
          <p className="hero-tagline">{t.tagline}</p>
          <h1 id="overview-headline">
            {t.headline[0]} <span className="hl">{t.headline[1]}</span> {t.headline[2]}{' '}
            <span className="hl">{t.headline[3]}</span> {t.headline[4]}
          </h1>
          <p className="hero-lede">{t.description}</p>
          <div className="hero-actions">
            <button type="button" className="btn-primary" onClick={onDemo} data-testid="launch-demo">
              {t.cta}
              <ArrowRight size={18} className="arrow-nudge" aria-hidden="true" />
            </button>
            <a className="btn-glass glass" href="#how-it-works">
              <PlayCircle size={18} aria-hidden="true" style={{position: 'relative', zIndex: 2}} />
              <span style={{position: 'relative', zIndex: 2}}>{t.secondary}</span>
            </a>
          </div>
          <p className="hero-helper">{t.helper}</p>
        </div>

        <figure className="preview-window glass" style={{margin: 0}} aria-label={t.preview.window}>
          <div className="preview-frame">
            <div className="preview-rail" aria-hidden="true">
              <span><Layers size={16} /></span>
              <span><BarChart3 size={16} /></span>
              <span><ShieldCheck size={16} /></span>
              <span><Settings2 size={16} /></span>
            </div>
            <div>
              <div className="preview-top">
                <ShieldCheck size={17} aria-hidden="true" />
                PaceVant
              </div>
              <div className="preview-body">
                <div className="preview-heading">
                  <span>
                    <Workflow size={14} aria-hidden="true" style={{color: 'var(--accent)'}} />
                    {t.preview.window}
                  </span>
                  <span className="chip tone-idle">{t.preview.badge}</span>
                </div>
                <div className="preview-flow">
                  <motion.div className="preview-tile" {...tile(0)}>
                    <Sparkles size={22} aria-hidden="true" />
                    <span>
                      <strong>{t.preview.agent[0]}</strong>
                      <br />
                      <small>{t.preview.agent[1]}</small>
                    </span>
                  </motion.div>
                  <span className="preview-connector" aria-hidden="true">
                    <ChevronRight size={16} />
                  </span>
                  <motion.div className="preview-tile" data-core="true" {...tile(1)}>
                    <ShieldCheck size={22} aria-hidden="true" />
                    <span>
                      <strong>{t.preview.core[0]}</strong>
                      <br />
                      <small>{t.preview.core[1]}</small>
                    </span>
                  </motion.div>
                  <span className="preview-connector" aria-hidden="true">
                    <ChevronRight size={16} />
                  </span>
                  <motion.div className="preview-tile" {...tile(2)}>
                    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                      <circle cx="12" cy="12" r="11" fill="#e8414a" />
                      <path d="M12 6.5 L17.5 16 H6.5 Z" fill="#fff" />
                    </svg>
                    <span>
                      <strong>{t.preview.chain[0]}</strong>
                      <br />
                      <small>{t.preview.chain[1]}</small>
                    </span>
                  </motion.div>
                </div>
                <dl className="preview-facts">
                  {t.preview.facts.map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <figcaption className="preview-caption">{t.preview.caption}</figcaption>
            </div>
          </div>
        </figure>
      </section>

      <section className="about-strip glass" aria-labelledby="about-heading">
        <ShieldStackArt className="about-art" />
        <div>
          <h2 id="about-heading">{t.aboutTitle}</h2>
          <p>{t.aboutBody}</p>
        </div>
        <ul className="about-features">
          {t.features.map(([title, body], index) => {
            const Icon = featureIcons[index];
            return (
              <li key={title}>
                <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
                <strong>{title}</strong>
                <span>{body}</span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="story-grid" aria-label={vi ? 'Câu chuyện sản phẩm' : 'Product story'}>
        {t.story.map((item, index) => {
          const Art = storyArt[index];
          return (
            <article className="story-card" key={item.title}>
              <div>
                <span className="story-step" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </div>
              <Art className="story-art" />
            </article>
          );
        })}
      </section>

      <section className="phases-section" id="how-it-works" aria-labelledby="phases-heading">
        <div className="section-title">
          <h2 id="phases-heading">{t.phasesTitle}</h2>
          <p>{t.phasesBody}</p>
        </div>
        <ol className="phase-stack">
          {PHASES.map((phase, index) => (
            <li className="phase-line" key={phase.title[1]}>
              <div className="phase-line-head">
                <span className="phase-index">{String(index + 1).padStart(2, '0')}</span>
                <strong>{phase.title[vi ? 0 : 1]}</strong>
              </div>
              <div className="phase-modules">
                {phaseMembers(index).map((member, position) => (
                  <span key={member} style={{display: 'contents'}}>
                    {position > 0 && <ChevronRight size={14} aria-hidden="true" />}
                    <span>{workflowNodes[member].label}</span>
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="proof-heading">
        <div className="section-title" style={{marginBottom: 8}}>
          <h2 id="proof-heading">{t.proofTitle}</h2>
        </div>
        <div className="demo-proof">
          {t.proof.map(([title, body], index) => {
            const Icon = proofIcons[index];
            return (
              <div className="proof-item" key={title}>
                <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="cta-band glass" aria-labelledby="cta-heading">
        <div>
          <h2 id="cta-heading">{t.ctaTitle}</h2>
          <p>{t.ctaBody}</p>
        </div>
        <div className="cta-actions">
          <button type="button" className="btn-primary" onClick={onDemo}>
            {t.cta}
            <ArrowRight size={18} className="arrow-nudge" aria-hidden="true" />
          </button>
          <button type="button" className="btn-glass" style={{background: 'rgba(255,255,255,.75)', boxShadow: 'inset 0 0 0 1px var(--line), var(--shadow-1)'}} onClick={onEvidence}>
            <BadgeCheck size={17} aria-hidden="true" />
            {t.ctaSecondary}
          </button>
        </div>
      </section>
    </div>
  );
}
