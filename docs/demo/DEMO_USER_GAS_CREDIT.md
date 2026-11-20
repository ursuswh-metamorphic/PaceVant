# Demo User và gas credit — thiết kế, API và cách demo

Phiên bản sau checkpoint `3fba479`, ngày 20/11/2026. Đây là bổ sung cho [system design V2.1](../AI_Treasury_Security_System_Design_v2.1.md); giữ một Python/FastAPI backend, Solidity/ABI/proof engine và toàn bộ pipeline bảo mật hiện có. Không cần contract mới, WalletConnect, Paymaster hoặc thêm API server.

## 1. Người dùng sử dụng gì?

Ban giám khảo chỉ chọn **PaceVant - Demo User** rồi bấm chạy với goal mẫu đã điền sẵn, hoặc chỉnh goal nếu muốn. Không nhập mã/token, không Connect Wallet. Website gọi `POST /v1/demo/select` để tự nhận quyền chỉ dành cho demo, giữ trong bộ nhớ tab. Chỉ có một tài khoản dùng chung; khi bật demo, người truy cập website đều có thể chọn tài khoản và cùng chia sẻ hạn mức đã cấp. Đây chưa phải hệ thống đăng nhập/ownership theo ví hoặc multi-user production.

Địa chỉ từ private `.env`: `0xf23bE4A69B162DdC0F7D5456172212d294b233c7`. Đã đối chiếu key/address nhưng không công bố key. Private key Demo User **không dùng** để đăng nhập, ký swap, trả gas hoặc được forward vào runtime/frontend.

Token swap vẫn nằm ở **treasury vault**, không lấy từ ví Demo User. Ví này là identity của tài khoản demo và để hiển thị số dư AVAX thực. Người dùng không thay recipient/router/token/mandate bằng request. Adapter chỉ cho bounded USDC → WAVAX exact amount, tạo one-shot ITAG intent rồi gọi cùng `ControlPlane.run`.

## 2. Ba ngân sách khác nhau

| Loại | Nguồn / mục đích | Có tự chuyển tiền on-chain? |
| --- | --- | --- |
| AVAX thực của Demo User | Đọc RPC tại địa chỉ Demo User; chỉ hiển thị | Không; không bị trừ để trả gas |
| Gas credit Demo User | Sponsor cấp một hạn mức off-chain trong SQLite, định danh bằng wei; ghi nợ phí relayer đã trả | Không; chưa phải tiền khách hàng đã nạp hoặc claim rút AVAX |
| Certified risk / session / daily spend | Các guard của treasury và vault hiện tại | Giữ nguyên semantics, không dùng gas credit thay thế |

Relayer trả gas thật trên chain. Không có ERC20 transfer hoặc AVAX transfer mỗi lần ghi credit/debit. Mô hình prepaid-style demo này mô phỏng **cấp ngân sách nội bộ**, còn phí gas lấy từ receipt thật; chưa tích hợp việc thu tiền/nạp prepaid từ khách hàng. UI ghi rõ điều này, không gọi credit là số dư ví.

## 3. Luồng và ranh giới trách nhiệm

```mermaid
sequenceDiagram
  actor U as Ban giám khảo
  participant UI as Browser
  participant D as Scoped demo API
  participant C as Existing ControlPlane
  participant X as Existing ExecutionService / Relayer
  participant DB as Existing execution SQLite + gas ledger
  participant F as Public Fuji Vault / LFJ
  participant M as Existing outcome monitor
  U->>UI: Chọn Demo User, không nhập mã
  UI->>D: POST select, account_id=demo
  D-->>UI: Tự cấp scoped session, không trả server secret
  UI->>D: GET account / treasury (demo Bearer)
  D-->>UI: Wallet AVAX riêng, gas credit, history
  U->>UI: Goal swap chính xác
  UI->>D: POST goal + Idempotency-Key
  D->>DB: Durable request ID -> workflow ID (một lần)
  D->>C: Authenticate exact one-shot ITAG terms; run workflow
  Note over C,X: Planner, Shield, ITAG, builder, Anvil stress, oracle, risk, Z3, SDE, revalidation và attestor giữ nguyên
  C->>X: Exact signed PDR + build
  X->>X: Verify all gates, estimateGas và chọn gasPrice
  X->>DB: Atomic reserve gasLimit*gasPrice + raw send journal
  alt Thiếu credit / relayer AVAX / vượt fee cap
    DB-->>X: Refuse, rollback journal/hold
    X-->>C: FAILED_TO_SUBMIT; không broadcast
  else Ngân sách đủ và journal committed
    X->>F: Broadcast cùng signed bytes một lần
    F-->>M: Receipt / canonical block / actual gas
    M->>DB: Idempotent settlement hoặc giữ pending/reorg hold
    DB-->>UI: Debit thực tế + phần giữ chỗ đã giải phóng
  end
```

