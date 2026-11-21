# PaceVant — Luminous Editorial Fintech

Supersedes "Liquid Glass Security Workbench". One token set (`frontend/src/app/styles.css`, `:root`) drives Overview, Live Demo and Evidence. Light only; no dark theme.

## Intent
Bright, premium and calm, with one strong visual moment. Editorial typography and a real product showcase come before decoration. Never invent execution, customers or statistics: the Overview showcase replays the recorded runs in `fixtures/judge` (Fuji fork, `public_chain_broadcast: false`) and says so.

## Typography (tested, not assumed)
- Display: **Plus Jakarta Sans Variable** (h1–h3, numerals in the facts strip), weight 700–780, tracking −0.03 to −0.042em.
- Text/UI: **Be Vietnam Pro** 400/500/600/700 (static, so CSS weights are 500/600/700 only).
- Data: **Geist Mono Variable** (hashes, addresses, step numbers, durations).
- All candidates (Plus Jakarta, Be Vietnam Pro, Geist, Space Grotesk, Inter, Geist Mono) passed 146/146 Vietnamese glyphs, upper and lower case, by fallback-width measurement. Geist read as template-generic and Space Grotesk as crypto-generic, so both were rejected.
- Plus Jakarta's stacked capital marks reach 1.22em, so multi-line headings keep line-height ≥ 1.1 and the hero breaks after its first sentence.

## Brand
- Logo: the PaceVant mark cut from `docs/PaceVant_Brand_Identity_Board.png`. The background was flood-filled from the crop border, so the enclosed white node rings stay opaque, and anti-aliased edges were un-mixed against the board background.
  - Assets: `frontend/src/app/assets/pacevant-mark.png` (241×192, transparent), `frontend/public/favicon.png` and `apple-touch-icon.png` (the app-icon tile).
  - Used in the header, footer and showcase title bar. The wordmark is set in Plus Jakarta Sans.

## Palette (sampled from the brand board)
- Ground `#F5F9FF`, surface `#FFFFFF`, wells `#F2F7FF`, tints azure `#E7F1FF`, lilac `#EEE9FF`, mint `#E2F5EF`. Rules `#DDE6F3` / `#C7D5EA`.
- Ink navy `#0B1F45` (the logo wordmark), `#33476B`, `#4D6082` (smallest text step). `#8FA1BF` is for icons and disabled controls only.
- Brand azure `#0A5CF0` (hover `#0048D4`, text links `#0047C2`, soft `#E7F1FF`). Gradients run deep blue `#003CB4` → azure `#0A5CF0`, with sky `#5FB5FD` / aqua highlights, never under small white text.
- States: ok `#06705D` (graph "lit" green `#0EA47E` for edges and icons), warn `#8F5507`, bad `#C0263A`.
- Phase colours: Preparation azure · Verification violet `#6B4EE6` · Execution teal.

