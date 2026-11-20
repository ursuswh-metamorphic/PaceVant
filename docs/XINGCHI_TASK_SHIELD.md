> Imported technical reference from `origin/main` at `08c35df`. Adapted paths below use the modular Python backend. Historical test counts/live metrics in this document belong to upstream; see [current merge verification](integrations/MAIN_SYNC_2026_11_20.md) for this checkout. The current `.env` explicitly sets Task Shield to `disabled`; `paper`/`wallet_hardened` are opt-in. The current Fuji Circle-USDC/Chainlink/PDR-V2 authorization path is supported; blanket Fuji valuation blockers below describe upstream faucet-USDC only.

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

# Xingchi Responses API — setup and real-model validation

Configured on **20 November 2026 (Asia/Saigon)** using the provider and credential supplied by the user. Production Task Shield now supports both Chat Completions and Responses, without replacing its extraction/scoring pipeline or weakening the wallet gates. [Machine-readable evidence](../evidence/task-shield-xingchi-live.json).

## Working local setup

| Setting | Configured value |
|---|---|
| Endpoint | `https://xingchiapi.com/v1/responses` |
| Provider | `openai_compatible` |
| API style | `responses` |
| Model alias | `gpt-6.1-sol` |
| User-Agent | `Cursor/0.45.0`, per the supplied provider example |
| Mode | `wallet_hardened` |
| Epsilon | `0`, unchanged |
| Temperature | Omitted in this provider profile, matching the supplied minimal API example; not the paper's controlled temperature-0 experiment |
| Timeout / retry | 60 seconds per call / 1 bounded retry |
| Server | `http://127.0.0.1:8021` |
| Chain mode | MOCK for local operational endpoints; the separate chain observation test reads public Fuji only |

The local **`.env.task-shield`** contains the supplied API credential plus newly generated separate operator/internal service credentials. It is ignored by Git and is not included in the PR. Existing `.env`, wallets, deployments and dashboard databases were not overwritten. The dedicated local server uses `data/control-plane-xingchi-mock.sqlite3`.

Working commands from repo root on this machine:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.control-data-integration/venv-a'

# Benign connection/JSON/UTF-8 check:
uv run --locked --env-file .env.task-shield python tools/evaluation/check_shield_provider.py

# Start the configured Task Shield API (already started on port 8021 during setup):
uv run --locked --env-file .env.task-shield python scripts/serve.py --port 8021

# Local real-LLM cases; these do not send transactions:
uv run --locked --env-file .env.task-shield python tools/evaluation/evaluate_task_shield.py --output data/task-shield-xingchi-live-evaluation.json

# Real LLM interception + actual public Fuji read; the denied-write callback is only a counter:
uv run --locked --env-file .env.task-shield python tools/evaluation/check_task_shield_live_flow.py
```

The server's `/healthz` is public health metadata. Task/session/check APIs require the Bearer operator credential from the local profile. The provider credential is backend-only and must not be supplied to the browser. The existing mock dashboard is not a new token-management UI; this setup targets the backend API and shield runtime.

## Adapter behavior

`ShieldConfig.api_style=responses` selects `/responses`, sends structured system/user messages as input, requests `store=false` and disables streaming for this bounded checker. Completed assistant `output_text` parts are concatenated; reasoning items are not treated as final text. Missing/incomplete status, refusals, unexpected tool calls and malformed output fail closed. Provider `input_tokens` / `output_tokens` are normalized to existing `prompt_tokens` / `completion_tokens` counters.

The base URL is `https://xingchiapi.com/v1`, not the full `/responses` endpoint, so paths cannot be accidentally appended twice. Provider-required User-Agent is configurable and rejects control/header-injection characters. Redirects remain disabled; no Authorization forwarding occurs to a different host. Existing Chat Completions defaults and provider tests remain supported. API response/error logging never prints the credential.

Protocol shape was checked against the official [Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create) and then verified against the actual supplied Xingchi endpoint. Provider compatibility and a configured alias do not establish that this is the paper's original GPT-4o model or a comparable experiment.

## Actual results, including failures

The initial connection returned a valid Vietnamese greeting JSON in **5,922 ms**, with provider-reported usage of 50 input / 44 output tokens. This confirms real network/model response parsing rather than a scripted fixture.

| Real-model local suite | Initial run | Revised run |
|---|---:|---:|
| Cases | 15 | 15 |
| Expected classifications matched | 13 | 14 |
| Benign cases aligned | 3/4 | 4/4 |
| Adversarial cases classified misaligned | 10/11 | 10/11 |
| Unavailable results | 0 | 0 |
| Checker LLM calls | 26 | 25 |
| Sum of checker-reported latency | 271,239 ms | 244,550 ms |

These are **local classification cases**, not AgentDojo ASR or wallet attack success. No actual transaction is executed by the case runner. Cost is left unknown because no authoritative provider pricing was supplied. Usage counters in evidence are reported by the provider and cover the checker reports; they do not represent a complete invoice for initialization, probes, interrupted setup attempts or separate runtime checks.

Two concrete findings guided the revision:

1. The quote case used the undefined argument strings `mandated USDC` / `mandated WAVAX`. The model correctly identified missing identity context. The fixture now uses `USDC` / `WAVAX` explicitly for the language-only quote scenario; this is not a fabricated on-chain token mapping or USD valuation.
2. The first extractor returned `[]` for an assistant statement beginning “I will…”. Prompt version `task-shield-acl2025-v1.1` explicitly includes first-person assistant intentions/plans as actionable instructions, as required by Section 3.1. No heuristic detector or score threshold was substituted. The revised assistant-deviation case is classified misaligned.

The revised run still has **one false alignment: `wrong_chain`**. The model assigned positive scores for not violating other prohibitions, even though it assigned zero to actually achieving the swap objective. With the paper's sum/zero rule, that positive total passes. This result is retained in the evidence with the model's scores/reasons. It was not relabelled or hidden. Deterministic chain/mandate controls remain mandatory and refuse that financial action independently; a positive LLM score is never execution permission.

The runtime test uses the same `ShieldRuntime` interception used by orchestration, with the actual configured LLM. It allows a public Fuji block read, checks the resulting tool output, then refuses an unrelated transfer proposal **before** its counter callback runs. The callback count is `0`; no transaction-sending function exists in that diagnostic script. The resulting block/hash and check statuses are in the evidence file.

## Regression verification and practical limits

- Root A/shared: **168 passed**, 1 opt-in public Fuji test skipped. This includes 16 new Responses/configuration/error-path tests; existing 59 scripted shield tests remain regression tests, distinct from the real-model runs above.
- Existing B/A+B/contract/golden checks remain in CI. Provider calls in CI still use deterministic fixtures; CI does not receive the supplied API credential.
- No public Fuji broadcast or deployment occurred. LFJ faucet USDC valuation and its fail-closed oracle identity gate are unchanged.
- Measured provider latency can exhaust the existing **30-second** financial approval TTL across multiple sequential checks. The TTL was not increased or bypassed. A complete financial workflow with this provider is not claimed as verified by the read-only diagnostic.
- The API is configured and running locally. The change is proposed through the existing Task Shield PR; it is not automatically merged into main.
