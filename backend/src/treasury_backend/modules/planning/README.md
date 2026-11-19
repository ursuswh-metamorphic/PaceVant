# planning

Provider failover is now available: `PACEVANT_PLANNER_PROVIDER=rotate`, with default order `gemini,groq,xingchi`. Google uses native Gemini `generateContent` with `gemma-4-26b-a4b-it`; the user-confirmed Xingchi endpoint uses `/v1/responses` with model ID `gpt-6.1-sol`. Groq strict-schema behavior remains available as a standalone provider. See [rotation configuration and live validation](../../../../../docs/integrations/AI_PROVIDER_ROTATION.md).

`remote.py` provides native wire adapters; `rotation.py` orchestrates bounded failover and request-local trace metadata. `PLANNED` timeline events record actual provider/model and sanitized attempt reasons. The workflow's top-level provider `rotate` identifies configuration, not a claim that every provider was called.

Each request attempts each configured provider at most once. Rate/local-quota/auth/availability/invalid-JSON failures can advance to the next provider. Unsupported goals and amount/direction mismatches stop the request instead of trying another model. Independent validation and all downstream gates are mandatory. All providers failing refuses planning; never fall back to rules/fixtures. Cooldowns/cache/rolling quotas remain durable per provider; Groq retains its existing root data path when switching to rotate. Existing `GROQ_*` budget/time/output/cache settings also bound the new provider adapters (legacy configuration names); no new runtime SDK is required.

Turn a bounded user goal into a typed transaction proposal.

## Interface and files

`GoalPlanner.parse` / `metadata` / `close` in `provider.py`; `GroqPlanner` in `groq.py`; `propose`, `requested_amount`, `reverse_goal` in `service.py`. Settings: `config/planning.py`.

Input: bounded goal, mandate, chain context and revised amount. `rules` is the explicit offline provider; `groq` uses real strict-schema chat completions. Independent grammar/amount/direction validation remains mandatory. The model returns direction/decimal amount only; a deterministic compiler creates `TransactionProposal` from trusted mandate fields. Groq failure never falls back to fixtures/rules.

## Cache, quotas and failure boundaries

Durable `planner.sqlite3` and `planner.lock` beside the control DB serialize calls and preserve quota/cache across restart. Reserve UTF-8 message/schema bytes + output cap + margin before HTTP; failures stay charged locally. Rolling per-minute/day request/token budgets, timeout, bounded response, no redirects/proxies/automatic retries and Retry-After cooldown reduce provider throttling. Shared organization activity outside this data path cannot be guaranteed.

Draft cache stores direction/amount and expiry keyed by prompt version/model/goal; it never caches authorization/proof/signatures/chain state. Planning resolves before the approval window. Replans reuse the validated goal plan but regenerate build/simulation/proof. Provider auth/rate/schema/network/mismatch fails closed with sanitized errors and ESCALATED workflow; no signature.

Only static instructions + goal reach Groq; no wallet keys, service tokens or balances. `GROQ_API_KEY` is explicitly forwarded to control/unified runtime only. Existing httpx is sufficient; no new SDK/runtime language dependency. Unsupported free-form goals remain uncertain until independent semantic validation is designed.

## Development boundary

Add a goal parser or planner adapter here. Keep allowlists, mandate caps and uncertainty explicit. A proposed action still goes through alignment, simulation, risk and decision; the planner cannot approve or sign it.

Import public functions from `treasury_backend.modules.planning` where exported. Infrastructure settings belong to `config/`; process/deployment wiring belongs to `operations/`. See [the module map](../../../../MODULES.md) for dependency direction and shared-review rules.

## Verification

Run from the repository root after `uv sync --locked`:

```sh
uv run --locked python -m pytest backend/tests/control/test_workflows.py -q
uv run --locked python -m pytest backend/src/treasury_backend/modules/planning/tests backend/tests/integration/test_planning_configuration.py -q
```

Add focused tests under this module's `tests/` directory for new feature logic; pytest discovers them automatically. Existing regression tests remain under `backend/tests/`. Chain integration tests require native Foundry and compiled contracts; use [backend setup](../../../../README.md).

[Groq/env integration](../../../../../docs/integrations/GROQ_PLANNER_AND_ENV.md) records current config, real API/LOCAL validation and remaining mocks.
