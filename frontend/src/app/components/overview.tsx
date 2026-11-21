import {ArrowRight, Bot, LockKeyhole, ShieldCheck, CheckCircle2, ShieldAlert, Cpu} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {overviewCopy} from '@/lib/overview-copy';
import type {Language} from '@/lib/i18n';

export function Overview({language, onDemo}: {language: Language; onDemo: () => void}) {
  const t = overviewCopy[language];
  const vi = language === 'vi';

  return (
    <div className="editorial-overview">
      {/* Hero Section */}
      <section className="editorial-hero" aria-labelledby="overview-headline">
        <div className="editorial-eyebrow">
          <span className="eyebrow-rule" />
          {t.badge}
          <span className="eyebrow-rule" />
        </div>

        <h1 id="overview-headline">
          {t.headline.split('. ')[0]}.
          <br className="headline-mobile-break" /> {t.headline.split('. ').slice(1).join('. ')}
          <span>{t.highlight}</span>
        </h1>

        <p className="editorial-intro">{t.description}</p>

        <div>
          <Button className="editorial-cta" onClick={onDemo} data-testid="launch-demo">
            {t.cta}
            <ArrowRight size={18} aria-hidden="true" />
          </Button>
          <p className="editorial-helper">{t.helper}</p>
        </div>
      </section>

      {/* Architecture Ribbon / Interactive Product Visual */}
      <section
        className="architecture-ribbon"
        aria-label={vi ? 'Kiến trúc bảo mật rút gọn' : 'Security architecture overview'}
      >
        <div className="ribbon-caption">
          <span>PACEVANT SECURE TRANSACTION RUNTIME</span>
          <span>{vi ? 'TỪ Ý ĐỊNH ĐẾN THỰC THI ON-CHAIN' : 'FROM INTENT TO ON-CHAIN EXECUTION'}</span>
        </div>
        <div className="ribbon-flow">
          <div className="ribbon-endpoint">
            <Bot size={28} strokeWidth={1.8} aria-hidden="true" />
            <div>
              <span>01 / PREPARATION</span>
              <h2>AI Agent Proposal</h2>
              <p>{vi ? 'Đề xuất intent trong phạm vi Owner cho phép' : 'Propose intent within owner-authorized scope'}</p>
            </div>
          </div>

          <ArrowRight className="ribbon-arrow" size={22} aria-hidden="true" />

          <div className="ribbon-engine">
            <ShieldCheck size={32} strokeWidth={1.8} aria-hidden="true" />
            <div>
              <span>02 / VERIFICATION (12 SECURITY GATES)</span>
              <h2>PaceVant Security Engine</h2>
              <p>Shield · ITAG · EVM Simulation · Economic Risk · Z3 Formal Proof</p>
            </div>
          </div>

          <ArrowRight className="ribbon-arrow" size={22} aria-hidden="true" />

          <div className="ribbon-endpoint">
            <LockKeyhole size={28} strokeWidth={1.8} aria-hidden="true" />
            <div>
              <span>03 / EXECUTION</span>
              <h2>PolicyVault on Fuji</h2>
              <p>{vi ? 'Ký EIP-712 và thực thi atomic trên blockchain' : 'Sign EIP-712 and enforce atomically on-chain'}</p>
            </div>
          </div>
        </div>
      </section>

      {/* Problem vs Solution Comparison */}
      <section className="editorial-problem" aria-labelledby="problem-heading">
        <div className="editorial-section-lead">
          <span className="editorial-index">01 — {vi ? 'VẤN ĐỀ CẦN GIẢI QUY' : 'THE CORE CHALLENGE'}</span>
          <h2 id="problem-heading">{t.problemHeading}</h2>
          <p>{t.problemSubtitle}</p>
        </div>

        <div className="editorial-comparison">
          <div className="comparison-row">
            <span className="comparison-label">{vi ? 'RỦI RO TỰ ĐỘNG HÓA' : 'AUTONOMOUS RISK'}</span>
            <h3>{t.problemTitle}</h3>
            <p>{t.problemDescription}</p>
            <ul>
              {t.problems.map((item, i) => (
                <li key={item}>
                  <span>0{i + 1}</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="comparison-row comparison-solution">
            <span className="comparison-label">{vi ? 'CƠ CHẾ BẢO VỆ CỦA PACEVANT' : 'PACEVANT APPROACH'}</span>
            <h3>{t.solutionTitle}</h3>
            <p>{t.solutionDescription}</p>
            <ul>
              {t.solutions.map((item, i) => (
                <li key={item}>
                  <span>0{i + 1}</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* 4-Step Process Flow */}
      <section className="editorial-method" aria-labelledby="method-heading">
        <div className="editorial-method-heading">
          <span className="editorial-index">02 — {vi ? 'QUY TRÌNH BẢO MẬT' : 'THE VERIFICATION PROCESS'}</span>
          <h2 id="method-heading">{t.howHeading}</h2>
          <p className="mt-2 text-slate-500 text-sm max-w-xl">{t.howSubtitle}</p>
        </div>

        <ol className="editorial-steps">
          {t.steps.map((step, index) => (
            <li key={step.title}>
              <span className="method-number">STEP 0{index + 1}</span>
              <h3>{step.title}</h3>
              <p>{step.description}</p>
            </li>
          ))}
        </ol>

        <div className="text-center mt-12">
          <Button className="editorial-cta" onClick={onDemo}>
            {t.cta}
            <ArrowRight size={18} aria-hidden="true" />
          </Button>
          <p className="editorial-helper">{t.note}</p>
        </div>
      </section>
    </div>
  );
}
