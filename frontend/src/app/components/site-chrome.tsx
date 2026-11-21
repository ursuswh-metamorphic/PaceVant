import {ArrowUpRight, GitBranch, Globe2, ShieldCheck} from 'lucide-react';
import type {Language} from '@/lib/i18n';
import {overviewCopy} from '@/lib/overview-copy';

export function LanguageSwitcher({
  language,
  onChange,
}: {
  language: Language;
  onChange: (language: Language) => void;
}) {
  return (
    <div
      className="language-control"
      role="group"
      aria-label={language === 'vi' ? 'Chọn ngôn ngữ' : 'Choose language'}
    >
      <Globe2 className="language-globe" size={14} aria-hidden="true" />
      <div className="language-options">
        <button
          type="button"
          lang="vi"
          aria-label="Tiếng Việt"
          aria-pressed={language === 'vi'}
          onClick={() => onChange('vi')}
        >
          VI
        </button>
        <button
          type="button"
          lang="en"
          aria-label="English"
          aria-pressed={language === 'en'}
          onClick={() => onChange('en')}
        >
          EN
        </button>
      </div>
    </div>
  );
}

export function SiteFooter({language}: {language: Language}) {
  const t = overviewCopy[language];
  return (
    <footer className="site-footer">
      <div className="footer-row">
        <span className="footer-brand">
          <ShieldCheck size={20} strokeWidth={2.1} aria-hidden="true" />
          PaceVant
        </span>
        <div className="footer-copy">
          <p>{t.footerDescription}</p>
          <small>
            {t.footerProject} · © {new Date().getFullYear()} {t.rights}
          </small>
        </div>
        <div className="footer-links">
          <a className="github-pill" href="https://github.com/ursuswh-metamorphic/PaceVant" target="_blank" rel="noreferrer">
            <GitBranch size={15} aria-hidden="true" />
            GitHub
            <ArrowUpRight size={13} aria-hidden="true" />
          </a>
        </div>
      </div>
    </footer>
  );
}
