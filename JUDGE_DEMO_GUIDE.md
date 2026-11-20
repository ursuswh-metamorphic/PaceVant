# PaceVant — hướng dẫn giám khảo và video 3 phút

Giao diện mặc định có ba tab: **Live Demo**, **Security & Policies**, **History**. Không cần wallet, tài khoản, credential, AVAX hay USDC. Bản build React/TypeScript dùng static assets; backend giữ nguyên pipeline PACE/PGS.

## Hai chế độ phải phân biệt

* **Fuji fork:** backend lấy state/token/DEX/oracle từ Avalanche Fuji, tạo fork Anvil riêng và các role tạm. Proposal dùng model thật; simulation/Z3/attestation/preflight/contract execution/receipt là thực trên fork. Không tiêu tiền công khai, không có link explorer public cho hash fork.
* **Verified replay:** đọc bằng chứng đã ghi lại từ một workflow fork thật, có SHA-256 được pin. Không chạy lại model/EVM và không tạo giao dịch mới. UI hiển thị recorded time/replay banner. Không tự chuyển live error thành replay success.

Public Fuji Operator Mode hiện chưa được nghiệm thu: Owner còn cần triển khai/fund/ký manifest contract MVP mới. Judge API không nhận public Owner/Attestor/Relayer keys và không expose các API admin/raw execution. Historical public V2 swap là evidence khác, không phải acceptance payment mới.

## Kịch bản quay ở 1440×900 hoặc 1920×1080

1. **0:00–0:20:** mở Live Demo; nêu bài toán AI chỉ đề xuất trong quyền Owner, các chỉ số lấy từ source/run thực. Overview ghi rõ on-chain read hay recorded snapshot; “worker available” không bảo đảm mọi dependency đạt điều kiện.
2. **0:20–1:10:** bấm **Run Payment Demo**: exact **0,01 USDC** đến EOA được duyệt trong fork. Chỉ các stage events thật mới đổi màu pipeline. Mở actual receipt, economic risk debit và full evidence.
3. **1:10–2:00:** bấm **Run Swap Demo**: exact **0,000001 USDC → WAVAX**, approved LFJ V1; input cực nhỏ phù hợp pool Fuji mỏng. Xem quote/Chainlink/Phi và receipt.
4. **2:00–2:30:** bấm **Test Security Guard**. Server kiểm reverse route hoặc một payee không được duyệt cố định nếu market thay đổi; verdict đến từ cùng pipeline, không hardcode Rejected. Nếu model/oracle không sẵn sàng thì ghi unavailable, không giả rejection.
5. **2:30–3:00:** mở Security & Policies, expand Z3/attestation; mở History/details. SAT chỉ dùng cho satisfiable assumptions; violation queries phải UNSAT. Z3 chạy off-chain, không phải ZK proof.

Nếu một run tốn nhiều thời gian, có thể cắt đoạn chờ trong video, không sửa thứ tự evidence hay giả animation. Nếu Chainlink/RPC/model hiện unavailable, chọn **View verified demo** rõ nhãn, không nói đó là live run vừa thực thi. Cả ba scenario đã có recorded evidence thật; guard recording bị builder từ chối vì quoter chọn route ngoài approved V1, chưa đi đến Z3/signing. Lần swap API mới nhất qua exact preflight nhưng chưa có receipt được giữ UNKNOWN; recording swap CONFIRMED là checkpoint trước. Xem `docs/audit/judge-api-acceptance.json`.

## Retry và giới hạn

Request key/scenario được persist trước POST. Double click không tạo job mới; reload khôi phục key/job trong cùng tab và cookie visitor. Timeout giữ request, query trước khi retry; không tự gửi từ polling. Không thay amount/recipient/deadline của workflow đã accepted. Pending/unknown không đổi thành success/failure tùy ý.

Mặc định 6 runs/visitor/ngày, 6 starts/IP/giờ, 30 runs toàn hệ thống/ngày, một job nặng tại một thời điểm, timeout 240 giây. Trạng thái Busy không spawn queue/subprocess vô hạn. Quota là SQLite durable, không chỉ disabled button. Quota/rate bảo vệ best-effort anonymous demo, không là user identity/KYC; Nginx thêm IP rate limiting.

HTTPS cần cho secure visitor cookie và browser request identity. HTTP localhost chỉ cho QA; IP HTTP smoke có thể xem frontend/read-only/replay nhưng không gửi operator secrets. Không đưa credentials vào source/bundle.

## Evidence và logs

Drawer hiển thị intent, model explanation, ITAG, measured effects, oracle, risk, solver queries, Phi, attestation metadata, exact signed preflight và receipt nếu workflow đã đi qua các gate đó. Bước chưa chạy hiển thị Not run/Unavailable. No fabricated chain-of-thought.

Giao diện không hiển thị Owner kill switch cho giám khảo. Admin/operator vẫn ở API authenticated cũ và không được public Nginx judge site proxy. Người vận hành xem `journalctl -u pacevant-judge`, readiness/config và history visitor để chẩn đoán; không yêu cầu giám khảo xử lý cấu hình blockchain.
