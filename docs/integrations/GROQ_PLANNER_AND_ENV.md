# Groq planner và cấu hình ví — 19/11/2026

> Tích hợp sau checkpoint này bổ sung oracle quan sát và adapter thực thi LFJ trên fork. Xem [Fuji/LFJ V2.1](FUJI_LFJ_V2_1.md) để biết trạng thái hiện tại của DEX và định giá.

Private `.env` chọn `PACEVANT_PLANNER_PROVIDER=groq`, model `openai/gpt-oss-20b`. Template chọn `rules` để fresh clone/test offline không tự gọi dịch vụ ngoài. Groq lỗi không fallback sang rules/MOCK. Chain mode và planner provider là hai cấu hình độc lập.

## Đã tích hợp và kiểm chứng

Ba private key được cấp đã khớp ba địa chỉ tương ứng và được cập nhật vào `.env`. `.env`, `.env.example` và initializer `ENV_DEFAULTS` có cùng tập tên biến, không có tên trùng; template không chứa secret thật. Các biến compatibility giữ alias rõ để không phá code đang dùng.

Một request Groq thật trả direction/amount đúng; request lặp dùng cache, không inference lần hai. Full LOCAL cũng chạy actual Groq → alignment/risk → V2 proof VERIFIED/ba UNSAT → ký → actual Anvil receipt CONFIRMED. Không gửi Fuji transaction. Workflow metadata/dashboard hiển thị provider/model; `/health` chỉ cho biết config, không gọi Groq mỗi healthcheck.

Regression sau tích hợp: full suite **182 Python tests passed, 1 LOCAL ablation opt-in skipped**, hai dependency deprecation warnings. Sau hardening thêm phần schema vào token reservation, focused suite **26 passed** (21 provider cases + 5 configuration/workflow cases), gồm regression schema-overhead mới. Các cases kiểm schema/amount/direction tampering, quota persistence, 429/cooldown, timeout/auth/redirect, concurrency cache và no-fallback/no-signing. Không mô tả focused run như một lần full suite mới. Tests dùng HTTP doubles; real API/LOCAL là các lượt kiểm riêng. [Public evidence](groq-validation-summary.json); private logs trong `.control-data-v2/`.

## Ví và biến môi trường

| Vai trò | Secret hiện tại | Alias/public checks | Nơi dùng |
| --- | --- | --- | --- |
| Owner | `DEPLOYER_PRIVATE_KEY` | `B_FUJI_OWNER_PRIVATE_KEY=${DEPLOYER_PRIVATE_KEY}`, optional `TREASURY_OWNER_ADDRESS` | Explicit deploy/renew trên máy quản trị; loại khỏi serving env |
| Attestor | `PACEVANT_ATTESTOR_KEY` | `B_FUJI_ATTESTOR_ADDRESS`, optional `TREASURY_ATTESTOR_ADDRESS` | Ký ApprovalV2 sau decision/revalidation |
| Relayer | `AGENT_PRIVATE_KEY` | `B_FUJI_RELAYER_PRIVATE_KEY=${AGENT_PRIVATE_KEY}`, `AGENT_ADDRESS`, `PACEVANT_RELAYER_ADDRESS`, optional `TREASURY_RELAYER_ADDRESS` | Ký/gửi EVM envelope, trả gas |

Expected addresses nếu có phải khớp key/manifest theo role. LOCAL dùng ephemeral local keys. Thay env không tự đổi owner/attestor của contract đã deploy. Keys/API key đã qua chat chỉ nên dùng testnet; thay key trước khi dùng tài sản có giá trị. Hosting dùng [runtime template](../../deploy/runtime.env.example) riêng, không owner key hoặc aliases chưa resolve.

## Luồng và giới hạn của LLM

Groq nhận static instructions + goal, trả strict JSON chỉ có direction và decimal amount. Không gửi private wallet keys, service tokens, balances hoặc SQL records vào prompt. Independent parser đối chiếu direction/amount/precision với goal, sau đó deterministic compiler lấy chain/vault/router/recipient/slippage từ trusted mandate. Model không cấp thẩm quyền giao dịch.

Goal hỗ trợ: `Buy WAVAX with 200 USDC`, `Mua WAVAX bằng 200 USDC`, `Sell 0.1 WAVAX for USDC` và các mẫu trong parser. Goal tự do/không chắc chắn bị từ chối. Đây là bounded LLM planner, chưa phải semantic verifier hoặc agent hội thoại tự do. Reverse vẫn cần owner cap dương.

