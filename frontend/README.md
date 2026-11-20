# PaceVant frontend

The current public judge interface lives in `src/app`: React + TypeScript + Vite, Tailwind CSS, locally owned shadcn-style Radix components, Motion for React, Lucide and TanStack Query. It has three tabs: Live Demo, Security & Policies, History.

```bash
npm ci --prefix frontend
npm run --prefix frontend dev
npm run --prefix frontend test
npm run --prefix frontend build
```

Development proxies `/judge` to the local backend at port 18040. Start it separately with `uv run --locked python -m treasury_backend.operations.judge_serve --port 18040`, using a model-only environment as described in the deployment guide. It does not load the private root `.env`. Without model configuration, verified recordings remain available. Local HTTP testing requires `PACEVANT_JUDGE_SECURE_COOKIE=0`; production HTTPS keeps secure cookies enabled.

Production output is **`dist`**, served through native Nginx. Node is build tooling only. See [judge guide](../JUDGE_DEMO_GUIDE.md) and [VPS deployment](../VPS_DEPLOYMENT.md).

| Path | Responsibility |
|---|---|
| `src/app/App.tsx` | Three tabs, fixed scenarios, exact request recovery and backend polling |
| `src/app/lib/api.ts`, `types.ts` | Same-origin API client and response contracts |
| `src/app/lib/recovery.ts` | Persist request identity before POST; recover by key |
| `src/app/lib/pipeline.ts` | Gate states derived from backend evidence |
| `src/app/components` | Pipeline, results, accessible evidence drawer and policy sections |
| `src/app/components/ui` | Locally maintained Radix/shadcn-style primitives |
| `src/app/styles.css` | Light fintech design, responsive layouts and reduced motion |

Real runs execute on isolated Fuji forks with temporary roles. Replays are explicitly labeled and hash checked. Missing, rejected or uncertain evidence cannot become a confirmed receipt; fork hashes never link to a public explorer. Model/RPC/oracle failures remain visible. The judge interface receives no operator token or wallet signing key.

`legacy-index.html`, `treasury-mvp.html`, `treasury-v3.html`, the older `src/features`, `src/api/client.js`, ITAG viewer and legacy Docker files remain compatibility/research sources. They are not the public judge entrypoint. The authenticated operator API remains a separate backend surface, outside the native public judge Nginx proxy. Old Demo User/HMAC and four-area interface descriptions are superseded.
