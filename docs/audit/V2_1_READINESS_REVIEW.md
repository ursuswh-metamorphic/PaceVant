# Rà soát toàn hệ thống V2.1 — 19/11/2026

> **Báo cáo lịch sử:** kết luận không có oracle/DEX/LLM/public Fuji bên dưới thuộc checkpoint 19/11. Xem [rà soát source, security và dữ liệu thực hiện tại](SYSTEM_SECURITY_REAL_DATA_REVIEW.md) cùng bằng chứng được liên kết trong đó cho phiên bản sau tích hợp main, Shield và ITAG.

> Checkpoint trước tích hợp Groq. Sau đó có bounded real Groq planner, thay ba cặp ví theo user và sync env; xem [integration guide](../integrations/GROQ_PLANNER_AND_ENV.md). Các số tests/env-preservation và missing-LLM nhận xét trong báo cáo này mô tả checkpoint ban đầu, không phải trạng thái sau cập nhật đó.

Đọc [system design hiện tại](../AI_Treasury_Security_System_Design_v2.1.md) để hiểu kiến trúc, từng module, dữ liệu, luồng xử lý, quyền và vận hành. Báo cáo này ghi đối chiếu yêu cầu, lỗi đã sửa, kiểm chứng và phần chưa hoàn thành. [Evidence tóm tắt dạng JSON](validation-summary.json) không chứa private keys, tokens hoặc RPC credentials.

## Kết luận

**Lõi proof-gated treasury V2.1 đã chạy end-to-end trên LOCAL, nhưng chưa đạt toàn bộ điều kiện phát hành/thực tế của implementation plan.** Không có bằng chứng deployment V2, normal swap hoặc protected revert trên public Fuji; chưa build/run Docker image hoặc hosted backend. Oracle thị trường, DEX và planner LLM chưa được tích hợp.

Phạm vi đối chiếu là [implementation plan được cung cấp](../IMPLEMENTATION_PLAN_V1_TO_V2_1.md), source, tests, cấu hình và docs trong working tree. Bản design V2.1 bên ngoài mà plan từng tham chiếu chưa được cung cấp; file system design mới được viết từ code hiện tại, không được dùng để tự chứng minh đã đáp ứng một thiết kế bên ngoài.

Checkpoint trước refactor là `19aa935`; nhánh hiện tại `refactor/modular-backend-frontend`. Các thay đổi module/gộp API và sửa lỗi lần này còn trong working tree, chưa commit thêm. Kết luận áp dụng cho working tree đã kiểm tra; không phải xác nhận đã đồng bộ với mọi remote branch, dependency mới nhất hoặc security audit độc lập.

## 1. Đối chiếu thành phần và release gates

| Yêu cầu | Source/kiểm chứng | Trạng thái |
| --- | --- | --- |
| Một SDE và immutable approval record | `modules/decision`, `modules/persistence`, `modules/workflows/authorization.py`; control tests | Có; attestor nhận decision ID, không nhận arbitrary signed payload |
| Planner và alignment | `modules/planning`, `modules/alignment` | Có parser/template/regex; không phải agent LLM hoặc semantic verifier tổng quát |
| Exact build, simulation, stress, effects | `modules/execution/{transaction,simulation,evidence}`; execution integration tests | Có EVM fork thật, pinned block, bounded stress; token/adapter mock |
| Economic eligibility | `modules/{portfolio,risk}`; control gate tests | Có; exposure kiểm trước ký, execution-cost gate là estimate; chưa phải runtime exposure guard |
| Check/Compile/risk bound | Shared `treasury_contracts/proof.py`, `v2.py`; backend proof adapter và exact-arithmetic tests | Có SAT/UNSAT/UNKNOWN handling, feasibility checks, source-bound artifacts, canonical Phi/debit |
| ApprovalV2 / signed bindings | `modules/signing`, shared V2 codecs, Solidity tests, viem vectors | Có; chain/vault/policy/session/calldata/Phi/nonce/expiry được bind và kiểm tra |
| Vault enforcement | `contracts/src/PolicyVault.sol`; 49 Forge tests | Có atomic postconditions, allowance cleanup, rollback, daily/session/global counters, reverse cap |
| Monitor / pending / receipt / reorg | `modules/workflows/monitoring.py`, `execution/relaying`; integration tests | Có reconcile khi polling; chưa có background watcher/automatic fee replacement |
| UI proof/session/budgets | `frontend/src/features`; actual LOCAL Chrome flow | Có proof/obligations/Phi/debit và chain counters; protected revert hiển thị trong workflow REVERTED |
| Persistence/recovery | SQLite, immutable records, raw tx journal; regression tests mới | Có; đã sửa quarantine dedup và recovery helper sau gộp API |
| Oracle merge point | `modules/oracle`, `operations/services.py` | Có JSON provider/external writer mode; chưa có nguồn thị trường thực |
| Deploy/serve | `operations`, root Dockerfile, frontend Dockerfile, Compose | Có code/config/runbook; chưa có actual image/host/Fuji smoke evidence |
| PGS reference không thành runtime dependency | `.gitignore`, architecture/import scan | Folder reference chỉ đọc, ignored/untracked; không import hoặc cần nó để chạy backend |

