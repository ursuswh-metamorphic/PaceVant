# Live Demo: đầu vào, tiến trình và đầu ra của 12 bước

Ngày hoàn thiện: **21/11/2026 — Asia/Saigon**. Thay thế các nhận xét chưa được xử lý trong [báo cáo trước khi sửa](LIVE_DEMO_MODULE_AUDIT_20261121.md). Các dữ liệu và ảnh của bản rà soát cũ vẫn được giữ làm checkpoint lịch sử.

## Thay đổi đã thực hiện

Giữ bố cục ba giai đoạn và 12 bước. Theo yêu cầu cập nhật, **tên cả 12 module luôn giữ tiếng Anh ở cả chế độ VI và EN trên mọi trang**; các mô tả, đầu vào/đầu ra và giải thích vẫn theo ngôn ngữ được chọn. Đổi tuyên bố “12 module độc lập” thành “12 bước bảo vệ giao dịch”. Không bổ sung nghiệp vụ tài chính hay nới các điều kiện của Owner, oracle, proof, ký hoặc vault.

Mỗi panel có đường dẫn nhanh **Đầu vào / Xử lý / Đầu ra**, tên bước được giữ trên thanh điều hướng khi cuộn, và nút đóng luôn nằm trong vùng nhìn thấy. Đầu vào không còn phụ thuộc vào việc bước đã tạo kết quả. Dữ liệu từ các bước trước có nguồn rõ ràng và có thể mở rộng.

| Bước | Thông tin được bổ sung |
|---|---|
| Chính sách chủ ví | Yêu cầu/chain/vault/session, danh mục đã ký, quyền và hạn mức, thời hạn, block tham chiếu, giá và vòng cập nhật Chainlink |
| AI và ý định | Yêu cầu cố định và điều khoản chính xác ngay khi đang chạy; Shield kiểm tra nội dung/lời gọi; đối chiếu đề xuất; provider, thời gian và token được báo cáo |
| Dựng giao dịch | Registry và phạm vi phiên; hạn mức recipient; báo giá LFJ so với dự trữ pool và Chainlink; phương thức/tham số call được giải mã khi ABI hỗ trợ; calldata gốc còn trong bằng chứng |
| Mô phỏng EVM | Transaction/build, pinned context, balances trước/sau, deltas, số tiền thực nhận trong mô phỏng, allowances và gas |
| Rủi ro kinh tế | Từng kiểm tra freshness, hash binding, outflow, allowance, minimum receipt/output, chi phí và cửa sổ oracle; expected/observed/verdict |
| Shield và ITAG | Đồ thị thực của backend, mức tin cậy/nguồn gốc, quan hệ và tham chiếu; kiểm tra history/authority; semantic result; các lần Shield interception xuyên suốt workflow |
| Z3 và Phi | Bốn truy vấn với expected SAT/UNSAT và actual result; budget/exposure; giả định, Phi, query source/hash; không diễn giải SAT là bằng chứng an toàn chung |
| Quyết định bảo mật | Tổng hợp các điều kiện bắt buộc, hashes/evidence liên kết và thời hạn phê duyệt |
| Kiểm tra lại và ký | Revalidation state/risk/Shield, chạy lại proof, sign-once, domain/chain/contract/nonce/deadline và các trường operation thực sự được ký |
| Kiểm tra giao dịch đã ký | Exact signed preflight, Phi cuối, effects/gas và tái kiểm tra state trước relay |
| Gửi và thực thi | Signer/relayer, gas guard, journal và giữ phí trong cùng transaction DB, trạng thái broadcast và khôi phục đúng submission cũ |
| Biên nhận và đối soát | Receipt lookup, transaction binding, event/effects/Phi, canonical block, confirmations, actual gas expense; kết quả mới nhất đứng trước lịch sử |

Ngân sách USDC/USD-e8 và các lượng WAVAX/AVAX được đổi đúng đơn vị khi có ngữ cảnh. Các giá trị nhỏ không bị trình bày thành 0 do cắt còn sáu chữ số USD hoặc mười hai chữ số WAVAX. Hash, nonce, địa chỉ, tên phương thức và enum gốc vẫn được giữ ở lớp bằng chứng kỹ thuật.

