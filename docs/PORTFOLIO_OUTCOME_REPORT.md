# Báo cáo triển khai Portfolio State & Outcome Monitoring

Nguồn: `main` tại `8e833d3d6eef4872f65312d2de23df47d0b1c0ab`, đã đối chiếu remote trước khi bàn giao. Nhánh: `codex/portfolio-outcome-reconciliation`. Thay đổi được gửi qua PR để review, không tự merge. [Audit trước triển khai](PORTFOLIO_OUTCOME_AUDIT.md) · [Vận hành và migration](PORTFOLIO_OUTCOME_MONITORING.md) · [Bằng chứng JSON](../evidence/portfolio-outcome-validation.json).

## Kết quả theo module

| Module | Before | After | Tests | Remaining limitation |
|---|---|---|---|---|
| Portfolio snapshot | Số dư/giá/block number, ID ngẫu nhiên; thiếu provenance khi A ghép dữ liệu | Schema 2.0 tách Observed/VerifiedDecision; hash canonical; chain/Vault/token/code/decimals/block hash/time/RPC/policy; số nguyên và null rõ ràng | Native/ERC-20 chính xác, hash xác định, chain/token/decimals/block sai, stale, oracle thiếu/sai identity, không giả zero | Hai token theo mandate và native AVAX; chưa là indexer tất cả tài sản |
| Nguồn Fuji và A/B | B đọc pinned block; A chủ yếu kiểm header; observer chưa đi cùng persisted portfolio | A tự đọc pinned block, so B cùng block; kiểm metadata/owner/policy; CLI quan sát public LFJ; oracle chỉ quan sát | Public Fuji read-only thực tế; negative RPC và oracle; A+B thực | Tin cậy RPC/archive; hai implementation đọc độc lập có thể dùng cùng node |
| Lịch sử SQLite | Version toàn cục; post balance best effort | Bảng snapshot/link/lifecycle bất biến, scoped version theo mode/chain/Vault, pre/post gắn decision/build/tx, projection phí dedup | Trigger immutable, scope khác Vault/mode, restart, duplicate/concurrent, reorg invalidation | Scoped v2 bắt đầu từ 0; dữ liệu legacy cần đọc archive để đối chiếu |
| Receipt verifier | Có log/delta/gas checks nhưng thiếu đầy đủ tx/calldata/canonical binding | Một verifier dùng chung A/B; PDR/calldata/runtime/log metadata/event/token/minOut/nonce/allowance; đọc lại canonical hash | 14 trường hợp Anvil receipt gồm pending/outage, sai hash/block/recipient/calldata/event/delta/nonce/policy/allowance; LFJ fork | Depth confidence không phải chứng minh consensus finality |
| Outcome worker | Poll theo workflow GET, không có queue/lease bền vững | Job SQLite, lease/CAS, backoff, lookup journal chỉ đọc, worker process mới không cần khóa ký, kiểm lại terminal receipt | Pending→success/revert, restart worker trước/sau mining, outage/recovery, lease hết hạn, concurrent, unknown/expired hash, phí một lần | Cần chạy worker liên tục để theo dõi khi không có API GET; polling tuần tự cho tải POC |
| Reconciliation | Receipt summary và số dư mới nhất; khó quy kết external activity | Pre/post cùng block được định danh; effects theo tx logs; residual tách riêng; reorg giữ audit và cập nhật projection; gas relayer tách Treasury | A+B success/replan/protected revert/delayed mining; external delta inconclusive; reorg→reinclusion | Unrelated transfers giữa hai snapshot làm attribution inconclusive, cần review |
| API/SDK | SDK 1.2.0, các DTO A/B hiện có | SDK 1.3.0 thêm reconciliation/submission lookup/pinned snapshot; authenticated current/history/detail; observer không có execute/attest route | Compatibility consumer, golden Python/viem/Solidity, auth, giới hạn query, read-only RPC allowlist | Consumer cũ phải kiểm detailed report trước khi hiểu inclusion là safe execution |

## Kiểm thử đã chạy

Không có test cũ bị bỏ hoặc nới assertion. Bộ A/root tăng từ **59 lên 93** test deterministic; thêm một test public Fuji opt-in. B tăng từ **51 lên 66** test deterministic, bao gồm **5** luồng A+B; hai test fork vẫn opt-in. Các lần chạy cuối không có test fail.

| Lệnh | Kết quả thực tế |
|---|---|
| `uv run --locked python -m pytest -q` | 93 passed; 1 public-Fuji test skipped khi không bật opt-in |
| `uv run --locked ruff check .` và `ruff format --check .` | PASS |
| `npm run test:python` (WSL Ubuntu, Anvil tạm) | 66 passed, 2 public-state fork tests skipped theo mặc định |
| `npm run test:contracts` | 37 passed |
| `npm run test:integration` | PASS: Python ↔ TypeScript EIP-712 digest/signer/calldata/canonical manifest |
| `npm run scan:secrets` | PASS, không tìm thấy configured secret hoặc file bị lộ |
| `npm run test:lfj:fork` | 2 passed; receipt được shared read-only verifier xác nhận VERIFIED trên fork |
| `$env:PACEVANT_PORTFOLIO_FUJI_READ='1'; uv run --locked python -m pytest apps/control-plane/tests/test_portfolio_fuji_read.py -q` | 1 passed, public Fuji reads only |