Đường dẫn module ở bảng tương đối với `backend/src/treasury_backend` trừ nơi ghi rõ khác. Interfaces/ownership đầy đủ: [MODULES.md](../../backend/MODULES.md) và README ngay trong từng module.

| Gate của plan | Đánh giá hiện tại |
| --- | --- |
| A — Baseline/migration discipline | Có checkpoint, inventory, baseline/evaluation và giữ các invariants; không duplicate engine. Refactor có thay đổi layout/process được ghi rõ, không mô tả là diff nhỏ tuyệt đối |
| B — Formal correctness | Đạt các local tests trong mô hình hai tài sản, independent price bands và assumption đã công bố; không chứng minh oracle trung thực hoặc mọi hành vi DEX |
| C — Signing/on-chain | Đạt local tests và V1/V2 golden vectors; V2 vault vô hiệu V1 path. Owner vẫn là trust root. Signer cùng process với relayer theo yêu cầu gộp backend |
| D — End-to-end/resilience | LOCAL đạt. Fuji normal/revert receipt và CI fresh clone/image từ working tree này chưa được xác nhận; gate chưa complete toàn bộ |
| E — Evaluation/honest claims | Có bounded local ablation, proof sweep và full-protocol evidence trước đó. Chưa có full-protocol B/C throughput hoặc bằng chứng performance trên public Fuji/hosting |

Các khác biệt có chủ đích với pseudo-layout trong plan: một FastAPI thay hai server; signer không còn cách ly process; một `PROVED` event chứa ba nghĩa vụ; session views đọc trực tiếp chain thay vì SQL risk ledger authoritative; unified execution routes có prefix `/execution`. Những khác biệt này được công bố, không âm thầm coi là giữ nguyên mọi giả định thiết kế.

## 2. Code mới, code tương thích và entrypoints

Canonical runtime là `api/app.py:create_app` → `ControlPlane` với injected `VerifiedExecutionClient(LocalExecutionSDK)` → cùng một `ExecutionService`. Chỉ có một Uvicorn/API port. Giao tiếp control–execution dùng method calls, không mở HTTP nội bộ. App/container/operator không khởi động standalone B server.

Code tại `apps/control-plane/app`, `apps/execution-plane/app`, `apps/dashboard` đã được chuyển sang `backend/` và `frontend/`; runtime không import namespace `app` cũ. Shared proof engine chỉ có một bản trong protocol SDK, không có proof engine thứ hai trong mỗi module.

**Vẫn có code tương thích V1 được giữ có chủ đích:**