Chữ ký treasurer vẫn do attestor tạo sau approval đã lưu. Demo credential chỉ vào các endpoint hẹp; không được gọi operator `/v1/workflows/start`, internal `/v1/approvals/attest`, execution `/execution/...` hay xem workflow người quản trị không thuộc demo. Operator flow cũ vẫn còn ở mục quản trị.

## 4. Input/output từng phần bổ sung

| Thành phần | Input | Output / hành vi |
| --- | --- | --- |
| `config/demo.py` | Enabled, public wallet address, scoped token, initial credit/fee cap | Validated DemoSettings; token không có trong repr; flag/budget sai fail startup |
| `api/demo.py` / `demo_auth.py` | Public account selection, sau đó session Bearer + goal + Idempotency-Key | Tự cấp HMAC-signed demo session 24 giờ; authenticated exact ITAG intent, stable workflow ID và full pipeline; không nhận arbitrary calldata/signature |
| `modules/gas_credit` | Request/build binding; signed tx max cost; verified reconciliation report | Durable reservation, actual debit, reorg reversal/hold và account/history DTO |
| `LocalExecutionSDK` / `ExecutionService.build` | Trusted workflow identity + build result | Bind billing vào build của request demo; không đổi wire/signature schema |
| `Relayer` hook | Build đã bind, actual estimateGas/gasPrice, relayer pending balance | Reserve + send journal trong cùng DB transaction; không gửi nếu thiếu tiền |
| `OutcomeMonitor.fee_observer` | Report của shared outcome verifier + reorg invalidation | Charge/reverse/hold; không ký, không gửi hoặc tạo giao dịch mới |
| `frontend/src/features/demo` | Public account/fees/history + tab request ID | Wallet vs credit tách biệt, actual fee equation, explorer/workflow links, GET-only resume |

## 5. Accounting và xử lý lỗi

```text
maximum_reserved_wei = signed_tx.gasLimit * signed_tx.gasPrice
actual_fee_wei       = receipt.gasUsed * receipt.effectiveGasPrice
available_credit    = allocated_credit - sum(current_settled_fees) - sum(active_maximum_holds)
```

Tiền lưu integer wei dạng decimal strings; không dùng float. `BEGIN IMMEDIATE` serialize reservations và settlement. `tx_hash`/`build_id` có uniqueness; ledger events append-only. Credit và raw journal cùng commit trước broadcast, nên không có send thành công nhưng chưa giữ ngân sách do lỗi insert journal.

| Tình huống | Gas credit và hành động |
| --- | --- |
| Policy/Shield/ITAG/risk/proof từ chối trước gửi | Không charge gas on-chain; history ghi workflow bị chặn |
| Chưa có credit ngay từ request | Refuse trước model/fork calls |
| Credit còn nhưng không đủ maximum của signed tx | Refuse tại relayer, không broadcast, không ghi debit/hold dở dang |
| Fee vượt per-transaction cap hoặc relayer thiếu AVAX | Cũng refuse; không tự nâng cap, mua AVAX hay chuyển từ owner |
| PENDING / unknown broadcast / RPC unavailable | Giữ maximum hold, không ghi phí 0 và không tự retry/rebroadcast |
| Receipt đủ confirmations, success | Trừ actual fee một lần, giải phóng phần reserve thừa |
| Receipt đủ confirmations, revert | Vẫn trừ actual gas một lần; token swap rollback, gas không hoàn lại |
| Effects mismatch nhưng gas identity đã xác minh | Có thể charge gas đã trả; không biến kết quả security mismatch thành success |
| Reorg | Reverse charge cũ bằng event mới, giữ lại maximum trong REORG_HOLD; re-inclusion verified thì settle lại |
| Đọc/poll lặp hoặc restart | Cùng tx/receipt không bị trừ thêm; đổi initial-credit env không tự top-up |
| HTTP timeout / browser reload | Giữ request ID, dùng GET kiểm tra cùng workflow; không POST mới tự động |
| Crash trước khi tạo control workflow | Durable request có thể ở STARTING_OR_REVIEW_REQUIRED; cần operator kiểm tra journal/state; không tự khởi chạy lại |