Prompt giải thích mới ưu tiên tiếng Việt, với phiên bản `task-shield-hybrid-v1.1-vi` và `itag-catalog-v3.5-vi`. Điều khoản gốc, schema, enum và số lượng chính xác không được dịch hay thay đổi. Bản ghi cũ giữ nguyên nội dung gốc; giao diện nói rõ khi bản ghi chưa có nhật ký chi tiết.

## Dữ liệu backend

`workflow.timeline` tiếp tục là bằng chứng nghiệp vụ. `workflow.activity` là luồng quan sát bổ sung, gồm:

- `sequence`, `stage`, `created_at`;
- `kind`: `started`, `check`, `completed`;
- `status`: kết quả thật, ví dụ `RUNNING`, `PASS`, `FAIL`, `UNKNOWN`, `UNAVAILABLE`;
- `check_id` và `check_ref` để giữ từng lần interception riêng biệt;
- `expected`, `observed`, `input_refs`, `inputs`, `output_refs` khi có;
- `duration_ms` được đo tại backend, không suy ra từ animation hoặc tiến độ giả.

Bảng `treasury_activity` có index theo workflow/sequence và trigger chặn update/delete, tương tự bằng chứng nghiệp vụ. Trace không được dùng làm đầu vào cấp quyền hoặc trường mới của EIP-712. Source hash của proof vẫn phản ánh phiên bản source thực tế theo cơ chế SDK hiện có.

Trong transaction DB giữ chỗ ký, sự kiện được đệm rồi ghi sau khi transaction kết thúc. Điều này tránh mở writer thứ hai gây khóa SQLite. Timestamp và duration vẫn là mốc thực lúc thao tác diễn ra. Vì thế một số kết quả bên trong bước ký xuất hiện cùng lúc sau commit, không phải tiến trình được dựng bằng timer.

`ATTESTATION.signed_fields` chỉ chứa nội dung operation công khai, không chứa chữ ký hoặc khóa. Callback execution chỉ chuyển facts/references cần thiết. Các trường chứa private key, credential, signature hoặc raw transaction bị loại khỏi trace; các public bytes32 hash vẫn được giữ.

Giai đoạn chuẩn bị có `request`, `preparation`, `oracle_observation`: thời điểm quan sát, block, cửa sổ ký còn lại và thời gian tối thiểu cần có. Guard chưa chọn intent cụ thể chỉ được mô tả là tình huống do server chọn, không trình bày amount/recipient giả định như điều khoản đã chốt.

History chỉ được tải/poll khi người dùng mở trang Bằng chứng. Job đang chạy tiếp tục lấy cập nhật mỗi giây; backend không phát sinh thêm RPC hay model call để làm animation. Snapshot `activity` được đọc cùng workflow khi công bố progress và chỉ thuộc đúng job hiện tại.

## Kiểm tra bảo mật trên giao diện

Nút **Chạy kiểm tra bảo mật thực tế** gọi preset `guard` cố định của backend, dùng quota, idempotency và recovery hiện có. Đây là tình huống do máy chủ chọn; không phải thực thi sáu bản mô tả tấn công.

Sáu lựa chọn ở mục “Tìm hiểu tình huống tấn công” được ghi rõ là nội dung mô tả, chưa tạo kiểm tra/giao dịch. Không có tuyên bố bảo đảm mọi tấn công sẽ bị chặn. Lỗi oracle/model không bị đổi thành kết quả phát hiện tấn công.

## Kiểm chứng

### Lượt chạy mới, model thật và EVM fork thật

| Kịch bản | Job | Kết quả |
|---|---|---|
| Payment | `judge_89cc7d398e37416abead2bf9a31d6ea7` | **CONFIRMED**, 0,01 USDC thực nhận trên fork |
| Swap | `judge_f19883e32c8c4308ac4549ced52ecf3f` | **CONFIRMED**, USDC → WAVAX qua luồng hiện có |
| Guard từ nút mới | Xem [summary](live-demo-observability-20261121/summary.json) | **REJECTED**, `LFJ_UNSUPPORTED_ROUTE`, trước ký/relay |