| Phần giữ lại | Vì sao / có nằm trong V2 mặc định không? |
| --- | --- |
| V1 DTO, hash/signature branch, frozen standalone OpenAPI | Giữ consumer contract, golden vectors và baseline tests. V2-enabled vault từ chối V1 execution |
| `api/serve_control.py`, standalone execution factory/CLI, `RestExecutionClient` | Test consumer legacy và benchmark; canonical app inject direct adapter, không dùng transport này |
| `scripts/*.py` | Shims trỏ về module/tool mới, không phải một backend implementation khác |
| `b:*` npm aliases | Được ghi rõ là B-only compatibility; không phải full-system V2 commands |
| `workflows/mock.py`, `fixtures/mock` | MOCK UI V1 không cần chain; không phải proof V2.1 |
| Baseline archive trong evaluation tool | So sánh với original commit; không import source cũ để phục vụ API hiện tại |
| Docs A/B, PoC và migration chronology | Lịch sử/compatibility; không dùng làm hướng dẫn deploy hiện tại |

Rà soát này phát hiện các npm alias phổ thông còn gọi B-only CLI. Đã chuyển `dev`, `local`, `dev:local`, `dev:fuji`, `demo`, `deploy:*` sang canonical app/operator; test architecture chặn hồi quy. `dev` là MOCK; `local`/`dev:local` chạy full LOCAL; `demo` gọi LOCAL API đã bật. `b:*` giữ explicit legacy behavior. CLI Python `uv run --locked treasury ...` vẫn là cách vận hành chính, không cần npm.

Không có tuyên bố “đã xóa mọi dòng code V1”: làm vậy sẽ phá compatibility và benchmark. Mục tiêu đạt được là đường chạy V2 mặc định không vô tình dùng entrypoint cũ hoặc hạ cấp qua V1.

## 3. Toàn bộ dữ liệu mock và giới hạn chạy thật

| Nguồn | Hiện trạng | Ảnh hưởng |
| --- | --- | --- |
| MOCK execution client | Địa chỉ/block/bytecode/calldata placeholder, số dư và receipt/hash/gas fixture | Chỉ xem UI và các gate V1; không có EVM/proof/Phi/session V2.1 |
| Demo oracle | Giá danh nghĩa USDC=1 USD, WAVAX=20 USD từ cấu hình; heartbeat tạo timestamp mới sau kiểm head | Chưa phản ánh thị trường. Timestamp heartbeat không phải thời điểm cập nhật market feed |
| `JsonFilePriceProvider` | Đọc strict snapshot; hiện allowlist `TRUSTED_TEST_ORACLE` | External mode không tự gọi real feed. Cần merge nguồn, decimals/freshness/outage validation và đồng bộ owner-approved source/config hashes |
| MockUSDC/MockWAVAX | ERC20 mint bởi owner; WAVAX mock không wrap/redeem native AVAX | LOCAL/FUJI có contract thật nhưng tài sản không có giá trị/thanh khoản thị trường |
| MockSwapAdapter/liquidity | Linear quote owner-controlled; demo mint liquidity | Không có AMM/real DEX/slippage thị trường/MEV model đầy đủ |
| Stress | Baseline/mild/adverse quote cố định trong isolated fork | Bounded scenarios, không phải phân bố tấn công/giá thực tế |
| Planning/alignment/experience | Rules/templates/regex và amount hints | Không có API LLM, semantic proof hoặc học máy |
| Operator baseline mandate | Một số limits cài trong code, không phải mọi thứ đều env/UI-editable | Ví dụ 500 USDC/swap, 1.000/ngày, 25% exposure trước ký, $50 daily cost, tối đa hai replans |

LOCAL thực sự chạy Z3, EIP-712, native Anvil, vault enforcement và receipt. FUJI code sử dụng public RPC/transaction nếu triển khai; **các thành phần mock ở trên vẫn mock trên Fuji**. Xem [system design mục 4–8](../AI_Treasury_Security_System_Design_v2.1.md) để biết công thức, units, assumptions và từng nguồn dữ liệu.

## 4. Lỗi tìm thấy và đã sửa

