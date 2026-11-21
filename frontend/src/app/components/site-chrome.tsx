import type {CSSProperties} from 'react';
import {ArrowRight, ArrowUpRight, BookOpen, GitBranch, Globe2} from 'lucide-react';
import {TabsList, TabsTrigger} from '@/components/ui/tabs';
import type {Language} from '@/lib/i18n';
import {overviewCopy} from '@/lib/overview-copy';
import markUrl from '@/assets/pacevant-mark.png';

const REPO = 'https://github.com/ursuswh-metamorphic/PaceVant';

/** PaceVant mark cut from the brand board (transparent PNG, 241×192). */
export function BrandMark({size = 30}: {size?: number}) {
  return <img className="brand-logo" src={markUrl} alt="" width={Math.round((size * 241) / 192)} height={size} decoding="async" />;
}

export type BackendState = 'pending' | 'ready' | 'limited' | 'offline';

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

/** Avalanche mark, drawn inline so no external asset is fetched. */
function AvaxMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="11" fill="#e84142" />
      <path d="M11 6.2 L5.6 15.8 H9.2 L11 12.6 Z M13.6 10.6 L10.6 15.8 H16.6 Z" fill="#fff" />
    </svg>
  );
}

const backendCopy: Record<BackendState, [string, string]> = {
  pending: ['Đang kiểm tra kết nối backend', 'Checking backend connection'],
  ready: ['Backend sẵn sàng chạy giao dịch', 'Backend ready to run transactions'],
  limited: ['Backend đang ở chế độ giới hạn: chạy trực tiếp chưa được cấu hình', 'Backend in limited mode: live runs are not configured'],
  offline: ['Không kết nối được backend', 'Backend unreachable'],
};

/** Floating Liquid Glass navigation. Must render inside the Radix <Tabs> root. */
export function SiteHeader({
  tab,
  tabs,
  language,
  onLanguage,
  runActive,
  runLabel,
  backend,
  onDemo,
}: {
  tab: string;
  tabs: {value: string; label: string; testId?: string}[];
  language: Language;
  onLanguage: (language: Language) => void;
  runActive: boolean;
  runLabel: string;
  backend: BackendState;
  onDemo: () => void;
}) {
  const vi = language === 'vi';
  const index = Math.max(0, tabs.findIndex(item => item.value === tab));
  const status = backendCopy[backend][vi ? 0 : 1];

  return (
    <header className="site-header">
      <div className="header-inner glass">
        <a href="/" className="brand chrome-layer" aria-label="PaceVant">
          <BrandMark />
          <span className="brand-name-full">PaceVant</span>
        </a>

        {/* Equal-width tabs + one indicator that only slides horizontally (never re-measured on scroll). */}
        <TabsList
          className="main-nav chrome-layer"
          aria-label={vi ? 'Điều hướng chính' : 'Main navigation'}
          style={{'--i': index, '--tab-count': tabs.length} as CSSProperties}
        >
          <span className="nav-pill" aria-hidden="true" />
          {tabs.map(item => (
            <TabsTrigger key={item.value} value={item.value} data-testid={item.testId}>
              {item.label}
              {item.value === 'live' && runActive && <span className="nav-run-dot" aria-label={runLabel} />}
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="header-status chrome-layer">
          <span className="net-chip" data-state={backend} title={status}>
            <AvaxMark />
            <span className="net-label">Avalanche Fuji</span>
            <span className="net-dot" aria-hidden="true" />
            <span className="sr-only">{status}</span>
          </span>
          <a className="docs-link" href={`${REPO}#readme`} target="_blank" rel="noreferrer">
            <BookOpen size={15} aria-hidden="true" />
            {vi ? 'Tài liệu' : 'Docs'}
            <ArrowUpRight size={13} aria-hidden="true" />
          </a>
          <LanguageSwitcher language={language} onChange={onLanguage} />
          {/* Always mounted: off the Overview it collapses (width + fade) so the items
              beside it glide over instead of jumping. */}
          <button
            type="button"
            className="btn-primary header-cta"
            data-collapsed={tab !== 'overview'}
            aria-hidden={tab !== 'overview'}
            tabIndex={tab === 'overview' ? 0 : -1}
            onClick={onDemo}
          >
            <span className="header-cta-label">{vi ? 'Bắt đầu Demo' : 'Start Demo'}</span>
            <ArrowRight size={15} className="arrow-nudge" aria-hidden="true" />
          </button>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter({language}: {language: Language}) {
  const t = overviewCopy[language];
  return (
    <footer className="site-footer">
      <div className="footer-row">
        <span className="footer-brand">
          <BrandMark size={26} />
          PaceVant
        </span>
        <div className="footer-copy">
          <p>{t.footerDescription}</p>
          <small>
            {t.footerProject} · © {new Date().getFullYear()} {t.rights}
          </small>
        </div>
        <div className="footer-links">
          <a className="github-pill" href={REPO} target="_blank" rel="noreferrer">
            <GitBranch size={15} aria-hidden="true" />
            GitHub
            <ArrowUpRight size={13} aria-hidden="true" />
          </a>
        </div>
      </div>
    </footer>
  );
}
