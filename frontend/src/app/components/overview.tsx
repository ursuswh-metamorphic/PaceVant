import {ArrowRight, Bot, LockKeyhole, ShieldCheck} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {overviewCopy} from '@/lib/overview-copy';
import type {Language} from '@/lib/i18n';

export function Overview({language,onDemo}:{language:Language;onDemo:()=>void}) {
  const t=overviewCopy[language],vi=language==='vi';
  return <div className="editorial-overview">
    <section className="editorial-hero" aria-labelledby="overview-headline">
      <div className="editorial-eyebrow"><span className="eyebrow-rule"/>{t.badge}<span className="eyebrow-rule"/></div>
      <h1 id="overview-headline">{t.headline.split('. ')[0]}.<br className="headline-mobile-break"/> {t.headline.split('. ').slice(1).join('. ')}<span>{t.highlight}</span></h1>
      <p className="editorial-intro">{t.description}</p>
      <Button className="editorial-cta" onClick={onDemo} data-testid="launch-demo">{t.cta}<ArrowRight size={18} aria-hidden="true"/></Button>
    </section>

    <section className="architecture-ribbon" aria-label={vi?'Kiến trúc bảo mật rút gọn':'Security architecture overview'}>
      <div className="ribbon-caption"><span>PACEVANT</span><span>{vi?'TỪ Ý ĐỊNH ĐẾN THỰC THI':'FROM INTENT TO EXECUTION'}</span></div>
      <div className="ribbon-flow">
        <div className="ribbon-endpoint"><Bot size={23} strokeWidth={1.6} aria-hidden="true"/><div><span>01 / INPUT</span><h2>AI Agent</h2><p>{vi?'Đề xuất trong phạm vi cho phép':'Propose within authorized scope'}</p></div></div>
        <ArrowRight className="ribbon-arrow" size={20} aria-hidden="true"/>
        <div className="ribbon-engine"><ShieldCheck size={27} strokeWidth={1.6} aria-hidden="true"/><div><span>02 / VERIFICATION</span><h2>Security Engine</h2><p>Shield · ITAG · EVM · Risk · Z3</p></div></div>
        <ArrowRight className="ribbon-arrow" size={20} aria-hidden="true"/>
        <div className="ribbon-endpoint"><LockKeyhole size={23} strokeWidth={1.6} aria-hidden="true"/><div><span>03 / EXECUTION</span><h2>PolicyVault</h2><p>{vi?'Thực thi điều kiện bảo vệ':'Enforce protective conditions'}</p></div></div>
      </div>
    </section>

    <section className="editorial-problem" aria-labelledby="problem-heading">
      <div className="editorial-section-lead"><span className="editorial-index">01 — {vi?'VẤN ĐỀ':'THE CHALLENGE'}</span><h2 id="problem-heading">{t.problemHeading}</h2><p>{t.problemSubtitle}</p></div>
      <div className="editorial-comparison">
        <div className="comparison-row"><span className="comparison-label">{vi?'RỦI RO':'THE RISK'}</span><h3>{t.problemTitle}</h3><p>{t.problemDescription}</p><ul>{t.problems.map((item,i)=><li key={item}><span>0{i+1}</span>{item}</li>)}</ul></div>
        <div className="comparison-row comparison-solution"><span className="comparison-label">{vi?'CÁCH TIẾP CẬN':'OUR APPROACH'}</span><h3>{t.solutionTitle}</h3><p>{t.solutionDescription}</p><ul>{t.solutions.map((item,i)=><li key={item}><span>0{i+1}</span>{item}</li>)}</ul></div>
      </div>
    </section>

    <section className="editorial-method" aria-labelledby="method-heading">
      <div className="editorial-method-heading"><div><span className="editorial-index">02 — {vi?'QUY TRÌNH':'THE METHOD'}</span><h2 id="method-heading">{t.howHeading}</h2></div></div>
      <ol className="editorial-steps">{t.steps.map((step,index)=><li key={step.title}><span className="method-number">0{index+1}</span><h3>{step.title}</h3><p>{step.description}</p>{index<3&&<ArrowRight size={17} aria-hidden="true"/>}</li>)}</ol>
    </section>
  </div>;
}