Plan được lấy trước approval window 30 giây. Replan không gọi model lại, nhưng amount mới phải build/simulate/prove lại. Cache chỉ lưu direction/amount theo hash prompt version/model/goal và TTL; không cache approval, proof, signature, balances hoặc session. Mỗi workflow vẫn đi qua mọi gate.

## Model và quota miễn phí

Kiểm tra 19/11/2026: Groq liệt kê GPT-OSS 20B trên Free Plan với 30 RPM, 1.000 RPD, 8.000 TPM và 200.000 TPD; exact quota tùy organization. Model hỗ trợ strict JSON schema. [Rate limits chính thức](https://console.groq.com/docs/rate-limits), [Structured outputs](https://console.groq.com/docs/structured-outputs).

| Biến | Default | Vai trò |
| --- | --- | --- |
| `PACEVANT_PLANNER_PROVIDER` | Template `rules`, private env `groq` | Explicit offline hoặc real API |
| `GROQ_API_KEY` | Blank trong template | Secret chỉ vào control/unified env, không standalone execution |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Reviewed strict-schema model; không auto model/tier fallback |
| `GROQ_TIMEOUT_SECONDS` | 20 | HTTP timeout |
| `GROQ_MAX_COMPLETION_TOKENS` | 512 | Bound completion theo provider semantics |
| `GROQ_REQUESTS_PER_MINUTE` | 4 | Rolling 60s cap |
| `GROQ_REQUESTS_PER_DAY` | 200 | Rolling 24h cap |
| `GROQ_TOKENS_PER_MINUTE` | 4.000 | Conservative local token reservation |
| `GROQ_TOKENS_PER_DAY` | 80.000 | Conservative rolling 24h budget |
| `GROQ_CACHE_TTL_SECONDS` | 300 | Draft cache TTL, không phải approval validity |

`planner.sqlite3`/`planner.lock` nằm cạnh control DB. File lock serialize calls/cache; token/request reservations commit trước HTTP và survive restart. Failed requests vẫn giữ reservation. Token estimate dùng UTF-8 message/schema bytes + output cap + framing margin; không phải tokenizer/billing chính xác, có thể refuse sớm hơn provider. Quota dùng chung cho processes cùng data path; profiles/hosts khác có local budgets riêng.

429 tạo durable cooldown theo `Retry-After`, mặc định 60s nếu header không hợp lệ; exhausted remaining headers cũng chặn thêm request. Không automatic retry, redirect, proxy inheritance, paid-model fallback hoặc bỏ gate. Cache hit vẫn dùng được vì không gọi API. `PLANNER_LOCAL_QUOTA`, `PLANNER_RATE_LIMITED`, `PLANNER_BUSY`, auth/network/schema/mismatch được sanitize; workflow ESCALATED và không ký.

**Không thể bảo đảm tuyệt đối không gặp 429:** quota chung theo organization, app/profile/host khác có thể cùng tiêu quota; provider có thể đổi limits/availability. Code không chọn/đổi billing plan tài khoản qua API key. Đối chiếu Limits trong Groq console nếu actual quota khác. Không tự retry start workflow vì request đó có thể tạo một trade mới.

## Chạy và test

```powershell
# Chỉ kiểm config, không inference/transaction:
uv run --locked treasury doctor --network fuji
# Real Groq + local proof/EVM/receipt, không gửi Fuji:
uv run --locked treasury local --once
# Giữ dashboard:
uv run --locked treasury local
# HTTP doubles trong regression, không tiêu quota:
uv run --locked python -m pytest backend/src/treasury_backend/modules/planning/tests backend/tests/integration/test_planning_configuration.py -q
```

Private env chọn FUJI; canonical `treasury local` override sang LOCAL. `treasury serve --network fuji` cần actual deployment manifest/session. Direct API runner không tự tải root env nếu không launcher/explicit env loading.

## Phần vẫn mock/chưa chạy public

Oracle demo vẫn USDC=1/WAVAX=20, external oracle chưa merge. Token/liquidity/adapter vẫn mock contracts dù EVM execution thật. LLM không được bịa giá thay oracle. V2 Fuji deployment/receipts và hosted smoke cần bước riêng trong [runbook](../demo/AVALANCHE_FUJI_DEMO.md). Groq key không tự làm chúng thành real market execution.

Source: [planning module](../../backend/src/treasury_backend/modules/planning/README.md), [settings](../../backend/src/treasury_backend/config/planning.py). Không thay Solidity, proof formulas hoặc các signing gates.