| ID | Vấn đề trước sửa | Cách sửa và kiểm chứng |
| --- | --- | --- |
| F01 | Một protected revert được reconcile lại sau reorg có thể bị đếm hai lần, làm quarantine sai | Chỉ lấy latest terminal event cho từng decision/attestation đã kết thúc. Ba regression cases: một revert reconcile lại, hai revert khác nhau, confirmed ngắt chuỗi |
| F02 | Recovery CLI cũ tạo control client trỏ B server đã bỏ, không dùng được trên unified backend | Thêm operator-auth `POST /v1/workflows/{id}/recover`; CLI gọi đúng unified API. Kiểm known journaled hash/decision/build/chain, không ký hoặc resend; tests kiểm recovery/repeat/wrong hash/auth/schema/redirect/unsafe origins |
| F03 | Primary npm commands còn trỏ B-only execution CLI | Chuyển startup/deploy/demo aliases sang unified path; giữ `b:*` có nhãn compatibility; thêm architecture regression |
| F04 | MOCK notice có thể bị hiểu nhầm là demo proof V2.1 | UI ghi rõ V1 fixture, không proof V2.1 hoặc giao dịch on-chain |
| F05 | Docs còn mô tả hai server, isolated signer, sai test bị skip | Canonical design/navigations ghi một API và cùng-process keys; sửa skip thành LOCAL ablation. Historical checkpoint được đánh dấu riêng |

F01 là lỗi liveness/quarantine; không có bằng chứng mất tiền hoặc bypass signing. Repro trước sửa có một test thất bại; các regression và full suite sau sửa đều đạt. Không thay Solidity, signed schema hoặc công thức proof trong lượt rà soát này.

## 5. Kết quả kiểm chứng mới

| Kiểm tra đã chạy | Kết quả / giới hạn |
| --- | --- |
| Full Python sau các sửa lỗi và command aliases | **157 passed, 1 skipped**, hai dependency deprecation warnings; skip là LOCAL ablation opt-in |
| Solidity Forge | **49 passed**, không fail/skip |
| V1/V2 Python ↔ viem vectors | PASS: EIP-712/digest/signer, V2 Phi ABI/hash/version isolation |
| Browser module syntax | **8 files PASS** |
| Actual LOCAL browser workflow | 200 USDC → CONFIRMED; REAL_LOCAL_SIM; proof VERIFIED, ba UNSAT; certified risk reservation **$4,792**; actual Anvil receipt block 16 |
| Browser visual check | Desktop 1440×1100, mobile 390×844; không horizontal overflow/uncaught JS errors; profile tạm, không dùng session cá nhân |
| LOCAL four-mode ablation, chạy riêng | **1 passed**; 28 records/4 modes, cumulative reservation case ở V2 bị chặn trước ký |
| Proof parameter sweep | **128 cases**: 80 VERIFIED, 48 refused, 0 UNKNOWN; p50 8,39 ms, p95 12,89 ms, worst 15,94 ms trên máy local |
| Ruff / secret scan / docs links / whitespace | PASS; 406 local file links tồn tại, không thấy configured secrets trong tracked/unignored files; không có diff whitespace errors |
| Env check | Read-only, không RPC/transaction; configuration_ready=true, không thiếu mandatory names cho demo profile; `.env` giữ nguyên bytes |

Hai warnings Python hiện tại là deprecation từ `websockets.legacy` và Starlette/AnyIO testclient alias. Không tự nâng dependency trong một lượt audit/refactor vì cần review compatibility riêng. Ruff áp dụng scope/exclusions trong `pyproject.toml`; không đồng nghĩa toàn repo đã được format hoặc dependency CVE audit.

Ablation mới gồm FULL_V1: 6 confirmed/1 protected revert; PGS_CORE: 5/2; V1_PLUS_PHI: 5/2; V2_1_CORE: 4/2/1 pre-sign refusal. Đây là guard-level bounded scenarios; không phải benign acceptance rate hoặc APR của thị trường. 48 proof refusals thuộc parameter grid, không được tự gọi là 48 false positives trong thực tế.

Full-protocol 14-case V1-original/V2-unified comparison được chạy ở checkpoint gộp API trước đó, tóm tắt tại [unified-protocol-summary.json](../architecture/unified-protocol-summary.json). Lượt audit này không chạy lại comparison đó; không trộn số timing lịch sử với kết quả mới. Existing evaluation reports/raw JSON được giữ nguyên; lần mới ghi output riêng.

Các lệnh đã dùng từ root:

