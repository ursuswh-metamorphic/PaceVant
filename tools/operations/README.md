# Recovery tooling

`recover_submission.py` sends an authenticated request to the **running unified backend**. It does not construct a legacy B HTTP client, load an attestor into a second control process, sign, or resend a transaction.

```sh
uv run --locked python tools/operations/recover_submission.py WORKFLOW_ID TX_HASH --env-file .env
# Hosted backend:
uv run --locked python tools/operations/recover_submission.py WORKFLOW_ID TX_HASH --api-url https://your-backend.example --env-file deploy/runtime.env
```

The default origin is loopback at TREASURY_A_PORT (8000). Only PACEVANT_OPERATOR_TOKEN is forwarded, never wallet keys. Redirects and environment proxies are disabled; public HTTP, URL credentials and URL paths are rejected. Error output does not echo credentials or server response bodies.

The API is `POST /v1/workflows/{id}/recover` with body `{"tx_hash":"0x..."}`. It accepts only a SUBMITTING workflow and a known execution journal/receipt whose decision/build/chain binding matches that workflow. Unknown/mismatched hashes fail; repeat recovery after a terminal result fails. Copy the known hash from the existing execution journal; do not invent a replacement trade. Pending receipts continue to hold reservations.

Read [current system design](../../docs/AI_Treasury_Security_System_Design_v2.1.md) for recovery/state semantics. Regular startup/deploy/doctor/demo/renew commands belong to `uv run treasury`. Never commit private journals, raw transactions or keys.