Sau deep reorg, nếu các giao dịch sau đã dùng phần headroom giải phóng trước đó, credit khả dụng có thể âm và hệ thống chặn gửi mới. Không xóa DB/journal để gỡ hold. Chưa có auto refund/top-up/payment integration hay cơ chế tự kết luận dropped transaction để giải phóng ngân sách; đây là giới hạn bảo thủ có chủ đích.

## 6. API

| Method / path | Auth | Input / output |
| --- | --- | --- |
| `GET /v1/demo/config` | Public | Enabled và một public account; không có token/private key/budget history |
| `POST /v1/demo/select` | Public khi demo enabled | `{ "account_id": "demo" }` → demo-only session tự động; không tạo intent, workflow, hold hay giao dịch |
| `GET /v1/demo/account` | Demo Bearer | Wallet address, nullable actual AVAX balance/status, allocated/spent/reserved/available wei, txs/ledger/request history |
| `GET /v1/demo/treasury` | Demo Bearer | Existing treasury view của đúng mandate/vault; không đổi quyền owner |
| `POST /v1/demo/workflows` | Demo Bearer + `Idempotency-Key` | `{ "goal": "Buy WAVAX with 0.000001 USDC" }` → existing workflow result |
| `GET /v1/demo/requests/{key}` | Demo Bearer | Stable workflow cho request ID đã tiếp nhận; đọc lại không khởi chạy |
| `GET /v1/demo/workflows/{workflow_id}` | Demo Bearer | Workflow do demo sở hữu; workflow khác trả not found |

Bearer demo được cấp tự động, có HMAC signature, scope cố định `demo` và expiry 24 giờ; không dùng được như operator/internal/execution credential. Hết hạn hoặc reload có thể chọn lại account, không phải nhập gì và không reset credit. `PACEVANT_DEMO_ACCESS_TOKEN` nay chỉ là server signing secret, không gửi cho giám khảo/browser và không chấp nhận nó như Bearer trực tiếp. CORS chỉ cho explicit origins; sessionStorage chỉ lưu random request ID, credential chỉ ở tab memory. UI chặn submit tiếp khi còn request chưa rõ kết quả. Chỉ khi GET xác nhận `DEMO_REQUEST_NOT_FOUND` mới có thể bỏ ID chưa được tiếp nhận. Mọi người chọn demo cùng chia sẻ ngân sách/lịch sử; không dùng cho multi-user thật.

## 7. Env và lưu trữ

Đã bổ sung bốn tên biến vào `.env`, `.env.example` và env initializer; cùng hai biến Demo User đã có trước đó:

| Biến | Cấu hình local hiện đặt / ý nghĩa |
| --- | --- |
| `PACEVANT_DEMO_ENABLED` | `1` trong private env, `0` trong template; opt-in |
| `PACEVANT_DEMO_ACCESS_TOKEN` | Server-only secret ký session tự cấp; giữ giá trị hiện có trong `.env`, template trống. Không đưa cho giám khảo và không điền lên website |
| `PACEVANT_DEMO_INITIAL_CREDIT_WEI` | `1000000000000000` = **0,001 AVAX** allowance lúc khởi tạo ledger lần đầu |
| `PACEVANT_DEMO_MAX_TX_FEE_WEI` | `100000000000000` = **0,0001 AVAX** maximum reserve cho một giao dịch |
| `TREASURY_DEMO_USER_ADDRESS` | Public demo identity nêu ở mục 1 |
| `TREASURY_DEMO_USER_PRIVATE_KEY` | Giữ riêng trong `.env`, không dùng/forward; không cần cho runtime của flow mới |

Hai env root khớp **104 tên biến**. Không hardcode key/token vào JS. Runtime cần `require_itag=1`, Shield `wallet_pipeline` hoặc `wallet_hardened`, LOCAL/FUJI execution và demo token khác ba service tokens; thiếu các điều kiện này thì không bật demo. `doctor` kiểm thêm cấu hình demo, không coi presence của key hay credit allocation là bằng chứng có tiền nạp thật.