Cả ba dùng `ANVIL_FORK`, không broadcast public. Browser reload khi đang chạy, phục hồi đúng job và mỗi kịch bản chỉ tạo một POST. Payment/swap ghi nhận 86 activity events ở thời điểm chạy kiểm chứng; các annotation bổ sung cho model/ABI/budget được kiểm tra tiếp bằng EVM regression, không dùng con số 86 làm điều kiện cố định của ứng dụng.

### Kiểm tra hiển thị và hồi quy

- 48 lượt mở panel: đủ 12 bước × desktop/mobile × VI/EN, dùng response payment thật vừa thu để kiểm tra hiển thị, không gọi đó là 48 lần thực thi.
- 8 lượt kiểm tra thêm các panel chính sau lần chỉnh cuối. Không có lỗi JavaScript hay tràn ngang trong các lượt này.
- Frontend: **29 tests passed**, TypeScript và production build đạt. Build vẫn có cảnh báo bundle hiện có và directive của dependency; không phải lỗi build.
- Backend: lượt chạy rộng kiểm tra 77 trường hợp, ban đầu 76 đạt và một assertion cũ chưa chấp nhận `oracle_observation`. Assertion đã được cập nhật để kiểm tra chính giá trị freshness mới; các lượt chạy tiếp theo của nhóm liên quan đều đạt, gồm **17 tests** ở đợt cuối. Các nhóm đã kiểm tra gồm boundaries, public activation/key filtering, quotas/recovery, ITAG/citations, planning, local-EVM workflows, observability và resilience.
- Các kiểm tra mới xác nhận trace không thay đổi kết quả proof khi bật/tắt observer, payment sai payee không tới ký, retry không tạo giao dịch/chữ ký mới, và trace không chứa signing capability.

Các script kiểm thử dùng mô hình fixture được ghi nhãn fixture. Chúng kiểm tra protocol/EVM và các nhánh âm; không thay cho kết quả live ở bảng trên. Bản ghi hiển thị được phục vụ lại riêng GET job trong browser QA để mở rộng panel mà không trả thêm tiền model hay chạy lại giao dịch. Không mock API trong ba lượt chạy live.

## Chạy lại tại local

```powershell
uv run --locked python -m treasury_backend.operations.judge_local
npm run --prefix frontend dev
```

`judge_local` chỉ đọc các setting model được whitelist từ `.env`, loại wallet keys khỏi process, bật HTTP cookie local và luôn dùng fork. Mặc định backend 18040, frontend 5173. Có thể dùng `--port`, `--model-env`, `--data-dir`; dùng `PACEVANT_API_TARGET` trong process Vite khi cần proxy tới cổng backend khác. Đây là entrypoint phát triển, không thay cấu hình public service.

Trong phiên hoàn thiện này, bản mới chạy ở **http://localhost:5174**, backend **http://127.0.0.1:18041**, còn tiến trình cũ được giữ nguyên. Không deploy production, đổi manifest, gia hạn session hay cấu hình lại wallet.

Fresh Chainlink, model/RPC, ngân sách, policy/session và quota vẫn là điều kiện thật để thực thi. Nếu thiếu, UI hiển thị chờ/không khả dụng và lý do. Không cam kết mọi lượt chạy sẽ thành công hoặc luôn hoàn tất trong một khoảng thời gian cố định.

## Bằng chứng lưu cùng thay đổi

- [Tóm tắt máy đọc được](live-demo-observability-20261121/summary.json).
- [Payment hoàn tất](live-demo-observability-20261121/payment-desktop.png), [swap hoàn tất](live-demo-observability-20261121/swap-desktop.png), [guard bị chặn](live-demo-observability-20261121/guard-desktop.png).
- [Chi tiết ITAG](live-demo-observability-20261121/itag-desktop.png), [kiểm tra lại và ký trên mobile](live-demo-observability-20261121/attestor-mobile.png), [đối soát receipt](live-demo-observability-20261121/receipt-desktop.png).

Response đầy đủ, script và raw browser reports nằm trong `data/module-evidence-check/` theo quy ước ignored của repository. Ảnh và summary trong thư mục tài liệu không chứa cookie hay khóa ví.
