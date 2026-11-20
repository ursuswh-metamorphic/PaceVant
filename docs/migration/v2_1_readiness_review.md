# Đối chiếu chức năng V2.1 và phần còn lại trước tích hợp thực tế

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](../AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](../README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

> Đây là review chỉ đọc ở checkpoint trước. [Rà soát mới có chạy tests và sửa lỗi](../audit/V2_1_READINESS_REVIEW.md), [system design hiện tại](../AI_Treasury_Security_System_Design_v2.1.md) được ưu tiên. File design hiện tại mới được viết từ source; design bên ngoài mà plan ban đầu tham chiếu vẫn chưa được cung cấp.

Ngày đối chiếu: 19/11/2026. Chỉ đọc mã, tests và kết quả đã lưu; không chạy lại test, khởi động dịch vụ, gọi RPC hoặc gửi giao dịch trong lượt review này.

## Cơ sở đánh giá

Target tại checkpoint này là [IMPLEMENTATION_PLAN_V1_TO_V2_1.md](../IMPLEMENTATION_PLAN_V1_TO_V2_1.md). Khi đó chưa có file design V2.1 riêng; điều này đã ghi trong [inventory](v2_1_repository_inventory.md). Sau này đã thêm system design as-built từ code hiện tại. Kết luận review này áp dụng cho MVP/release gates của plan được cung cấp, không khẳng định đã đối chiếu bản thiết kế ngoài repository.

**Kết luận:** đủ thành phần của lõi bảo mật proof-gated swap để demo local V2.1; chưa phải toàn bộ tích hợp thực tế/production. Đủ `.env` là readiness cấu hình, không phải bằng chứng đã deploy hoặc mọi thành phần đã kết nối nguồn thật.

## Ma trận hiện trạng

| Thành phần/chức năng | Bằng chứng mã chính | Hiện trạng và giới hạn |
|---|---|---|
| Owner mandate, allowlist, caps, policy/session lifecycle | `backend/src/treasury_backend/core/models.py`, `backend/src/treasury_backend/operations/`, `contracts/src/PolicyVault.sol` | Đã có. Owner deploy/configure/renew; không tự reset global/day counters. Chưa áp dụng lên deployment Fuji V2 |
| Planner/typed intent | `backend/src/treasury_backend/modules/planning/__init__.py` | Có, `rules-v1`, parser cho buy/sell templates. Chưa có LLM API hoặc agent suy luận mở |
| Task Alignment/Shield | `backend/src/treasury_backend/modules/alignment/__init__.py` | Có kiểm tra mandate/recipient/token/chain/slippage và injection patterns. Dùng luật/regex, không phải semantic LLM verifier hoặc chứng minh chống mọi prompt injection |
| Deterministic transaction builder | `backend/src/treasury_backend/modules/execution/transaction/builder.py` | Đã có; exact calldata, policy/deadline/nonce và directional caps |
| Simulation/stress/effect extraction | `backend/src/treasury_backend/modules/execution/simulation/runner.py`, `evidence/extractor.py` | Đã chạy guarded entrypoint thật trên pinned Anvil fork, đọc balances/allowances và fixed stresses. Adapter/token vẫn là mock |
| Economic risk | `backend/src/treasury_backend/modules/risk/__init__.py` | Đã có size/day/slippage/exposure/gas/freshness/value checks. Hiện dùng controlled demo prices, chưa dùng oracle của bạn |
| SMT Check, Phi compiler, SMT Compile, certified debit | `packages/contracts-api/treasury_contracts/proof.py`, `backend/src/treasury_backend/modules/proof` | Đã có Z3/exact arithmetic, typed artifacts, source/query commitments, refusal cho SAT/UNKNOWN/error. Bảo đảm có điều kiện trong modeled price domain |
| SDE duy nhất và immutable approval | `backend/src/treasury_backend/modules/decision`, `storage`, `backend/src/treasury_backend/modules/workflows/service.py` | Đã có; APPROVE cần các gate đạt; revalidation và final compiled-Phi guarded preflight trước ký |
| Attestor/ApprovalV2 | `backend/src/treasury_backend/modules/signing`, shared `v2.py` | Đã có EIP-712 và key riêng, recheck immutable decision. Là module trong A, chưa tách HSM/process signer riêng |
| Relayer và idempotency | `backend/src/treasury_backend/modules/execution/relaying/relayer.py`, `store.py` | Đã có immutable payload checks và raw-tx journal trước broadcast; retry cùng bytes |
| On-chain guard/Phi/budgets/rollback | `contracts/src/PolicyVault.sol` | Đã có nonce/policy/domain checks, two-asset/two-allowance Phi, session/global/day accounting atomic; V2 khóa entrypoint V1. Đã kiểm tra local, chưa deploy Fuji V2 |
| Hai chiều swap | Vault, builder, simulation/risk và V2 tests | Có mã và tests cho cả hai chiều. Cấu hình hiện tại reverse cap bằng 0 nên WAVAX→USDC bị khóa có chủ đích |
| Replan/Experience | `backend/src/treasury_backend/modules/experience/__init__.py`, orchestration | Có history, giảm amount theo rule, tránh lặp amount, tối đa hai replans. Chưa có mô hình học máy/tự học; không cần giả định một learning engine để claim MVP này |
| Outcome monitor/reorg/reconciliation | B relayer monitor, A orchestration/storage | Đã có receipt/actual delta/canonical block/confirmation checks, in-flight reservation và quarantine. Được gọi qua API/polling, không phải dịch vụ observer độc lập |
| Dashboard/audit/persistence | `frontend`, A storage, B store | Đã có timeline, proof/Phi, budget/gas/actual deltas, authenticated API và SQLite/content-addressed artifacts |
| Oracle thực tế | Hiện A đọc oracle JSON; `refresh_oracle()` tạo nguồn demo | **Chờ merge.** Chưa review code của người cộng tác nên chưa xác nhận tương thích |
| DEX/token thật | Hiện `MockSwapAdapter`, `MockUSDC`, `MockWAVAX` | **Chưa tích hợp và không thuộc MVP của implementation plan.** Oracle thật không tự biến adapter thành DEX thật |
| Exposure runtime on-chain | Hiện economic evaluator pre-sign only | **Chưa có; optional trong plan.** Phi không bảo đảm allocation 25% tại inclusion |
| Test/evaluation/CI | `contracts/test`, control/execution/integration tests, evaluation scripts, workflow CI | Có tests và measured local results. Không phải audit độc lập, kiểm chứng formal toàn Solidity hoặc stress/load diện rộng |
| Public Fuji end-to-end | V2 manifest/receipt chưa có | **Chưa kiểm chứng.** Env đã chuẩn bị đủ; normal/protected-revert receipts thật trên Fuji vẫn cần thực hiện ở lượt deploy/test riêng |

## Khi merge oracle thực tế

Oracle không phải một biến `.env` còn thiếu. Đây là tích hợp mã/data contract cần review. Các điểm hiện đang gắn với `TRUSTED_TEST_ORACLE`:

- `backend/src/treasury_backend/modules/oracle/models.py`: `OraclePrice.price_source` là literal nguồn test; giá USDC/WAVAX dùng USD-e8, scope chain/vault và `price_timestamp`.
- `backend/src/treasury_backend/modules/risk/__init__.py`: từ chối source không phải nguồn test hiện tại.
- `backend/src/treasury_backend/modules/proof/__init__.py`: ràng buộc source/hash và chuyển giá sang interval cho proof.
- `backend/src/treasury_backend/operations/`: `owner_config()` commit hash nguồn test; `refresh_oracle()` ghi giá nominal từ env và timestamp demo.
- `backend/src/treasury_backend/modules/workflows/service.py`: A hiện đọc oracle file từ đường dẫn cấu hình, chưa trực tiếp gọi feed/provider thật.

Các điều kiện trước khi đánh dấu oracle đã tích hợp:

1. **Chốt interface:** adapter hoặc API/file contract, chain/vault, asset mapping, source identifier/provenance, giá chuẩn hóa USD-e8 và timestamp cập nhật dữ liệu nguồn. Không mặc định decimals của feed giống decimals token.
2. **Giữ freshness đúng nghĩa:** dùng thời điểm cập nhật giá thực, không thay bằng thời điểm backend vừa đọc/ghi file để làm mới một giá cũ. Lỗi provider, giá không dương, stale/future hoặc sai network phải từ chối ký. Hiện A giữ freshness 60 giây; phải đối chiếu SLA/heartbeat thực tế của oracle trước khi chọn policy phù hợp.
3. **Đồng bộ source/hash:** schema, risk, proof, owner configuration và on-chain policy phải cùng nguồn/hash. Không gắn nhãn test cho dữ liệu thực để né source checks. Nếu đổi policy/source sau deployment thì owner phải cấu hình lại commitment/session cho khớp.
4. **Không để heartbeat demo ghi đè:** khi dùng producer oracle thật, thay/điều chỉnh `refresh_oracle` và service lifecycle; không chạy đồng thời demo writer lên cùng file nguồn thật.
5. **Đồng bộ mô hình demo:** quote adapter hiện neo nominal 20 USD/WAVAX, portfolio khởi tạo cũng dựa trên 1/20. Đưa giá thị trường vào mà không xem lại quote/balances có thể khiến exposure/slippage/value gate từ chối hợp lệ. Chọn rõ demo vẫn mock hay tích hợp adapter khác; không tắt gate để buộc pass.
6. **Kiểm tra end-to-end:** normal, nguồn sai, stale/future, sai decimals, mất kết nối, giá thay đổi trước ký và binding oracle/proof/policy; sau đó mới xác nhận Fuji integration. Các test này chưa được chạy với oracle của người cộng tác.

Nếu oracle mới yêu cầu feed address/provider URL/API key, chỉ có thể kết luận tên biến cụ thể sau khi xem interface/code đó. Không cần thêm speculative env placeholders ngay lúc này.

## Việc còn lại theo mục tiêu

- **Demo bảo mật V2.1 với mock assets:** code lõi có sẵn; chọn có bật reverse cap hay không, deploy V2 Fuji và xác nhận normal/revert/receipt thật khi người dùng muốn chạy.
- **Demo với oracle của người cộng tác:** merge theo các điều kiện phía trên và chạy regression cho nguồn thật. Đây là phần tích hợp đang chờ, không phải thay toàn bộ hệ thống.
- **AI planner dùng LLM thật:** là phần chưa có; cần adapter/provider/typed-output validation nếu đó là yêu cầu của bản thiết kế ngoài repository. LLM không được có private key hoặc bỏ qua các deterministic gates.
- **Giao dịch DEX/tài sản thật hoặc production:** cần scope, adapter/simulation/token/oracle review, signer isolation/operations và security audit riêng; không nằm trong tuyên bố đã hoàn thành MVP hiện tại.

Kết quả lần kiểm thử đã ghi nhận trước review này: root Python **84 passed**, execution Python **46 passed / 1 opt-in skipped**, Forge **49 passed**; có full-protocol local benchmark 14 records và four-mode guard ablation riêng. Xem [progress](v2_1_progress.md), [full-protocol report](../evaluation/full_protocol_results.md), [policy coverage](../security/policy_coverage_v2_1.md). Đây là kết quả các lần chạy trước, không phải test vừa được chạy trong lượt đối chiếu này.
