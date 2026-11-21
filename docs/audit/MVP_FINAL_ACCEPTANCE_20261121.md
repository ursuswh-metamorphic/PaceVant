# Kiểm thử MVP qua web và đo thời gian/chi phí — 21/11/2026

## Kết luận theo phạm vi thực tế

**Hai nghiệp vụ tài chính đã chạy thành công qua giao diện local; preset Security Guard thực sự bị chặn trước khi ký.** F5 mở lại đúng tab Demo và phiên đang chạy hoặc kết quả đã hoàn tất. Không giả lập phản hồi thành công trong các lượt live, không sửa timestamp oracle, không nới policy và không thay kết quả bằng replay.

Phạm vi là Chromium → React/Vite `127.0.0.1:5173` → Judge API `:18040` → model DeepSeek thật → EVM fork của Avalanche Fuji. Không phải kiểm thử production VPS hoặc phát giao dịch mới lên public Fuji.

**Giới hạn quan trọng:** sáu lựa chọn tấn công theo payment/swap vẫn chỉ là bản xem trước UI theo scope trước đây. Chúng không có API chèn tấn công và chưa thể được gọi là sáu bài kiểm tra phát hiện tấn công chạy thật. Security Guard là preset backend riêng; lần này được gửi qua API đúng contract rồi xem kết quả trên cùng giao diện. Không gán kết quả của Guard cho sáu bản xem trước.

## Ba lượt live mới nhất

| Kịch bản | Kết quả thực | Thời gian quan sát trên web | Worker | Gọi AI | Token input / output |
|---|---|---:|---:|---:|---:|
| Thanh toán 0.01 USDC | CONFIRMED | 48.102 giây | 43.906 giây | 11 | 33,892 / 2,821 |
| Hoán đổi 0.000001 USDC → WAVAX | CONFIRMED | 51.374 giây | 46.828 giây | 11 | 39,727 / 2,933 |
| Security Guard có sẵn ở backend | REJECTED — `LFJ_UNSUPPORTED_ROUTE` | 36.661 giây | 33.016 giây | 5 | 10,745 / 1,036 |

Thời gian trên web tính từ response job được chấp nhận đến snapshot terminal, không bao gồm thời gian chờ nguồn giá **trước khi bấm** trong harness. Worker gồm chuẩn bị fork, gọi model, pipeline và cleanup; khác biệt là startup/subprocess/polling. Đây là ba quan sát, không phải p95 hoặc SLA.

Job IDs:

- Payment: `judge_c7d229821ce848deab0afdc5876598f9`.
- Swap: `judge_972d1050213c422e9446bca41b01661d`.
- Guard: `judge_af50ce6384ed4492a70ee36bb8f4c8b1`.

Hai lượt positive đều đi qua Owner → AI → Builder → EVM Simulation → Economic Risk → ITAG → Z3/Phi → SDE → Attestor → Exact Signed Preflight → Relayer/PolicyVault → Receipt. Risk/ITAG PASS, proof VERIFIED, preflight không có simulation overrides. Các lời gọi được Shield kiểm tra xuyên suốt. Đã đối chiếu 24/24 panel với stage thật, prompt/intent đúng response, Receipt và tx hash hiện đúng. Một số bước ngắn hoàn tất trong cùng lần polling; không ép animation kéo dài để tạo tiến độ giả.

Guard dừng tại Trusted Builder do route nằm ngoài allowlist LFJ; timeline có Owner, AI và rejection, **không có Attestation hoặc Outcome**. UI giải thích bằng VI/EN và giữ kết quả sau F5. Đây là kiểm tra route thực tế, không phải kết luận mô hình đã phát hiện mọi loại prompt injection.

## Chi phí ghi nhận và cách tính

### Model

Worker có `runtime_metrics.inference` đo riêng tất cả lời gọi từ planning và security, bao gồm token do provider trả về. Không lưu thêm prompt, response, credential hoặc endpoint vào metrics. Bộ đo trả nguyên response hoặc exception của provider, không tham gia quyết định bảo mật.

