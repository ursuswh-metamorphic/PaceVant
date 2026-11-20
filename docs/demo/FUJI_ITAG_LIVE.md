# Fuji: chạy luồng V2.1 có Task Shield và ITAG

Tài liệu vận hành cho bản sửa sau `48fae36`. Checkpoint rollback: `backup/pre-fuji-fixes-48fae36`. Đây là backend Python/FastAPI một process, execution gọi nội bộ, Solidity V2 giữ nguyên. Không có backend Node.js.


**Live result:** official DeepSeek Flash handled the planner, Task Shield and ITAG semantic assessment. Workflow `workflow_329702d0468442d88c8f9789c4eca5c5` confirmed at Fuji block **61369698**: [public transaction](https://testnet.snowtrace.io/tx/0x3fdbbeb96646ed2e88ce31a63068747dd6d288644487cc2c8a09b49a4e2f55fe). All 14 public-chain checks and 3 negative eth_calls passed; the live intent history also rejects completion replay. Five exported SMT queries were rehashed and independently solved. [Full report](../integrations/fuji-itag-live-validation.json), [test scope](../integrations/fuji-itag-fixes-validation.json), [proof files](../integrations/fuji-itag-live-proof/README.md).

The backend currently serves `http://127.0.0.1:8000`. To display this confirmed result without another swap, open `/?workflow=workflow_329702d0468442d88c8f9789c4eca5c5` and connect using the operator token from `.env`. The tested request took about 266 seconds from PLANNED to CONFIRMED; public RPC/provider changes may safely reject later attempts. Both env files have **100 matching variable names**; the private env contains the actual credentials, the example contains placeholders.

## Cấu hình đã áp dụng

Owner đã cho phép và đã cập nhật trên Fuji: approval TTL **300 giây**, proof-policy snapshot max age **300 giây**. Không thay trần swap, slippage, exposure, session risk hoặc daily risk. Thay policy làm thay active policy hash nên đã tạo session mới; manifest công khai nằm tại `deployments/treasury-fuji-v2.json`.

Các biến sau có trong cả `.env` và `.env.example`; template để trống credentials:

| Biến | Cấu hình demo hiện tại / ý nghĩa |
| --- | --- |
| `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` | Private key trong `.env`; model `deepseek-flash` |
| `PACEVANT_AI_ROTATION_ORDER` | `deepseek,groq,gemini,xingchi` cho planner |
| `PACEVANT_REQUIRE_ITAG` | `1`: mọi workflow cần intent do operator xác thực |
| `PACEVANT_SHIELD_MODE` | `wallet_pipeline`: kiểm tra theo các pha bên dưới |
| `PACEVANT_SHIELD_PROVIDER`, `PACEVANT_SHIELD_API_STYLE` | `deepseek`, `chat_completions`: official DeepSeek API |
| `PACEVANT_SHIELD_MODEL` | `deepseek-flash`, non-thinking |
| `PACEVANT_SHIELD_BASE_URL` | `https://api.deepseek.com` |
| `PACEVANT_SHIELD_API_KEY` | Có thể để trống khi dùng đúng Gemini endpoint; dùng lại `GEMINI_API_KEY` |
| `PACEVANT_SHIELD_FALLBACKS` | `groq,xingchi`; dùng credentials hiện có, ghi trace thực tế |
| `PACEVANT_SHIELD_REASONING_EFFORT` | Để trống cho Gemini; adapter Xingchi fallback dùng `low` |
| `PACEVANT_SHIELD_TIMEOUT`, `PACEVANT_SHIELD_RETRIES` | `20`, `1`; luôn bị chặn bởi thời gian còn lại của candidate |
| `PACEVANT_SHIELD_MAX_REPLANS` | `0` cho demo một yêu cầu xác định |
| `PACEVANT_SHIELD_MAX_OUTPUT_CHARS`, `PACEVANT_SHIELD_CONTEXT_CHARS` | `65536`, `100000`; vượt budget thì từ chối, không cắt đuôi |
| `FUJI_RPC_URL` | `https://avalanche-fuji-c-chain-rpc.publicnode.com`: source chain/control reads |
| `PACEVANT_FUJI_VERIFICATION_RPC` | Cùng endpoint PublicNode; là phép đối chiếu riêng, **không phải nhà cung cấp RPC độc lập** |
| `TREASURY_FUJI_FORK_RPC_URL` | `https://api.avax-test.network/ext/bc/C/rpc`: Anvil cold-fork reads |
| `TREASURY_APPROVAL_TTL_SECONDS`, `TREASURY_MAX_ORACLE_AGE_SECONDS` | `300`, `300`; phải khớp cấu hình owner trên chain |

Gemini 3.1 Flash-Lite có free tier theo [bảng giá Google](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite). Quota thực phụ thuộc tài khoản; không thể bảo đảm API miễn phí luôn sẵn sàng hoặc không bao giờ 429. Provider rotation chỉ dùng endpoint được cấu hình, không tạo thêm tài khoản hay lách quota. Planner có quota/cache riêng; Shield có timeout, giới hạn số call và cooldown khi 429. Khi mọi provider lỗi, hệ thống fail closed, không dùng đáp án giả.

## Luồng xử lý hiện tại

```mermaid
sequenceDiagram
    actor O as Operator / dashboard
    participant API as FastAPI
    participant AI as Planner + Task Shield
    participant T as ITAG / SQLite
    participant E as Execution + Anvil fork
    participant P as Chainlink / Risk / Proof / SDE
    participant S as Attestor
    participant F as Fuji PolicyVault + LFJ
    O->>API: Goal + operator token
    API->>T: ONE_SHOT_SWAP, exact amount, revision, step
    API->>AI: Extract authenticated goal; inspect proposal and build arguments
    API->>E: Read state, build exact transaction, simulate baseline + stress
    E-->>API: Actual artifacts and observations
    API->>AI: Inspect all untrusted evidence in bounded batches
    API->>T: Deterministic + semantic temporal assessment
    API->>P: Real rounds, economics, SMT obligations, strongest verdict
    P-->>API: APPROVE / REJECT / ESCALATE
    API->>S: Revalidate proof, state, revision, history and reservation
    S-->>API: Signed ApprovalV2
    API->>AI: Inspect execute_approved_swap call
    API->>T: Atomic final revision/history/reservation check
    API->>E: Final deterministic freshness and guarded preflight
    E->>F: Relayer broadcasts exact approved call
    F-->>API: Canonical receipt / actual token deltas
    API->>T: Reconciliation and intent history
```

Trong `wallet_pipeline`, backend chạy một allowlist thao tác dữ liệu cố định: `read_chain_context`, `read_portfolio`, `observe_portfolio`, `build_swap`, `simulate_swap`, `read_simulation_artifact`. Các thao tác này không ký hoặc gửi swap lên Fuji. Output vẫn không tin cậy, được gom và kiểm tra **trước** temporal assessment/SDE/ký. Không thể tạo approval proof khi còn evidence chưa kiểm tra. Proposal và build arguments được kiểm tra riêng trước đó; thao tác tài chính `execute_approved_swap` vẫn có kiểm tra AI riêng trước khi gửi. Model không thể tự chọn tool ngoài allowlist. Mode này là tích hợp vận hành theo pha, không tuyên bố tái lập nguyên trạng thuật toán nghiên cứu; `paper`/`wallet_hardened` vẫn giữ cách kiểm tra từng tool.

Artifact EVM có thể vượt 16.000 ký tự. Semantic view giữ các trường dữ liệu có cấu trúc và toàn bộ chuỗi văn bản/unknown keys trong trace; opaque hex bytes được mô tả bằng độ dài và SHA-256. Không cắt đuôi văn bản. VM trace có hash toàn bộ sanitized content, contract addresses và số object. AI kiểm tra semantic view, **không đọc đầy đủ từng byte VM**. Raw artifact đầy đủ vẫn là nguồn kiểm tra hash/proof/effects/receipt và được lưu ở execution data; hash commitment không chứng minh AI đã hiểu bytes. Không dùng semantic view làm bằng chứng thay thế mô phỏng hoặc on-chain verification.

Amounts `*_base_units` là số nguyên: USDC 6 decimals, WAVAX 18 decimals. Ví dụ `1` USDC base unit = `0.000001 USDC`. Planner rationale mô tả đúng amount/direction/recipient, không dùng chỉ thị “rebalance” rộng hơn goal. Model nhận schema đơn vị; independent amount/direction validation vẫn bắt buộc.

## Chạy trên máy hiện tại

```powershell
uv sync --locked
uv run --locked treasury doctor --network fuji --live
# Một workflow nhỏ, tự chọn amount từ quote/balance/exposure; không tự deploy/renew
uv run --locked treasury fuji-demo
# Hoặc giữ API và giao diện chạy
uv run --locked treasury serve --network fuji
# Khi API đã chạy, chỉ gửi demo qua API đó
uv run --locked treasury demo --network fuji --goal "Buy WAVAX with 0.000001 USDC"
```

Dashboard: `http://127.0.0.1:8000`, viewer: `/itag`, health: `/health`. Nhập operator token từ `.env`; không cần nối Core để thực thi treasury demo. Hệ thống dùng attestor để ký approval, relayer trả gas, tài sản swap nằm trong vault. Owner dùng để quản trị policy/session, không đi vào backend phục vụ request. Demo User vẫn dự phòng, chưa phải luồng đăng ký/deposit user riêng.

Frontend tạo ONE_SHOT_SWAP với min=max=exact amount từ validated proposal, rồi gửi workflow kèm spec/revision/step. Refresh trang không tự gửi swap. Mỗi lần bấm chạy là yêu cầu mới; không bấm lặp khi chưa rõ receipt. Intent hoàn tất không được dùng lại để ký giao dịch thứ hai.

Session có thời hạn độc lập với TTL 300 giây. Nếu hết session:

```powershell
# Giao dịch owner thật; gia hạn quyền phiên, không reset daily/global counters
uv run --locked treasury renew-session --network fuji
# Restart backend để nạp mandate/session mới
uv run --locked treasury serve --network fuji
```

`renew-policy` chỉ dùng khi chủ động đổi policy. Không chạy lại owner writes chỉ vì bước đọc RPC cuối bị timeout: kiểm tra receipt trong `owner_renewals` của manifest trước. Không xóa journal hay DB để vượt budget/replay.

## Dữ liệu thật và giới hạn demo

| Phần | Nguồn / phạm vi |
| --- | --- |
| Goal parsing / Shield / semantic ITAG | API model thật khi chạy FUJI; provider/model/status/latency trace có trong audit |
| Balance, policy, session, nonce, pool quote | Public Fuji RPC, pinned block/hash được đối soát |
| Oracle ký proof | Round Chainlink thật trên Fuji; USD cho test token là reference valuation theo owner policy |
| Baseline | EVM execution trên fork state Fuji, không phải giao dịch đã xảy ra trên public chain |
| Stress | Kịch bản giả định có external actor funding/override **chỉ trong Anvil cô lập** |
| Proof | Z3 trên mô hình hữu hạn và concrete evidence; không phải audit toàn bộ protocol |
| Swap / receipt | Chỉ khi CONFIRMED mới được coi đã thực hiện trên public Fuji |
| MOCK / LOCAL tests | Fixture/scripted AI hoặc mock contracts được đánh dấu; không là bằng chứng AI accuracy/live Fuji |
| Lợi nhuận | Không chứng minh lợi nhuận tiền thật, redeem USD hoặc khả năng sinh lời mainnet |

Per-feed round age vẫn AVAX ≤600s, USDC ≤86400s; snapshot policy 300s không biến feed thành giá cập nhật tức thì. Drift vẫn ≤120 blocks. Pinned/latest round hoặc chain state thay đổi có thể yêu cầu chạy lại từ evidence mới, không dùng lại approval cũ. RPC reader lifetime 600s chỉ là transport budget; không nới TTL approval. RPC fallback/fork source phải cùng chain và đúng pinned block hash.

PolicyVault kiểm tra vi phạm ngay trong transaction: revert làm rollback thay đổi token/state của transaction đó và vẫn tiêu tốn gas. Hệ thống không thể “hoàn tác” một swap đã CONFIRMED; trường hợp biết sai trước khi gửi thì chặn ở backend. Negative `eth_call` chứng minh EVM từ chối nhưng không tạo failed transaction công khai.

Kết quả live và test của bản này được ghi riêng trong `docs/integrations/fuji-itag-live-validation.json` khi có bằng chứng kiểm chứng được. Giao dịch cũ không có ITAG không được dùng thay cho kết quả của pipeline mới.


## Actual test funding

The next smallest possible USDC swap (1 base unit) was blocked by the unchanged 25% exposure limit after the earlier trade. To continue the DeepSeek validation, the owner purchased 526 base units Circle test USDC with 0.007 test AVAX through LFJ and deposited those tokens into the vault. This is a real testnet funding operation, not an AI-authorized treasury swap and not a changed risk cap. [Funding receipts](../integrations/fuji-deepseek-demo-funding.json) are kept separately from the protected workflow receipt. Additional repeated demos can require further real test-token funding; the backend never fabricates balances or silently widens exposure limits.


## CLI round freshness preparation

Before creating a Fuji ITAG intent, the CLI checks that real Chainlink rounds have at least the configured approval TTL of remaining per-feed freshness. If the remaining window is too short, it waits for a new round for at most 300 seconds, polling at most once per 15 seconds. The approval window starts after this preparation. No timestamp is restamped and no oracle/risk limit is widened. A round update during an already-running workflow can still invalidate its pinned proof; that workflow must fail closed and any signed/unknown outcome must be checked before retrying. The HTTP API keeps its normal immediate validation behavior; this waiting step belongs to operator demo preparation.


## Signing-path RPC scope

PRE/revalidation snapshots still collect and verify actual balances, asset identities, policy, block/hash and history. The workflow reads authoritative pinned/latest Chainlink rounds separately for risk and proof. PRE/revalidation therefore omit duplicate dashboard-only oracle observations (Witnet/Pyth/reference feeds); interactive treasury/dashboard observations still collect those reference sources. This reduces RPC latency while preserving the 120-block drift cap, 300-second policy/TTL, and all dedicated Chainlink checks. Drift/age rejection now reports STALE_REQUIRES_REEVALUATION rather than incorrectly claiming a deployment mismatch.
