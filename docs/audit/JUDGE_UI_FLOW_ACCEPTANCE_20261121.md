# Kiểm tra luồng Live Demo qua giao diện — 21/11/2026

Phạm vi: frontend local `http://127.0.0.1:5173`, Judge backend local `:18040`, thanh toán USDC và hoán đổi USDC → WAVAX. Thao tác bằng Chromium, không mock API, không thay dữ liệu trả về và không phát giao dịch lên public chain. Trình duyệt tích hợp không khởi tạo được (`node:process` bị chặn); dùng Playwright/Chromium cục bộ.

## Lỗi phát hiện và bản sửa

1. **Nút chạy bị HTTP 403 `ORIGIN_NOT_ALLOWED`.** Vite dùng proxy dạng chuỗi tự đổi Host thành backend, không còn khớp Origin của trình duyệt. Đổi sang proxy object với `changeOrigin:false`. Giữ nguyên kiểm tra same-origin ở backend. Sau sửa, thao tác nút chạy tạo job bằng HTTP 202.
2. **Cả payment và swap bị ITAG từ chối do lỗi adapter sau merge.** Economic Risk PASS nhưng semantic grounding trả `CATALOG_OBJECTIVE_UNSUPPORTED`: graph operation cũ thiếu `status:AUTHENTICATED`, `terms.objective` và `proposal.user_goal_reason` theo catalog mới. Adapter nay truyền terms từ intent đã xác thực và rationale từ kế hoạch AI thực tế. Không lấy rationale từ builder, không dùng objective để giả câu trả lời AI, không sửa validator catalog hoặc nới policy. Hai job trước sửa: `judge_1e57fecc310d4eba93547ef8b0d57ede`, `judge_8b5dcdd6c5a54fcfb9175d61d879c696`.
3. **UI chưa giải thích giai đoạn chuẩn bị/chờ oracle.** Panel trạng thái nay hiển thị phase thực từ backend và giải thích lỗi nguồn giá bằng VI/EN. Graph vẫn không tạo dữ liệu hoặc tiến độ giả khi chưa có workflow.

## Kiểm tra đã hoàn tất

- 4/4 frontend tests: không hiện dữ liệu trước khi có evidence, prompt/intent thật đọc được, số dư và gas, giữ trạng thái chưa xác định.
- 26/26 backend tests cho catalog/adapter: cả payment/swap, ALIGNED/MISALIGNED/UNCERTAIN, citation sai, scope giả và build mismatch. Chỉ ALIGNED cùng các gate hợp lệ mới được PASS.
- 1/1 kiểm tra workflow trên EVM cục bộ: hoán đổi và receipt-checked payment qua proof, chữ ký, preflight, thực thi. Semantic provider trong kiểm tra này là scripted fixture, được phân biệt với lượt live có model thật.
- TypeScript và Vite production build thành công. Vẫn có cảnh báo kích thước bundle; không phải lỗi chặn build.
- Chromium xác nhận 6 bản xem trước tấn công theo nghiệp vụ không tạo POST/job hoặc kết quả bảo mật giả.
- Các lượt live đầu tiên khôi phục đúng job sau F5, không gửi thêm POST. Panel AI hiển thị objective khớp response backend và số lượng/intent được format dễ đọc; trình duyệt không báo lỗi JavaScript.

## Phụ thuộc nguồn giá thực tế

Hai lượt sau khi sửa adapter gặp `FRESH_CHAINLINK_SIGNING_WINDOW_UNAVAILABLE` trước khi có workflow: `judge_8ec6817373bc4e01996f123803a55e82`, `judge_815bf89814d449908abd5f91fa0855e0`. Khi đó Chainlink AVAX/USD đã quá cửa sổ Owner cho phép. Không ký, không relay; đây là từ chối an toàn, không được tính là thực thi thành công.

Worker hiện yêu cầu còn ít nhất 90 giây trong cửa sổ giá 300 giây, chờ tối đa theo cấu hình. Vì feed testnet không liên tục có round mới, không thể khẳng định lượt live luôn thực thi được 24/7 với policy hiện tại. Không đổi timestamp, không thay oracle bằng fixture và không nới policy để ép demo thành công.

