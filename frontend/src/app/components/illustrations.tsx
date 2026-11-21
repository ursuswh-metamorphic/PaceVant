import {useId} from 'react';

/*
 * Vector artwork. Plain geometry with layered gradients; decorative only, so
 * every component is aria-hidden and carries no information that is not also
 * present as real text on the page.
 */

type Tone = 'idle' | 'running' | 'approved' | 'passed' | 'rejected' | 'failed' | 'unknown';

const toneColor: Record<Tone, [string, string]> = {
  idle: ['#a9b9e6', '#6f84c8'],
  running: ['#5fb5fd', '#0a5cf0'],
  approved: ['#5fb5fd', '#0a5cf0'],
  passed: ['#46c19c', '#087a66'],
  rejected: ['#f2838f', '#c0263a'],
  failed: ['#f2838f', '#c0263a'],
  unknown: ['#f3c467', '#8f5507'],
};

const SHIELD = 'M0 -30 L24 -21 V-2 C24 15 13 26 0 32 C-13 26 -24 15 -24 -2 V-21 Z';

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
          <stop offset="1" stopColor="#e8eefc" />
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

/*
 * Isometric stack: AI Agent → PaceVant → PolicyVault → Avalanche.
 * Each plate is a 2:1 isometric slab (top face + two side faces). Icons are
 * drawn in plate space through the isometric matrix so they lie flat on the
 * top face. Hovering the figure gently separates the layers (CSS, motion-safe).
 */
const ISO = 'matrix(0.7071 0.3536 -0.7071 0.3536 0 0)';
const W = 224; // diamond width
const H = W / 2; // diamond height
const T = 12; // slab thickness

type Plate = {top: [string, string]; side: [string, string]; rim: string; label: string; sub: string; accent?: boolean};

export function LayerStackArt({labels}: {labels: [string, string][]}) {
  const id = useId().replace(/:/g, '');
  const plates: Plate[] = [
    {top: ['#ffffff', '#eef3ff'], side: ['#dfe7fb', '#c9d5f5'], rim: '#ffffff', label: labels[0][0], sub: labels[0][1]},
    {top: ['#5fb5fd', '#0a5cf0'], side: ['#2449c4', '#1a37a3'], rim: '#a9bcff', label: labels[1][0], sub: labels[1][1], accent: true},
    {top: ['#f6f3ff', '#e4dcff'], side: ['#d6cbfb', '#bfb0f2'], rim: '#ffffff', label: labels[2][0], sub: labels[2][1]},
    {top: ['#fff6f6', '#fde3e3'], side: ['#f6cdcd', '#ebb3b3'], rim: '#ffffff', label: labels[3][0], sub: labels[3][1]},
  ];
  const cx = 150;
  const gap = 100;
  const y0 = 70;
  const labelX = 330;

  const face = (cy: number) => `${cx},${cy - H / 2} ${cx + W / 2},${cy} ${cx},${cy + H / 2} ${cx - W / 2},${cy}`;
  const left = (cy: number) => `${cx - W / 2},${cy} ${cx},${cy + H / 2} ${cx},${cy + H / 2 + T} ${cx - W / 2},${cy + T}`;
  const right = (cy: number) => `${cx},${cy + H / 2} ${cx + W / 2},${cy} ${cx + W / 2},${cy + T} ${cx},${cy + H / 2 + T}`;

  return (
    <svg className="layer-stack-art" viewBox="0 0 520 450" fill="none" aria-hidden="true">
      <defs>
        {plates.map((plate, i) => (
          <g key={i}>
            <linearGradient id={`${id}t${i}`} x1={cx - W / 2} y1="0" x2={cx + W / 2} y2="0" gradientUnits="userSpaceOnUse">
              <stop stopColor={plate.top[0]} />
              <stop offset="1" stopColor={plate.top[1]} />
            </linearGradient>
            <linearGradient id={`${id}s${i}`} x1="0" y1="0" x2="1" y2="0">
              <stop stopColor={plate.side[0]} />
              <stop offset="1" stopColor={plate.side[1]} />
            </linearGradient>
          </g>
        ))}
        <radialGradient id={`${id}glow`} cx="0.5" cy="0.5" r="0.5">
          <stop stopColor="#2f8bff" stopOpacity="0.45" />
          <stop offset="1" stopColor="#2f8bff" stopOpacity="0" />
        </radialGradient>
      </defs>

      <ellipse cx={cx} cy={y0 + 3 * gap + 30} rx="170" ry="64" fill={`url(#${id}glow)`} opacity="0.55" />

      {/* Bottom plate first so upper plates overlap it */}
      {plates
        .map((plate, i) => ({plate, i}))
        .reverse()
        .map(({plate, i}) => {
          const cy = y0 + i * gap;
          return (
            <g key={i} className={`ls-layer ls-layer-${i}`}>
              <polygon points={left(cy)} fill={`url(#${id}s${i})`} />
              <polygon points={right(cy)} fill={`url(#${id}s${i})`} opacity="0.82" />
              <polygon points={face(cy)} fill={`url(#${id}t${i})`} stroke={plate.rim} strokeWidth="1.2" />
              <g transform={`translate(${cx} ${cy}) ${ISO}`}>{plateGlyph(i)}</g>
              {/* Leader line + label pill */}
              <path d={`M${cx + W / 2 - 4} ${cy} H${labelX - 10}`} stroke="#b8c6e6" strokeWidth="1" strokeDasharray="3 4" />
              <circle cx={labelX - 10} cy={cy} r="3" fill={plate.accent ? '#0a5cf0' : '#8fa1bf'} />
              <g transform={`translate(${labelX} ${cy - 21})`}>
                <rect width="176" height="42" rx="21" fill="#ffffff" stroke={plate.accent ? '#b9d5ff' : '#dde6f3'} />
                <text x="18" y="18" fontSize="13" fontWeight="600" fill="#0b1f45">
                  {plate.label}
                </text>
                <text x="18" y="33" fontSize="11" fill="#4d6082">
                  {plate.sub}
                </text>
              </g>
            </g>
          );
        })}
    </svg>
  );
}

function plateGlyph(i: number) {
  // Drawn in plate space (pre-isometric), centred on 0,0.
  if (i === 0)
    return (
      <g fill="#0a5cf0">
        <path d="M-6 -30 C-3 -12 2 -7 20 -4 C2 -1 -3 4 -6 22 C-9 4 -14 -1 -32 -4 C-14 -7 -9 -12 -6 -30 Z" />
        <path d="M20 8 C21.5 15 24 17.5 31 19 C24 20.5 21.5 23 20 30 C18.5 23 16 20.5 9 19 C16 17.5 18.5 15 20 8 Z" fill="#6b4ee6" />
      </g>
    );
  if (i === 1)
    return (
      <g>
        <path d="M0 -34 L28 -24 V-2 C28 18 15 30 0 37 C-15 30 -28 18 -28 -2 V-24 Z" fill="#ffffff" />
        <path d="M-11 0 L-3 8 L13 -9" stroke="#0a5cf0" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    );
  if (i === 2)
    return (
      <g stroke="#6b4ee6" strokeWidth="5" strokeLinejoin="round">
        <rect x="-28" y="-22" width="56" height="44" rx="8" fill="#ffffff" />
        <circle cx="0" cy="0" r="10" fill="#eee9ff" />
        <path d="M0 -4 V4" strokeLinecap="round" />
      </g>
    );
  return (
    <g>
      <circle r="30" fill="#e84142" />
      <path d="M-2 -16 L-16 12 H-4 L-2 8 Z M5 -2 L-3 12 H15 Z" fill="#ffffff" />
    </g>
  );
}
