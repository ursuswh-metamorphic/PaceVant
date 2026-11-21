import {useId} from 'react';

/*
 * Vector glass artwork. Every shape is plain geometry (plates, shields, ticks,
 * ribbons) with layered gradients for a frosted-glass read. Decorative only:
 * every component is aria-hidden.
 */

type Tone = 'idle' | 'running' | 'approved' | 'passed' | 'rejected' | 'failed' | 'unknown';

const toneColor: Record<Tone, [string, string]> = {
  idle: ['#9fb2e6', '#6f86d6'],
  running: ['#7d98ff', '#3d5ce8'],
  approved: ['#7d98ff', '#3d5ce8'],
  passed: ['#5fd3a2', '#12825a'],
  rejected: ['#ff8f99', '#c9333f'],
  failed: ['#ff8f99', '#c9333f'],
  unknown: ['#f8c76f', '#a8620a'],
};

const SHIELD = 'M0 -30 L24 -21 V-2 C24 15 13 26 0 32 C-13 26 -24 15 -24 -2 V-21 Z';

export function AmbientRibbons() {
  const id = useId().replace(/:/g, '');
  return (
    <svg className="ambient-ribbons" viewBox="0 0 1100 760" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}a`} x1="160" y1="80" x2="1020" y2="520" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" stopOpacity="0" />
          <stop offset="0.35" stopColor="#dfe8ff" stopOpacity="0.9" />
          <stop offset="0.7" stopColor="#a9bdfb" stopOpacity="0.75" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0.2" />
        </linearGradient>
        <linearGradient id={`${id}b`} x1="300" y1="0" x2="1100" y2="420" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" stopOpacity="0" />
          <stop offset="0.5" stopColor="#c4d3ff" stopOpacity="0.85" />
          <stop offset="1" stopColor="#7f9cf5" stopOpacity="0.55" />
        </linearGradient>
        <linearGradient id={`${id}c`} x1="420" y1="300" x2="1100" y2="700" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" stopOpacity="0" />
          <stop offset="0.6" stopColor="#d7e2ff" stopOpacity="0.7" />
          <stop offset="1" stopColor="#9fb4f7" stopOpacity="0.4" />
        </linearGradient>
        <linearGradient id={`${id}s`} x1="0" y1="0" x2="1100" y2="0" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" stopOpacity="0" />
          <stop offset="0.55" stopColor="#ffffff" stopOpacity="0.95" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0.2" />
        </linearGradient>
        <filter id={`${id}f`} x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="1.2" />
        </filter>
      </defs>
      <path
        d="M120 210 C 330 120, 470 330, 680 250 S 980 40, 1120 120 L 1120 210 C 980 140, 860 330, 680 360 S 360 260, 120 260 Z"
        fill={`url(#${id}a)`}
      />
      <path
        d="M300 40 C 520 10, 640 170, 820 120 S 1040 -20, 1140 20 L 1140 70 C 1030 40, 950 200, 820 210 S 560 90, 300 70 Z"
        fill={`url(#${id}b)`}
      />
      <path
        d="M440 520 C 620 420, 760 560, 900 470 S 1060 330, 1140 360 L 1140 420 C 1060 400, 1000 560, 880 580 S 640 500, 440 560 Z"
        fill={`url(#${id}c)`}
      />
      <g filter={`url(#${id}f)`} stroke={`url(#${id}s)`} strokeWidth="1.6" strokeLinecap="round">
        <path d="M120 212 C 330 122, 470 332, 680 252 S 980 42, 1120 122" />
        <path d="M300 42 C 520 12, 640 172, 820 122 S 1040 -18, 1140 22" />
        <path d="M440 522 C 620 422, 760 562, 900 472 S 1060 332, 1140 362" />
      </g>
    </svg>
  );
}

/** Stacked frosted plates with a shield — used beside "What is PaceVant". */
export function ShieldStackArt({className}: {className?: string}) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={className} viewBox="0 0 140 120" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}p`} x1="20" y1="40" x2="120" y2="110" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" stopOpacity="0.95" />
          <stop offset="1" stopColor="#c9d6fb" stopOpacity="0.85" />
        </linearGradient>
        <linearGradient id={`${id}s`} x1="50" y1="10" x2="92" y2="78" gradientUnits="userSpaceOnUse">
          <stop stopColor="#f4f7ff" />
          <stop offset="1" stopColor="#9db2f6" />
        </linearGradient>
      </defs>
      {[0, 1, 2].map(i => (
        <path
          key={i}
          d={`M70 ${96 - i * 12} L122 ${74 - i * 12} L70 ${52 - i * 12} L18 ${74 - i * 12} Z`}
          fill={`url(#${id}p)`}
          stroke="#ffffff"
          strokeOpacity="0.9"
          opacity={0.55 + i * 0.2}
        />
      ))}
      <g transform="translate(70 40)">
        <path d={SHIELD} fill={`url(#${id}s)`} stroke="#ffffff" strokeWidth="1.5" />
        <path d={SHIELD} transform="scale(0.62)" fill="none" stroke="#3d5ce8" strokeWidth="3" strokeLinejoin="round" />
      </g>
    </svg>
  );
}

