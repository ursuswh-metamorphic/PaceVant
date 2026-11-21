# PaceVant — Liquid Glass Security Workbench

Supersedes the earlier "Security Editorial" pass. One token set (`frontend/src/app/styles.css`, `:root`) drives Overview, Live Demo and Evidence.

## Intent
Calm, precise, trustworthy. Apple-style Liquid Glass is reserved for chrome; technical data sits on clean, near-opaque surfaces. Never invent execution, customers, certifications or statistics: preview content on Overview is labeled as an illustration.

## Tokens
- Ground `#F3F6FC`, surface `#FFFFFF`, tint `#EEF3FC`, rules `#E3E8F1` / `#D3DBE8`.
- Ink `#131A2B`, secondary `#4B586F`, muted `#6B7890` (captions only), disabled `#9AA5B8`.
- Accent cobalt `#3D5CE8` (hover `#2F4BD6`, ink `#2A43BF`, soft `#EAEFFF`). Used for primary action, selection and the running state only.
- States carry meaning only: ok `#12825A`, warn `#A8620A`, bad `#C9333F`, each with a soft fill and line. Rejected = filled red; execution failed = red outline; unknown = amber; skipped = dashed.
- Type: Inter Variable (UI, Vietnamese coverage); Geist Mono Variable for hashes, addresses and amounts only. Product scale 11.5 / 12.5 / 13.5 / 15 / 16 / 21 / 32; hero 32–48, tracking ≥ −0.035em.
- Radii 8 / 10 / 14 / 18 / 22; pills for small controls only. Elevation: shadow-1/2/3, never a 1px border under a wide shadow.
- Motion: 180–260 ms, `cubic-bezier(.16,1,.3,1)`; one authored moment (hero preview reveal); running nodes breathe; everything respects `prefers-reduced-motion`.

## Glass material (`.glass`)
Gradient translucent fill + `backdrop-filter: blur(22px) saturate(185%)` + inner rim highlights + masked specular edge (`::before`). Fallbacks: opaque white without `backdrop-filter` support and under `prefers-reduced-transparency`. Applied to: floating nav, hero preview window, "What is PaceVant" strip, CTA band. Not applied to graph nodes, tables or evidence.

## Live Demo
Three zones: scenario sidebar (264px) · graph (fluid) · result panel (300px); two columns below 1180px, one below 900px.
The graph is three phase rows stacked vertically (Preparation / Verification / Execution) computed from the measured canvas width so it renders at zoom 1. Rows wrap only when a node would drop below 118px, balanced (5 → 3 + 2). Edges keep their ids (`edge-i-i+1`); row-to-row edges route as a carriage return along the left gutter so they never cross nodes. Node and phase states derive solely from `workflowNodeState`.

## Evidence
Filterable run table (all / confirmed / blocked / other) with tx hashes and Snowtrace links only for public receipts; a read-only source panel shows the `/judge/source` snapshot (policy, oracle, vault balance, PolicyVault/Owner/Attestor/Relayer addresses).

## Research decisions
UI UX Pro Max confirmed the Liquid Glass style rules (navigation/controls only, reduced-transparency fallback, 4.5:1 text); its luxury palette and serif pairing were rejected for this product. Impeccable's craft floor and Operate guidance set the restraint on the workbench; Vercel Web Interface Guidelines drove focus, reduced-motion, tabular numerals, `translate="no"` hashes and the skip link.