[Bảng giá chính thức DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) kiểm tra ngày 21/11/2026: `deepseek-flash` off-peak mỗi triệu token là $0.003 input cache hit, $0.15 input cache miss, $0.60 output; peak gấp đôi. Ngày test là thứ Bảy nên thuộc off-peak theo lịch công bố. SDK hiện chưa lưu split input cache hit/miss; vì vậy báo **khoảng ước tính cho token thành công đã ghi nhận**, không giả một hóa đơn chính xác.

| Lượt | Tổng token | Ước tính USD cho token ghi nhận, off-peak |
|---|---:|---:|
| Payment | 36,713 | $0.001794–$0.006776 |
| Swap | 42,660 | $0.001879–$0.007719 |
| Guard | 11,781 | $0.000654–$0.002233 |
| **Tổng ba lượt mới nhất** | **91,154** | **$0.004327–$0.016729** |

Cận dưới coi mọi input là cache hit, cận trên coi mọi input là cache miss. Đây không phải mức tiền xác nhận đã bị trừ. Không bao gồm các lượt debug cũ, billing không báo token, phí thất bại không được provider trả về, VPS, thuê RPC hoặc chi phí lưu trữ. `billing_usd` để null vì không có hóa đơn. Nếu chạy giờ peak, khoảng tham chiếu gấp đôi; không hardcode giá vào quyết định thực thi.

### Gas

| Lượt | Gas của giao dịch nghiệp vụ | Phí Receipt trên fork, AVAX |
|---|---:|---:|
| Payment | 356,276 | 0.000356276002850208 |
| Swap | 453,058 | 0.000453058003624464 |
| Guard | Không gửi giao dịch nghiệp vụ | Không có Receipt nghiệp vụ |

Mỗi lần tạo môi trường còn có mười giao dịch deploy/config được helper ghi nhận, khoảng 7.374 triệu gas / 0.007374 AVAX trên fork. Đây không phải phí phát sinh trên ví public, cũng không phải tổng mọi chi phí mô phỏng: funding, RPC reads và các simulation con không nằm trong thống kê setup này.

**Phí public network của ba lượt: 0 AVAX**, vì không public broadcast. Model API vẫn là dịch vụ thật có thể tính tiền. Chưa đo CPU/RAM trên VPS và không suy ra chi phí VPS/tháng từ các mẫu local này.

## Kiểm tra hành vi và tình huống lỗi

- Cả hai lượt bấm web chỉ tạo **một POST/lượt**; chuyển sang Overview vẫn thấy thanh trạng thái. F5 tự mở Demo và khôi phục đúng job. F5 sau terminal vẫn mở cùng kết quả.
- Các scenario và nút chạy bị khóa trong lượt đang xử lý; tên nghiệp vụ, bước hiện tại và mã phiên xuất hiện trên thanh trạng thái. Không hiển thị phần trăm giả.
- 6/6 preview tấn công mở đúng nội dung theo payment/swap, không tạo job, không có data thực thi giả.
- Lịch sử lưu đúng lượt chạy; cả 12 node positive có evidence tương ứng. Kết quả chưa xác định không được coi là thành công.
- Không có lỗi JavaScript trong lần live. Không tràn ngang toàn trang ở 1440×900 và 390×844.
- 21/21 frontend unit tests.
- 16/16 backend tests cho quota/visitor/idempotency/restart, ITAG operation adapter và phép đo model.
- 18/18 kiểm tra an toàn MVP trên EVM local: unknown/counterexample của proof, reorg, broadcast chưa rõ, replacement, thiếu gas, ngân sách gas atomic, thay đổi typed terms, tuổi oracle và readiness không cấp quyền thực thi. Dữ liệu fault/scripted provider trong nhóm này **không được dùng làm bằng chứng đánh giá model live**.
- 4/4 kiểm tra browser có chủ đích chèn lỗi mạng bằng API test doubles: mất response POST rồi F5 lấy lại theo key; GET offline rồi reconnect; job đã accepted trả 404 vẫn không được POST lại; root error chung nhưng Risk evidence cụ thể phải được hiển thị đúng. Nhóm này đo UI/recovery, không giả làm lượt giao dịch thật.
- TypeScript/Vite build và các kiểm tra Ruff/diff liên quan đều qua. Còn cảnh báo bundle frontend lớn, không chặn build.

