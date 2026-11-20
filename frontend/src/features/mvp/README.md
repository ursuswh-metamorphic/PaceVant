# Single-tenant MVP frontend

Default page: `frontend/treasury-mvp.html`. Four areas show actual treasury/Relayer facts, two fixed operations, security evidence and isolated attack cases. Reuses the existing API client and tab-memory credential state.

No Demo User persona or private-key entry. Public status is read-only; execution requires the operator and Owner's existing on-chain session. Owner administration is prepared unsigned and signed separately by the exact Owner wallet. Only actual public-chain outcomes receive Fuji explorer links.

Run `npm run demo:mvp:local` for explicitly labeled LOCAL TEST protocol fixtures, then `tools/quality/check_mvp_browser.py` for browser verification. Static API base configuration remains in `frontend/assets/config.js`. The local fixture is not a live model or public-chain execution.
