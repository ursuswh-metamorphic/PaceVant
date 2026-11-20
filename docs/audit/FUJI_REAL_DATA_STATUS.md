# Kiểm tra thực trạng dữ liệu Fuji — 20/11/2026

> **DOC STATUS: HISTORICAL_AUDIT - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](../AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](../README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

Lượt rà soát mới nhất: 20/11/2026, đối chiếu public Fuji tại block **61345272**. Phạm vi: composition/config, planning/alignment, oracle/portfolio, risk/proof/signing, builder/simulation/evidence/relayer/storage, Solidity, frontend và deployment. Chạy kiểm tra tập trung; không gửi giao dịch mới, không gọi lại Groq, không chạy full suite. Bằng chứng chỉ đọc mới nhất: [fuji-reaudit-validation.json](fuji-reaudit-validation.json). Báo cáo này không phải audit bảo mật độc lập hoặc bảo đảm đã tìm mọi lỗi.

## Kết quả

Hệ thống đã triển khai và thực thi workflow thật trên Avalanche Fuji chain 43113. Receipt block 61340481 vẫn canonical, status 1, sender khớp relayer. Backend hiện trả mode FUJI, execution in-process, planner Groq; API không có token trả 401. Ba keys khớp vai trò, **74 tên biến** `.env`/template khớp nhau, gồm hai biến Demo User chưa tích hợp. Direct Chainlink đọc được rounds trong giới hạn tuổi ở thời điểm kiểm tra. Native runtime bytecode của PolicyVault/LFJSwapAdapter khớp compilation hiện tại sau khi loại các vị trí immutable; các cấu hình immutable/route được Chain kiểm riêng. Owner key và Demo User key không được đưa vào môi trường serving qua launcher.

Kiểm tra mới nhất: **58 Python tests pass** (architecture, Chainlink provenance/freshness, V2 gates, proof); **4 Solidity tests pass** (LFJ swap/allowances, exact deltas/counters, replay/expiry, Phi rollback). Ruff, syntax của 9 frontend JS files và secret scan đều pass. Đây là kết quả chạy lại tập trung; full-suite 235 Python/60 Solidity là evidence của lượt trước, không chạy lại trong lượt này.

**Tại thời điểm kiểm tra, session đã hết hạn.** Policy còn active, vault không pause, relayer còn gas. Cần owner chạy `uv run --locked treasury renew-session --network fuji` rồi khởi động lại backend để chạy giao dịch mới. Đợt kiểm tra này không tự gia hạn. Health/doctor configuration OK và `treasury_issues=[]` chưa phản ánh đầy đủ session expiry; không dùng riêng các trạng thái đó để kết luận có thể ký/gửi ngay.

## Dữ liệu thực và giả định

| Phần | Thực trạng |
| --- | --- |
| Số dư, policy/session, gas, receipt | Đọc chain thật; vốn nằm trong vault, gas swap trả bằng ví relayer hệ thống |
| Quote/swap | Circle test USDC → Fuji WAVAX qua LFJ V1 thật; live manifest dùng LFJSwapAdapter |
| Oracle | Raw rounds Chainlink thật. Gán giá tham chiếu USDC/USD và AVAX/USD cho token testnet là giả định định giá của policy, không phải giá trị USD có thể quy đổi |
| Planner | Cấu hình Groq thật, có evidence lần chạy trước; bounded buy/sell templates, cache/quota. Không kiểm API Groq mới trong lượt này |
| Risk, Z3, ký, enforcement | Logic thực; không trả sẵn PASS/UNSAT. Phạm vi chứng minh bị giới hạn bởi mô hình và giả định giá |
| Baseline/final preflight | EVM thực trên Anvil fork; thay signer/gas cho process mô phỏng, không phải giao dịch public |
| Stress | Kịch bản giả định 20/200 bps; impersonate Circle minter và cấp token cho external actor chỉ trên Anvil rồi swap pool thật. Không phải biến động thị trường đã xảy ra |
| MOCK/LOCAL | Còn fixtures, mock tokens/adapter và nominal prices 1/20. Live profile hiện tại không dùng chúng. Lệnh deploy mặc định vẫn chọn mock nếu không chỉ định đúng adapter/profile |
| Observatory khác | Witnet/Pyth/CoinGecko chỉ tham khảo, không dùng ký live policy này; không kiểm lại availability từng nguồn trong lượt này |

Giới hạn triển khai: một treasury/operator, một chiều swap và route cố định; một số caps còn cố định trong code; chưa có agent hội thoại/tự học đầy đủ. Dịch vụ nhiều user/thu phí chưa triển khai theo phạm vi hiện tại. Render/VPS/Docker chưa được smoke trên host; cần native Anvil, persistent storage, manifest và cấu hình runtime không chứa owner key. Monitor dựa trên polling, chưa có background recovery/fee-bump hoàn chỉnh.

## Các điểm còn thiếu/cần sửa

1. **Session readiness chưa phản ánh trên UI/doctor.** `modules/portfolio/service.py:policy_issues` kiểm identity của session nhưng chưa kiểm thời gian/active/budget tại gate ban đầu; `operations/services.py:doctor` chỉ báo configuration/RPC/funding. `frontend/src/features/treasury/index.js` bật Run khi đọc treasury được, dù session có thể hết hạn. Proof/vault vẫn kiểm session nên đây không phải bằng chứng bypass thực thi, nhưng khiến UX báo sẵn sàng sai và có thể tốn một lượt planning/simulation vô ích. Session hiện tại có active flag true nhưng đã vượt expiresAt; cần phân biệt hai điều này.

2. **Chưa có ngưỡng kiểm tra quote lệch oracle theo cả hai chiều.** `modules/risk/service.py` có fair-min-output, loss và exposure gates; không có kiểm tra riêng cho đầu ra tốt bất thường. Quote 1 base unit input tại block kiểm tra trả 13192899717724 base units WAVAX; feed AVAX/USD lúc đọc là 7,034 USD. Định giá tham chiếu đầu ra cao hơn nhiều input, nên swap thành công trên pool này chưa chứng minh mô hình thị trường hợp lý. Không kết luận mọi positive deviation đều là lỗi hoặc bắt buộc phải chặn; owner cần định nghĩa mức cảnh báo/escalation phù hợp. Không tự thêm ngưỡng tùy ý hoặc đổi policy trong lượt review.

3. **Proxy timeout có thể cắt workflow hợp lệ.** Endpoint start chạy đồng bộ; CLI timeout 300s nhưng `frontend/nginx.conf.template` đặt 90s. Workflow Fuji đã có lượt mất hơn 90s. Khi host dùng proxy đó, client có thể timeout dù backend đã tiếp tục xử lý/gửi giao dịch. Cần cấu hình timeout đồng bộ hoặc chuyển sang background workflow API; không tự retry POST start khi chưa reconcile.

4. **CLI kiểm LFJ chưa theo live token mặc định.** `operations/lfj.py:preflight` tạo `LFJClient(w3)` nên dùng LFJ faucet USDC mặc định; deployment hiện tại dùng Circle USDC. Kết quả diagnostic của lệnh này không được dùng làm trạng thái sẵn sàng cho live route nếu chưa sửa lựa chọn token. Builder/simulator live lấy đúng token từ manifest, không mắc nhầm này.

5. **Vận hành còn giới hạn.** Các caps 500 USDC/swap, 1000/ngày, exposure 25%, chi phí tham chiếu 50 USD/ngày và hai replans còn nằm trong operator code. Có journal, nonce và polling recovery nhưng chưa có worker bền vững/HA/HSM/fee bump. Khóa attestor và relayer ở cùng backend process. Demo User mới lưu env, chưa có đăng nhập/cấp quyền/funding hay user treasury.

6. **Phân biệt code có mock với live đang dùng mock.** MOCK/LOCAL và deploy adapter mặc định `mock` vẫn tồn tại có chủ đích; source Chainlink policy chỉ chọn direct RPC provider và không fallback JSON nếu nguồn lỗi. `TRUSTED_TEST_ORACLE` vẫn có thể dùng với controlled profile khác. Lệnh `fuji-demo --setup` là đường setup Circle live; không coi mọi lệnh deploy/serve mặc định đều là demo real-data. Các cảnh báo blocked faucet trong tài liệu cũ thuộc route cũ; xem system design/runbook live để tránh trộn checkpoint.

Không tự thay source, giá, ngưỡng policy, gia hạn quyền hoặc deploy trong lượt rà soát này. Kết luận: **đã có live Fuji end-to-end evidence; chưa hoàn chỉnh về readiness UI, kiểm điều kiện giá và vận hành hosted.**

Vault hiện có 603 base units Circle USDC = 0,000603 USDC và 13192993554324 base units WAVAX. Vốn bootstrap rất nhỏ; demo lặp nhiều cần thêm Circle test USDC vào vault, giữ nguyên exposure/risk gates.

Xem [runbook live](../demo/FUJI_LIVE_END_TO_END.md) và [bằng chứng giao dịch đã chạy](../integrations/fuji-live-validation.json).
