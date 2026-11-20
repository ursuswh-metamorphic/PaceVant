# Demo User UI

One predefined identity is selected from `/v1/demo/config`; a separate demo access code authenticates `/v1/demo/*` only. No wallet extension or private key is required. The access token stays in tab memory, not local/session storage, URL, static config or bundled source. Only a random idempotency/request ID is saved in sessionStorage so a lost response/reload can resume through a GET.

The API supplies gas credit allocation, available/reserved/spent amounts, actual gas receipt fields, immutable debit/reversal history, transactions and request history. Render with DOM textContent and BigInt wei arithmetic. The demo wallet AVAX balance is a separate on-chain read; unavailable remains unknown, never zero. Credit is explicitly labeled as a sponsor-funded demo allowance, not a verified cash deposit.

`app.js` owns account selection and the existing workflow/timeline viewer. `features/treasury` uses the scoped treasury endpoint when demo mode is active. `features/demo/index.js` owns balance/history rendering and safe request resumption. A pending/unknown request disables new submits in that tab. The check button never POSTs or rebroadcasts. If the server confirms a request ID was never accepted, the tab can clear that identifier; network failures retain it.

Run `node tools/quality/check_frontend.mjs` for developer syntax validation (Node is not a deployed backend dependency). Full behavior is covered at the API/EVM boundary by the demo integration tests; browser visual verification is separate. [Runbook](../../../../docs/demo/DEMO_USER_GAS_CREDIT.md).
