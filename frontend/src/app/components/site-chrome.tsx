import {ArrowUpRight, GitBranch, Globe2, Shield} from 'lucide-react';
import type {Language} from '@/lib/i18n';
import {overviewCopy} from '@/lib/overview-copy';
import {Button} from '@/components/ui/button';

export function LanguageSwitcher({language, onChange}: {language: Language; onChange: (language: Language) => void}) {
  return <div className="language-control" role="group" aria-label={language === 'vi' ? 'Chọn ngôn ngữ' : 'Choose language'}>
    <Globe2 className="language-globe" size={15} aria-hidden="true"/>
    <div className="language-options">
      <button type="button" lang="vi" aria-label="Tiếng Việt" aria-pressed={language === 'vi'} onClick={() => onChange('vi')}>VI</button>
      <button type="button" lang="en" aria-label="English" aria-pressed={language === 'en'} onClick={() => onChange('en')}>EN</button>
    </div>
  </div>;
}

export function SiteFooter({language}: {language: Language}) {
  const t = overviewCopy[language];
  return <footer className="site-footer">
    <div className="footer-top">
      <div className="footer-identity">
        <span className="footer-mark"><Shield size={19} strokeWidth={1.8}/></span>
        <div><strong>PaceVant</strong><p>{t.footerDescription}</p><small>{t.footerProject}</small></div>
      </div>
      <div className="footer-links">
        <Button variant="outline" asChild><a href="https://github.com/ursuswh-metamorphic/PaceVant" target="_blank" rel="noreferrer"><GitBranch size={17}/> GitHub <ArrowUpRight size={14}/></a></Button>
      </div>
    </div>
    <div className="footer-bottom"><span>© {new Date().getFullYear()} {t.rights}</span><span>AI Agent Security · Avalanche Fuji</span></div>
  </footer>;
}