Ledger nằm trong `.execution-data-fuji-v2/state.sqlite3` cùng execution records, thêm năm bảng `demo_*`; không tạo database server/service mới. Control DB vẫn giữ workflow/ITAG/Shield/proof/history cũ. Cần backup nhất quán cả hai DB/artifacts/journals. Không thay identity/chain/vault/relayer của ledger đã khởi tạo một cách âm thầm.

## 8. Tiết kiệm gas và cách demo

Chỉ swap được broadcast sau đủ mọi gate. Tạo/chọn account, cấp credit nội bộ, tạo intent, model, proof, Anvil, GET history và settlement **không tạo giao dịch phụ trên public chain**. Relayer dùng `estimateGas` thực, margin **10% + 5.000 gas** cho demo thay vì fixed limit lớn; gasPrice lấy RPC và maximum phải nằm trong credit/cap. Gas limit là trần thực thi, không phải toàn bộ phí bị trừ. Không hạ limit dưới estimate để cố giảm phí, không tự fee-bump hoặc gửi lại khi timeout.

Không thể cam kết 0,05 AVAX chạy được bao nhiêu lượt vì gas price, execution path, source freshness và thanh khoản thay đổi. Allowance 0,001 AVAX chỉ là một phần ngân sách; relayer vẫn phải có AVAX thật. User/vault risk budgets và exposure còn quyết định có được swap hay không.

1. Restart backend để nạp code/env mới. Nếu đang giữ một backend cũ ở cổng 8000, dừng nó trước rồi chạy:

   ```powershell
   uv run --locked treasury doctor --network fuji
   uv run --locked treasury serve --network fuji
   ```

2. Mở `http://127.0.0.1:8000`, bấm **Chọn Demo User**. Không nhập token/mã/private key. Goal mẫu đã có sẵn. Chọn tài khoản không tự gửi swap.
3. Kiểm tra hai dòng độc lập **AVAX thực trong ví** và **gas credit khả dụng/giữ chỗ/đã trừ**. Tài khoản chưa có receipt sẽ ghi chưa có phí xác minh, không tạo phí mẫu.
4. Khi thực sự muốn gửi giao dịch demo, nhập `Buy WAVAX with 0.000001 USDC` rồi chạy một lần. Theo dõi timeline cũ đầy đủ, tx hash/explorer và phí thực tế. Trong đợt triển khai này agent **không bấm gửi Fuji**.
5. Nếu pending/timeout, dùng **Kiểm tra yêu cầu đã gửi**; đây là GET-only. Không bấm/gửi goal mới để xử lý giao dịch chưa rõ.
6. Nếu hết session, stale feed hoặc thiếu USDC/exposure headroom, giải quyết đúng điều kiện đó. Gas credit không nới policy. Trạng thái cuối của audit trước tính năng này cho biết vault cần thêm Circle test USDC; xem [báo cáo có số dư và hướng dẫn nạp](../audit/SYSTEM_SECURITY_REAL_DATA_REVIEW.md). Không coi thông tin cũ là số dư được refresh trong đợt này.

## 9. Phạm vi kiểm chứng

Bổ sung thao tác chọn account không nhập mã có [report kiểm chứng riêng](../audit/demo-account-selection-validation.json): offline session/auth/API/ledger/architecture tests và syntax frontend. Không chạy swap hoặc tạo giao dịch trong đợt thay đổi thao tác chọn tài khoản; cần restart backend đang chạy bản cũ và reload website để nạp code mới.

Tests sổ cái dùng các verifier facts dựng rõ trong fixture để kiểm concurrency, reservation rollback, receipt scope, pending/revert/reorg/dedup/restart. Test integration chạy **Anvil thật trên chain 31337** với contracts V2, Shield replies scripted có nhãn test và cùng pipeline ITAG/proof/sign/execute/monitor. Các API adapters được kiểm auth, same-key replay và no-broadcast khi thiếu credit hoặc fee cap quá thấp. Kiểm syntax frontend riêng.

Không gửi public Fuji transaction để kiểm tính năng mới theo yêu cầu. Receipt Fuji trong audit cũ chứng minh pipeline trước bổ sung Demo User, **không được đổi nhãn thành receipt Demo User có prepaid billing**. Browser visual verification có phạm vi riêng và không thay test API/EVM. Xem [kết quả triển khai](../audit/demo-user-gas-credit-validation.json) để biết những gì đã thực sự chạy.
