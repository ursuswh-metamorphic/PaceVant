# DeepSeek chính thức và thứ tự ưu tiên AI

Theo yêu cầu operator, `.env` và `.env.example` dùng thứ tự **DeepSeek → Groq → Gemini → Xingchi**. Khóa thật chỉ nằm trong `.env`; template có `DEEPSEEK_API_KEY=` rỗng. Không đưa khóa vào frontend, execution-only environment, owner deployment environment, log hoặc báo cáo.

## Model và protocol

- Model `deepseek-flash`: dòng Flash nhẹ/chi phí thấp hơn Pro trong [bảng model chính thức](https://api-docs.deepseek.com/quick_start/pricing/), kiểm tra ngày 20/11/2026. Không dùng tên model cũ theo trí nhớ hoặc một gateway bên thứ ba.
- Endpoint cố định `https://api.deepseek.com/chat/completions`, Bearer token, `thinking: {type: disabled}`, `max_tokens` hữu hạn và `stream: false` theo [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).
- Planner dùng JSON object theo schema direction/amount và kiểm tra lại độc lập bằng grammar, precision, exact amount và direction. Shield dùng JSON array; không ép `json_object` vào một output array.
- Không cấp tool thực thi cho model. Model không trả địa chỉ tùy ý để compiler đưa thẳng vào giao dịch. Mandate và pipeline xác định token/vault/router/calldata; model không nới risk/proof/session policy.
- DeepSeek sử dụng số dư/grant của tài khoản. Cấu hình này không cam kết dùng API DeepSeek miễn phí, không tắt giới hạn output/timeout, không bảo đảm luôn sẵn sàng.

## Biến môi trường

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash
PACEVANT_PLANNER_PROVIDER=rotate
PACEVANT_AI_ROTATION_ORDER=deepseek,groq,gemini,xingchi
PACEVANT_SHIELD_PROVIDER=deepseek
PACEVANT_SHIELD_MODEL=deepseek-flash
PACEVANT_SHIELD_BASE_URL=https://api.deepseek.com
PACEVANT_SHIELD_API_STYLE=chat_completions
PACEVANT_SHIELD_API_KEY=
PACEVANT_SHIELD_FALLBACKS=groq,gemini,xingchi
GEMINI_MODEL=gemini-3.1-flash-lite
```

Shield đọc lại `DEEPSEEK_API_KEY` khi provider là `deepseek`, endpoint và model đã qua validation; không cần copy key vào `PACEVANT_SHIELD_API_KEY`. Model Google dự phòng là Flash-Lite có free tier; keys Groq/Gemini/Xingchi hiện có được giữ nguyên. Code vẫn hỗ trợ cấu hình provider đơn lẻ và thứ tự cũ để không phá profile đã tồn tại; thứ tự trong env hiện tại là cấu hình có hiệu lực cho demo này.

Planner fallback chỉ cho availability/auth/rate/quota/schema errors; sai amount/direction không được “thử model khác đến khi pass”. Shield kiểm tra schema, có giới hạn inference window, retry/cooldown và fail closed nếu không có kết quả hợp lệ. ITAG semantic evaluator dùng cùng Shield provider chain và ghi provider/model thực tế. Tất cả provider errors được ghi mã đã lọc, không log raw response chứa credential. `PLANNED` event và Shield `provider_trace` cho biết model nào thực sự trả lời; model cấu hình không được dùng thay bằng chứng model thực chạy.

Planner giữ SQLite quota/cache riêng từng provider. Các biến `GROQ_*` hiện có vẫn là tên cấu hình chung cho quota/timeout/output của planner adapters; không tăng chúng theo giả định tài khoản đã trả tiền. Shield dùng `PACEVANT_SHIELD_*` riêng. Restart backend sau khi đổi env.

## Kiểm chứng

Kiểm tra trực tiếp DeepSeek: HTTP 200, `deepseek-flash`, câu trả lời `[]`, khoảng 860 ms. Planner thật parse `Buy WAVAX with 0.000001 USDC` thành đúng 1 base unit với provider DeepSeek. Những phép gọi này chỉ chứng minh adapter/API và parsing; không tự chứng minh giao dịch Fuji.

[Runbook toàn luồng Fuji](../demo/FUJI_ITAG_LIVE.md) và [báo cáo pipeline hiện tại](fuji-itag-live-validation.json) ghi receipt, risk/proof, Shield/ITAG, model trace và các negative eth_calls. [Lượt Gemini trước cutover](fuji-itag-gemini-validation.json) là bằng chứng riêng, không được gọi là lượt DeepSeek.

Test offline dùng MockTransport để kiểm tra payload/endpoint, thứ tự ưu tiên, exact amount, từ chối sai amount và không rò key sang execution-only environment. Chúng kiểm tra cơ chế phần mềm, không đo độ chính xác hoặc latency của model thật.

```powershell
uv run --locked pytest backend/src/treasury_backend/modules/planning/tests backend/tests/integration/test_planning_configuration.py backend/tests/control/test_shield_native_rotation.py -q
```


ITAG citation handling: graph node IDs, task IDs and evidence refs remain separate namespaces. A bounded extra model call may repair a missing node linkage only when every submitted node/task/ref already exists in the graph. The original semantic verdict, drift flag, source, task relationships and presence of uncertainty must stay unchanged. A fabricated ref or a changed verdict is rejected. This does not turn a semantic veto into approval; the repair attempt, provider trace, latency and token usage are included in assessment metadata. The correction catalog contains only the missing links to stay within the context budget.


The final official-DeepSeek workflow `workflow_329702d0468442d88c8f9789c4eca5c5` is CONFIRMED on Fuji block 61369698. The linked public report records DeepSeek as the runtime planner, every Shield check, and the ITAG semantic provider. All public checks/negative calls passed.