/** A shield on a glowing ring — "why guardrails". */
export function ShieldOrbitArt({className}: {className?: string}) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={className} viewBox="0 0 140 130" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}s`} x1="42" y1="16" x2="104" y2="104" gradientUnits="userSpaceOnUse">
          <stop stopColor="#eef2ff" />
          <stop offset="0.55" stopColor="#aebffa" />
          <stop offset="1" stopColor="#5a77ee" />
        </linearGradient>
        <linearGradient id={`${id}r`} x1="10" y1="0" x2="130" y2="0" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" stopOpacity="0.2" />
          <stop offset="0.5" stopColor="#c6d3ff" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0.2" />
        </linearGradient>
      </defs>
      <ellipse cx="70" cy="98" rx="58" ry="16" stroke={`url(#${id}r)`} strokeWidth="5" />
      <ellipse cx="70" cy="98" rx="40" ry="9" fill="#dfe7ff" opacity="0.6" />
      <g transform="translate(70 58) scale(1.45)">
        <path d={SHIELD} fill={`url(#${id}s)`} stroke="#ffffff" strokeWidth="1.2" />
        <path d="M-10 0 L-3 7 L11 -8" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}

/** Stacked checklist cards — "how verification works". */
export function ChecklistArt({className}: {className?: string}) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={className} viewBox="0 0 140 130" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}c`} x1="20" y1="10" x2="110" y2="120" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" />
          <stop offset="1" stopColor="#d6e0fd" />
        </linearGradient>
        <linearGradient id={`${id}b`} x1="74" y1="64" x2="120" y2="118" gradientUnits="userSpaceOnUse">
          <stop stopColor="#a9bbfb" />
          <stop offset="1" stopColor="#3d5ce8" />
        </linearGradient>
      </defs>
      <rect x="36" y="8" width="78" height="92" rx="12" fill="#e7edff" stroke="#fff" />
      <rect x="22" y="18" width="78" height="96" rx="12" fill={`url(#${id}c)`} stroke="#ffffff" strokeWidth="1.5" />
      {[0, 1, 2].map(i => (
        <g key={i} transform={`translate(34 ${36 + i * 22})`}>
          <rect width="14" height="14" rx="4" fill="#ffffff" stroke="#c5d2f7" />
          <path d="M3.5 7 L6 9.5 L10.5 4.5" stroke="#3d5ce8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <rect x="22" y="4" width="34" height="6" rx="3" fill="#c9d5f8" />
        </g>
      ))}
      <rect x="76" y="68" width="46" height="46" rx="14" fill={`url(#${id}b)`} stroke="#ffffff" strokeWidth="1.5" />
      <path d="M88 91 L96 99 L111 83" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Frosted platform with the network emblem — "executed on Avalanche". */
export function ChainPlatformArt({className}: {className?: string}) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={className} viewBox="0 0 140 130" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}p`} x1="20" y1="60" x2="120" y2="124" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" stopOpacity="0.95" />
          <stop offset="1" stopColor="#ccd8fb" />
        </linearGradient>
        <radialGradient id={`${id}r`} cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(64 34) rotate(60) scale(34)">
          <stop stopColor="#ff8a8a" />
          <stop offset="1" stopColor="#e2343c" />
        </radialGradient>
      </defs>
      {[0, 1, 2].map(i => (
        <path
          key={i}
          d={`M70 ${120 - i * 10} L126 ${96 - i * 10} L70 ${72 - i * 10} L14 ${96 - i * 10} Z`}
          fill={`url(#${id}p)`}
          stroke="#ffffff"
          opacity={0.5 + i * 0.22}
        />
      ))}
      <ellipse cx="70" cy="74" rx="22" ry="7" fill="#ff6b72" opacity="0.18" />
      <circle cx="70" cy="42" r="24" fill={`url(#${id}r)`} stroke="#ffffff" strokeWidth="2" />
      <path d="M70 30 L82 52 H58 Z" fill="#ffffff" />
      <ellipse cx="62" cy="31" rx="9" ry="4" fill="#ffffff" opacity="0.35" transform="rotate(-25 62 31)" />
    </svg>
  );
}

/** Result-panel shield. Colour follows the current verdict tone. */
export function VerdictMark({tone}: {tone: Tone}) {
  const id = useId().replace(/:/g, '');
  const [light, deep] = toneColor[tone];
  const glyph =
    tone === 'passed' || tone === 'approved' ? (
      <path d="M-9 0 L-3 6 L10 -7" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" />
    ) : tone === 'rejected' || tone === 'failed' ? (
      <path d="M-7 -7 L7 7 M7 -7 L-7 7" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" />
    ) : tone === 'unknown' ? (
      <path d="M0 -9 V2 M0 8.5 V9" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" />
    ) : tone === 'running' ? (
      <circle r="7" stroke="#fff" strokeWidth="3" strokeDasharray="30 14" strokeLinecap="round" />
    ) : (
      <circle r="4" fill="#fff" />
    );
  return (
    <svg className="verdict-mark" viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}t`} x1="6" y1="6" x2="58" y2="58" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" />
          <stop offset="1" stopColor="#e7edfb" />
        </linearGradient>
        <linearGradient id={`${id}s`} x1="20" y1="12" x2="44" y2="54" gradientUnits="userSpaceOnUse">
          <stop stopColor={light} />
          <stop offset="1" stopColor={deep} />
        </linearGradient>
      </defs>
      <rect x="4" y="4" width="56" height="56" rx="16" fill={`url(#${id}t)`} stroke="#ffffff" strokeWidth="1.5" />
      <g transform="translate(32 32) scale(0.78)">
        <path d={SHIELD} fill={`url(#${id}s)`} stroke="#ffffff" strokeWidth="1.5" />
        {glyph}
      </g>
    </svg>
  );
}