## Lượt xác nhận sau sửa — PASS

Khi Chainlink có round mới lúc 08:20, đã chạy lại cả hai nghiệp vụ qua nút trên web với model `deepseek-flash`, dữ liệu Fuji/Chainlink/LFJ và EVM thực tế. Không dùng replay hoặc mocked response.

| Nghiệp vụ | Kết quả | Source block | Receipt block trên fork | Gas | Thời gian POST → terminal |
|---|---|---|---|---|---|
| Thanh toán 0.01 USDC | CONFIRMED | 61403696 | 61403708 | 356264 | 53.13 giây |
| Hoán đổi 0.000001 USDC → WAVAX | CONFIRMED | 61403720 | 61403732 | 453082 | 52.10 giây |

- Payment job `judge_75bb800d642d4088be6aca6281569384`, tx `0x89a2b4b91c223318ecd93187ced28638b2afc24d3d6a7bf72062951023e3601b`: người nhận thực nhận 10000 base units = 0.01 USDC.
- Swap job `judge_c088790158a847fd80f41c1e6aa04f10`, tx `0x8e8703b9315c5a19c1baabc8332a5698ccf4ed0f4858641b2616b768440bd2d8`: treasury giảm 1 USDC base unit, tăng 13266545691051 WAVAX base units.
- Hai lượt đều Risk PASS, ITAG PASS, proof VERIFIED; exact signed preflight dùng đúng giao dịch đã ký và không có simulation overrides.
- 24/24 panel module có dữ liệu thật theo stage; prompt, intent và tx hash hiển thị khớp response. Chưa chạy thì không có data; không hiển thị JSON trong panel.
- Timeline đúng thứ tự Owner → AI → Builder → Simulation → Risk → ITAG → Proof → SDE → Attestation → Exact Preflight → Outcome. Receipt dùng bằng chứng Outcome/Reconciliation, không tạo thêm stage giả. Shield kiểm tra lời gọi xuyên suốt.
- Mỗi lượt chỉ có một POST thành công, F5 giữa lượt chạy khôi phục cùng job. Lịch sử hiển thị đúng cả hai lượt.
- Khoảng cách GET quan sát trung vị 1.026 giây và 1.023 giây. Các bước nhanh có thể hoàn tất trong cùng snapshot; không kéo dài animation để giả tiến độ.
- 6/6 bản xem trước tấn công khớp nghiệp vụ; không gọi worker hoặc giả kết quả phát hiện tấn công.
- Không có lỗi JavaScript. Kiểm tra chiều rộng 1440×900 và 390×844 không có overflow ngang toàn trang.

**Hai receipt này thuộc Anvil fork, không phải public Fuji receipt; không gắn link explorer.** [Kết quả máy đọc](judge-ui-flow-20261121.json) lưu thêm dữ liệu receipt, proof, thời gian và kiểm tra panel. Bản đầy đủ nằm trong `data/judge-ui-acceptance/report.json`; dữ liệu job riêng nằm cạnh file báo cáo. Các lượt trước sửa và lượt nguồn giá không hợp lệ được giữ trong `before-itag-fix/` và `oracle-window-unavailable/`.

Chạy lại có kiểm soát bằng:

```powershell
python -u tools/quality/check_judge_workflow_ui.py --wait-oracle
```

Lệnh này tạo tối đa hai job live cố định và dùng quota hiện hành. Chờ nguồn giá chỉ phục vụ lịch kiểm tra; worker vẫn tự đọc và kiểm chứng lại dữ liệu trước khi cho phép ký. Không tự chạy lại job thất bại.

Các thay đổi hiện ở local, chưa push hoặc triển khai lên VPS.

Sau kiểm tra, local launcher được đặt giới hạn IP 18 lượt/giờ để sáu job QA không khóa các lượt demo thủ công tiếp theo; visitor quota vẫn 6/ngày. Production defaults và limiter backend không thay đổi. Backend local được khởi động lại khi không có job đang chạy; giữ nguyên SQLite và bằng chứng.