Trên máy hiện tại, root test chạy bằng `.control-data-integration/venv-a/Scripts/python.exe -m pytest -q` vì Windows Application Control chặn executable shim `pytest`; Python module và test vẫn chạy bình thường. B/Anvil/golden/Forge chạy trong checkout QA cô lập trên WSL; không đụng DB/dashboard đang chạy của người dùng. Có cảnh báo deprecation từ thư viện và lint Solidity hiện có trong test fixture; không có lỗi kiểm thử.

Các file test chính:

- `apps/control-plane/tests/test_portfolio_state.py`: 34 trường hợp bổ sung về provenance, persistence, worker, reorg, auth và capability.
- `apps/control-plane/tests/test_portfolio_fuji_read.py`: quan sát LFJ token thực trên Fuji, không wallet/key.
- `apps/execution-plane/tests/test_outcome_reconciliation.py`: 14 trường hợp xác minh receipt thật trên Anvil với phản hồi đọc bị sửa để kiểm thử âm.
- `apps/execution-plane/tests/test_ab_integration.py`: 5 luồng A/B trong tiến trình riêng, pre/post persisted và worker mới mở lại cùng DB không có ATTESTOR_KEY/INTERNAL_TOKEN/ORACLE_FILE.
- `apps/execution-plane/tests/test_lfj_fuji_fork.py`: bổ sung shared verifier trên receipt của LFJ route thật trong fork.

## Bằng chứng thật và giới hạn

Public Fuji observation đã lưu tại block **61341096**, hash `0x586544fe4988e2a951b45bfa0c42316a053265c1364808f2a9df31bbd1933fad`. Địa chỉ quan sát là pool LFJ `0x9371619C8E2A487D57FB9F8E36Bcb0317Bff0529`, **không phải Treasury/ví của người dùng**. Native balance là `0`; LFJ faucet USDC là `11750256108` base units và WAVAX là `1437166452128775484365` base units. Không diễn giải các số này thành giá trị USD. CLI xuất đúng địa chỉ token, decimals, code hash, block và trạng thái nguồn.

Chainlink AVAX/USD và USDC/USD được đọc thành công trong heartbeat của feed nhưng quá tuổi cho risk policy 60 giây tại lần quan sát đó. Witnet trả dữ liệu chưa hợp lệ; Pyth stale. Những trạng thái này được giữ trong snapshot, không biến thành giá thay thế. Feed USDC/USD không xác lập định giá cho LFJ faucet USDC. Trạng thái oracle là bằng chứng tại block nêu trên, không cam kết trạng thái hiện tại sau đó.

Hai receipt LFJ được kiểm thử trên **Anvil fork cô lập chain 43113**, với route LFJ V1 USDC/WAVAX qua LBRouter V2.2. Một ngân sách fixture không đủ stress được đánh dấu INCOMPLETE; fixture đủ ngân sách có COMPLETE với protected-revert stress. Bộ verifier xác nhận calldata/event/delta/nonce/allowance/gas của receipt fork. Việc cấp token/roles và ký fixture diễn ra riêng trên Anvil; runtime quan sát/monitor không đọc khóa ví người dùng.

**Số giao dịch public Fuji phát sinh: 0.** Không có deployment hay receipt public mới. Không tuyên bố luồng live A→SDE→PDR→LFJ đã hoàn tất. Định giá USD đáng tin cậy cho LFJ faucet USDC vẫn là phụ thuộc upstream; phải giải quyết bằng nguồn/identity hợp lệ hoặc một thay đổi chính sách testnet được review riêng. Không nới Economic Risk Evaluator để tạo APPROVE.

## Các điểm tự phản biện đã xử lý

1. Tái kiểm tra trước ký đang nằm trong transaction bảo vệ nonce; ghi snapshot bằng một connection khác gây khóa SQLite. Đã chuyển bước này thành fresh read/hash validation không ghi lồng; snapshot pre gốc vẫn được lưu bất biến, quy tắc ký/reservation giữ nguyên.
2. Poll terminal lặp có thể tạo nhiều post snapshot do observation time thay đổi. Đã tái sử dụng post snapshot cùng canonical block; phí/version chỉ đổi khi nội dung tài chính có thay đổi thực sự.
3. Receipt success và balance difference không đủ quy kết. Đã xác minh exact tx/log/state và giữ residual riêng; snapshot mâu thuẫn không mang lifecycle RECONCILED.
4. Worker dùng signing settings sẽ vô tình yêu cầu khóa. Đã có ObserverSettings/ReadClient/server riêng và test ngăn đọc tên biến khóa; RPC allowlist cấm send/sign/privileged methods.
5. Test restart ban đầu bỏ qua backoff thực tế. Đã cho test chờ đúng `next_at` lưu trong SQLite, thay vì bỏ backoff của implementation.
6. Chỉ đánh dấu reorg là chưa đủ: projection expense phải cập nhật, snapshot cũ phải invalidated và audit phải giữ. Test reorg/reinclusion xác nhận cả ba, không tính phí hai lần.

Các thay đổi không đụng Solidity/PDR signing format, không thêm Graph DB/Redis/Celery/Temporal Action Graph và không thay thế planner, SDE hay Economic Risk policy.