```powershell
uv run --locked --offline python -m pytest -q
uv run --locked --offline python tools/contracts/foundry.py forge test -vv
npm run test:integration
node tools/quality/check_frontend.mjs
uv run --locked --offline ruff check backend/src backend/tests tools
uv run --locked --offline python tools/quality/scan_secrets.py

$env:RUN_V2_ABLATION='1'
$env:V2_ABLATION_OUTPUT='.control-data-v2/audit-ablation-results.json'
uv run --locked --offline python -m pytest backend/tests/execution/test_v2_ablation.py -q
Remove-Item Env:RUN_V2_ABLATION, Env:V2_ABLATION_OUTPUT
uv run --locked --offline python tools/evaluation/benchmark_proof.py --output .control-data-v2/audit-proof-sweep.json
```

Private local logs/screenshots nằm trong ignored `.control-data-v2/` và `.control-data-ui/`. Public evidence JSON chỉ chứa kết quả đã lược thông tin máy/keys/tokens. LOCAL receipt hash chỉ là hash trên Anvil riêng, không tra được trên Fuji explorer. Disposable browser fallback được dùng vì in-app browser bootstrap không hoạt động trong session này.

## 6. Các việc còn lại trước khi gọi là demo public/production

| Ưu tiên | Việc còn thiếu | Điều kiện xác nhận |
| --- | --- | --- |
| Demo public | Deploy V2 lên Fuji bằng owner từ máy quản trị | Manifest/code/policy/session đúng; lưu actual normal swap và protected-revert hashes, canonical receipts/confirmations |
| Hosted demo | Build/run root và frontend images, mount storage/manifest, tạo runtime env | Health/startup/restart/pending recovery/proxy/CORS đạt trên Docker/Render/VPS thật |
| Release CI | Chạy workflow của working tree mới từ fresh clone không PGS reference | Có run/artifacts xanh thực tế; file CI tồn tại chưa phải CI pass |
| Dữ liệu thị trường | Merge/review oracle của cộng tác viên | Nguồn/provenance/precision/freshness/outage checks và policy/session hashes đồng bộ; không refresh timestamp để che stale feed |
| Real swap | Adapter/DEX/token thực, review side effects và registry coverage | Exact simulation + adversarial integration + vault tests cho adapter mới; mock pool pass chưa đủ |
| Production operations | Independent security audit, key storage/threat model, recovery/backup/load/monitoring review | Hiện một worker/instance, SQLite/journal; chưa có HSM/KMS/HA/distributed limiter/background watcher |

Giới hạn cần giữ trong thiết kế: final preflight dùng pinned build block/cache, không full re-sim latest; verification RPC có thể cùng provider, không phải quorum; proof conditional trên model/price bands/trusted inputs; certified debit là reservation, không realized PnL; exposure chỉ pre-sign; gas-cost budget không phải atomic on-chain gas ceiling. Chi tiết trong system design và [proof assumptions](../security/proof_assumptions_v2_1.md).

## 7. Môi trường và thao tác bên ngoài

Kiểm tra không gọi RPC cho thấy đủ cấu hình bắt buộc của demo profile và ba vai trò ví; không in hoặc sửa giá trị `.env`. Không cần thêm LLM/feed credentials khi tích hợp đó chưa có. Đọc [env template](../../.env.example) và [environment status](../demo/ENVIRONMENT_STATUS.md) để điền đúng units.

Hiện **chưa có V2 Fuji deployment manifest**, `deploy/runtime.env` riêng hoặc manifest mount cho Compose. Đây là artifacts cần tạo khi triển khai, không phải những biến có thể đoán để điền thay actual deployment. Runtime env phải dùng giá trị đã resolve, không chứa owner private key; owner/relayer funding và RPC historical-state support cần kiểm tra tại thời điểm chạy thật.

Docker Desktop Linux engine không chạy trên máy khi audit nên không kiểm chứng image/Compose/Render. Không gửi testnet transactions hoặc tạo hosting service trong lượt này. Điều này không ngăn LOCAL chạy, nhưng ngăn kết luận “đã hoàn chỉnh để chạy public/production”.