## Surfaces
- Ground: a fixed "clear water" aurora (azure, sky and aqua radial light over #F1F7FF → #F7FBFF → #EEF8FF) that stays behind content while scrolling, so every translucent surface always has colour behind it.
- Cards and panels are liquid glass (`--glass-card`: a white 64% → 36% diagonal gradient, blur 24px saturate 200%, bright top rim, soft azure shadow) rather than opaque white. They fall back to opaque white under `prefers-reduced-transparency`.
- One saturated surface: the showcase stage (azure → deep blue with sky/aqua corner highlights and a faint grid), echoed once by the CTA band. White text sits only over the deep part of these gradients.
- Glass (`.glass`, blur 22px saturate 185%) is used only for the floating nav, the showcase window and the showcase tabs. It has opaque fallbacks for missing `backdrop-filter` support and for `prefers-reduced-transparency`.
- Data (graph nodes, tables, evidence) sits on opaque white.

## Layout
- **Overview**, top to bottom:
  1. Centered hero: eyebrow chip, two-tone headline, lede, CTAs.
  2. Showcase: tabs (payment / swap / unsupported route) above a miniature Live Demo. It tours the three recordings continuously, holding 2s after each finishes. The tour pauses on hover, off screen, via the pause button in the window title bar (WCAG 2.2.2), and under reduced motion.
  3. Facts strip.
  4. Core technology: isometric layer stack, four layers.
  5. Three-phase journey listing all 12 modules.
  6. Verifiable-on-Fuji list.
  7. CTA band, then footer.

  Section heads are centered. Sections are spaced 112–168px apart and rise in once as they scroll into view.
- **Live Demo:**
  - A run panel in reading order: ① scenario cards with their terms (the selected card is a deep brand-gradient block), ② optional attack simulation, ③ run.
  - Below it, the workbench: graph (fluid) | result panel (340px). It becomes one column below 1180px.
  - Phase frames are light (7% tint, 1px border) so modules lead; rows are 42px apart. Edges are 2–2.75px with 18px arrowheads.
  - When evidence arrives, a module lights up: green border, glow and a one-off pulse; its outgoing edge turns green with a soft glow. The running hop is azure.
  - Scroll-wheel zoom is active while the pointer is over the graph, and the page does not scroll meanwhile. Fit restores 1:1.
  - Fixed widths and reserved heights keep the frame still across VI/EN, attack selection and scenario changes. This is measured with Playwright, at most 1px of sub-pixel rounding.
  - The result verdict becomes a solid cobalt / teal / red / amber card once a run starts.
  - The graph keeps three phase rows computed from the measured width at zoom 1. Edge ids are unchanged. Row-to-row edges route along the left gutter. Narrow nodes clamp the subtitle to one line via a container query.
- **Evidence:** filterable run table and read-only `/judge/source` panel.
- **Header:** brand · tabs · Fuji network chip · Docs · VI/EN · CTA (Overview only). The network chip's dot reflects `/judge/config` only (ready / limited / offline). Tabs have equal fixed widths and every header slot has a fixed width, so VI/EN and page changes never move it. A single CSS indicator slides only horizontally, and a new page always opens at its top. The header moves to two rows below 1000px.

## Screen-by-screen and smoothness (latest)
- **Overview:** five panels, each one screen tall (`min-height: 100svh − header`):
  1. Hero only, with a scroll cue.
  2. Showcase.
  3. Core technology + facts.
  4. Three phases.
  5. Proof + CTA.

  The hero type scales with height (`min(vw, vh)`). Measured at 1440×900 and 1920×1080: every panel is within 4px of one screen. On 768/720-tall screens the showcase and core panels run 70–120px over.

  Evidence buttons were removed from the Overview; every action leads to the Live Demo.
- **Reveals:** trigger when a panel's top is 8% inside the viewport, 0.45s, opacity/translate only (no blur).
- **Hover reveals never reflow:**
  - Layer cards cross-fade between description and module chips in one grid cell.
  - Module explanations float as a tooltip above the row.
  - Proof actions have reserved space.

  Verified: no movement of following content.
- **Live Demo fits one screen on desktop:**
  - No page heading; a slim run bar.
  - The graph measures the space left in the viewport, lays out wider and scales uniformly (0.75× at 1280×720 → 1.25× at 1920×1080). Wheel zoom and Fit work relative to that fitted zoom.
  - Nodes are 92px with a corner state badge (glyph + colour; full state in aria-label).
  - The result column (run session + verdict) never sets the row height: it scrolls inside, with actions pinned at its bottom.
  - The phase-row colour bars and the canvas helper line were removed.
- **Page switches:**
  - The next page mounts immediately and fades in (no blank frame).
  - `scrollbar-gutter: stable`.
  - The header CTA collapses (width + fade) instead of unmounting.
  - Header state updates before the page body, which renders as a React transition; the Overview showcase stops its timer the moment you leave, so that render is never interrupted.
  - The graph bundle is preloaded when idle.
- **Performance:** backdrop blur is kept only on the floating header and small chips. Large surfaces use translucent gradients and rims, since blur is invisible over the static aurora but expensive. The aurora sits on its own compositor layer.

## Motion & interaction
- Overview: the hero arrives in sequence. Each section fades and rises in as it scrolls into view, then its cards follow one by one (blur → sharp).
- Hover reveals, each also opened by keyboard focus:
  - Core layers show the modules that implement them.
  - Journey modules expand their real explanation.
  - Proof cards surface a direct action.
  - Showcase modules show a description tooltip.
- On touch screens these reveals are shown outright.
- Glass cards carry a pointer-following light.

Durations are 180–420ms, `cubic-bezier(.16,1,.3,1)`. The authored moments are the showcase replay (starts when the showcase scrolls into view, 280ms per module), the nav pill and the layer-stack hover separation. Everything respects `prefers-reduced-motion`; the replay jumps straight to the recorded outcome.

## Verification
- Rendered-pixel WCAG 2.2 AA audit: text line boxes are measured against a text-free screenshot of what is actually behind them, glass included. Result: 0 failures across Overview, Live Demo and Evidence at 1440 and 390, in VI and EN, after the brand-azure retone. The lowest values are the large gradient headings (≥ 3.77:1, need 3:1). Text that is invisible until hover is excluded until it is revealed.
- Playwright at 1920, 1440, 1280, 768 and 390: no horizontal overflow, no console errors.