## Sửa trong vòng hoàn thiện này

1. Giữ riêng idempotency identity của yêu cầu đang gửi và reference của phiên đang xem. Khi reload, ưu tiên pending attempt; không lấy nhầm kết quả cũ nếu POST mới chưa acknowledged. Terminal chỉ xóa pending identity, vẫn lưu phiên để đọc lại sau F5.
2. Khởi tạo tab Demo từ saved run thay vì luôn quay về Overview. Khóa thao tác trong lúc restore; bootstrap cookie trước các reads song song.
3. Luồng recover một job đã accepted chỉ dùng GET. Record không truy cập được không trở thành một lệnh gửi mới.
4. Thanh trạng thái rõ ràng trên các tab; nút chạy có trạng thái đang xử lý. Mất kết nối có nút reconnect và giữ bằng chứng gần nhất.
5. Giải thích lỗi cụ thể từ Risk, ITAG, Z3 hoặc error code, kèm module đã chặn. Phân biệt lỗi provider/citation với phát hiện hành vi tấn công. Chỉ tuyên bố dừng trước ký nếu evidence xác nhận `signed:false` và chưa có attestation/tx.
6. Thêm đo lường model/worker/setup mà không đổi logic chấp thuận. Các bản sửa proxy Vite/ITAG catalog từ vòng trước tiếp tục được kiểm tra qua live lần này.

## Điều chưa thể cam kết

Không thể cam kết mọi thời điểm đều CONFIRMED: oracle testnet có thể ngoài cửa sổ Owner, RPC/provider có thể lỗi, quota có thể hết và dịch vụ chỉ chạy một heavy job đồng thời. Khi thiếu bằng chứng hợp lệ, kết quả đúng là dừng/chưa xác minh, giữ lý do và không tự gửi lại. Lượt trước của vòng UI đã quan sát `FRESH_CHAINLINK_SIGNING_WINDOW_UNAVAILABLE`; không thay oracle để né lỗi này.

**Bản local đã qua phạm vi hai nghiệp vụ và nhánh Guard có sẵn; chưa phải acceptance cho cả sáu attack injection, public Fuji MVP migration, VPS production 24/7, multi-day soak hoặc kiểm định bảo mật độc lập.** Chưa push hoặc deploy các thay đổi local.

## Bằng chứng và tái lập

- [Số đo tổng hợp JSON](judge-mvp-final-20261121.json).
- `data/judge-mvp-final/report.json`: quan sát browser, polling, UI assertions và IDs.
- `data/judge-mvp-final/{payment,swap,guard}-job.json`: response backend cùng timeline và metrics.
- `data/judge-mvp-final/session-fault-injection.json`: fault injection UI, tách khỏi live.
- [Báo cáo vòng UI trước](JUDGE_UI_FLOW_ACCEPTANCE_20261121.md).

```powershell
# Cần local backend/frontend đang chạy; tạo 3 job thật và dùng quota/API model.
python -u tools/quality/check_judge_workflow_ui.py --wait-oracle --final
python tools/quality/summarize_judge_acceptance.py

# UI fault injection, không tạo job live/model call.
python -u tools/quality/check_judge_session_edges.py
```

Harness chỉ chờ round mới để lên lịch kiểm tra; worker tự đọc/xác minh lại và các gate vẫn có quyền từ chối. Không tự retry một giao dịch không chắc chắn. Không có dữ liệu thành công hardcode trong production để vượt kiểm thử.
