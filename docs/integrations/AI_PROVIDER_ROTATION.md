# AI provider failover — 20/11/2026

The Python planning module supports Gemini, Groq and user-confirmed Xingchi. This change affects bounded goal extraction only; it does not add a free-form agent, change trading policy, replace oracle data, or grant models signing authority.

## Private configuration

```dotenv
PACEVANT_PLANNER_PROVIDER=rotate
PACEVANT_AI_ROTATION_ORDER=gemini,groq,xingchi
GEMINI_API_KEY=
GEMINI_MODEL=gemma-4-26b-a4b-it
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b
XINGCHI_API_KEY=
XINGCHI_BASE_URL=https://xingchiapi.com/v1
XINGCHI_MODEL=gpt-6.1-sol
```

The supplied keys are saved only in ignored `.env`; `.env.example` has empty keys. The confirmed Xingchi URL was supplied by the user as `https://xingchiapi.com/v1/responses`; config stores its `/v1` base and the adapter appends `/responses`. The adapter sends the compatibility User-Agent `Cursor/0.45.0` from the user's working sample. It does not imply that the backend uses Cursor. Other HTTPS `/v1` endpoints require explicit configuration; no endpoint discovery with a private key occurs.

The single backend receives explicit AI credentials. Execution-only/deployment subprocess environments exclude them. Owner and Demo User keys remain outside the serving environment. Only static planning instructions, JSON schema and the user goal are sent to the selected provider; never include secrets in a user goal. RPC data, wallet private keys and signatures are not needed for model inference.

## Free model and spending limits

Google's current [Gemma hosting documentation](https://gemma.ai/deployment/gemini-api/) lists Gemma 4 26B A4B and 31B. Its [API pricing](https://ai.google.dev/gemini-api/docs/pricing) lists Gemma 4 input/output as free of charge. The adapter allowlists `gemma-4-26b-a4b-it`; it never upgrades to a paid Gemini model on failure. The local setting restricts model choice, not the billing state or future pricing of an external account.

[Google rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) are project-based, not key-based. This feature switches independent providers for availability; it does not rotate Google keys to bypass a project's quota. Local quotas reduce throttling but cannot guarantee zero 429 responses when a project is used elsewhere or provider limits change. Xingchi is an optional third-party fallback; no free-tier promise is made for its calls. Model ID acceptance does not independently certify which upstream model a gateway runs.

Adapters share the existing bounded defaults: `GROQ_TIMEOUT_SECONDS=20`, output cap 512, 4 requests/minute, 200/day, 4000 token-budget units/minute, 80000/day, cache TTL 300s. These legacy-named settings bound each provider independently. Reservations conservatively count UTF-8 prompt/schema bytes plus output cap/margin, not the provider's exact tokenizer. Failed requests retain their reservations. A timeout may still consume provider quota. To disallow Xingchi spending, omit it from `PACEVANT_AI_ROTATION_ORDER`.

## Failure semantics

1. Follow the explicit order, skipping providers missing a key or required endpoint.
2. Use each provider's own durable quota/cache/cooldown. Preserve legacy Groq quota history.
3. Make at most one bounded HTTP attempt per provider; no redirect/proxy following or automatic same-provider retry.
4. On 429 honor Retry-After (default 60 seconds); auth failure cooldown 300 seconds; availability/invalid response cooldown approximately 30 seconds. Move to the next configured provider.
5. Validate JSON, supported direction and exact amount independently. Wrong amount/direction or unsupported goal stops the request immediately. There is no search for a model that approves a rejected semantic result.
6. If all fail, return `PLANNER_ALL_PROVIDERS_UNAVAILABLE`; do not issue a plan/signature from a fixture or rule fallback.
7. Timeline `PLANNED` records the successful provider/model and preceding sanitized errors; failed workflows record attempt reasons. Trace uses request-local ContextVar so concurrent requests do not share attribution. Only draft outputs are cached; proofs/signatures are not cached by this feature.

Gemma and Xingchi use prompted JSON, followed by strict local Pydantic validation; hosted strict-schema enforcement is not assumed. Groq continues to request strict JSON schema. Native Gemini uses the API key header rather than a query URL; Xingchi/Groq use Bearer auth. Provider response bodies, keys and arbitrary HTTP exception strings are not exposed in workflow errors.

## Validation and running

Both new providers returned a valid draft for `Buy WAVAX with 0.000001 USDC` in direct API checks. No blockchain transaction was sent. [Sanitized live results](ai-provider-live-validation.json) record the requested/accepted model IDs and independent amount validation. Unit tests use mocked transports to exercise outages, 429, restart cooldown, cache, key isolation, semantic mismatch and all-provider failure; workflow integration verifies downstream gates and actual-provider tracing.

```powershell
uv run --locked python -m pytest -q backend/src/treasury_backend/modules/planning/tests backend/tests/integration/test_planning_configuration.py
```

An already-running backend keeps its old settings until restarted. After restart, `/health` reports `planner_provider=rotate`; use the workflow `PLANNED` event to see the provider actually used. A successful draft from either new provider does not revalidate a session or guarantee a swap; all existing Fuji gates still apply.
