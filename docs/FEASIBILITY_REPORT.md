# Báo cáo khả thi — Avalanche UniHack Integration PoC

Ngày đánh giá: 12/11/2026, giờ Việt Nam. Phạm vi: PoC kỹ thuật, không production.

## 1. Mục tiêu

Kiểm tra liệu ứng dụng AI Agent Security có thể dùng Avalanche làm nơi giữ trạng thái và cưỡng chế chính sách chi tiền. Agent trong PoC chỉ mô phỏng quyết định; quyền chuyển tiền do contract kiểm tra thực sự.

## 2. Kiến trúc

React/Vite đọc Fuji RPC; ví Core/MetaMask ký giao dịch. CLI TypeScript hỗ trợ deploy và đóng vai agent. Demo EOA có AvalancheStorage và AgentTreasuryGuard; luồng smart account mới có `UniHackSmartAccount` làm owner của bộ storage/treasury riêng, relay HTTP và EntryPoint v0.8. Owner EOA ký UserOperation EIP-712, agent chỉ propose, account batch approve+execute. Xem [ARCHITECTURE.md](ARCHITECTURE.md), [SMART_ACCOUNTS.md](SMART_ACCOUNTS.md).

## 3. Công nghệ thực chạy

Windows, Node 24.21.0, npm 11.19.0, Git 2.56.0, Hardhat 3.21.2, Solidity 0.8.38/Cancun, OpenZeppelin 5.6.1, viem 2.57.19, React 19.3.1, Vite 8.3.8, TypeScript 7.0.2, Playwright 1.65.0 với Chrome đã cài. Package-lock khóa phiên bản.

## 4. Đã hoàn thành

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Nghiên cứu Team1, starter code và Avalanche | PASS | [RESEARCH.md](RESEARCH.md) |
| Fuji RPC chain/block/balance/latency | PASS | [network.json](../evidence/network.json), chain 43113 |
| Compile Solidity Cancun | PASS | `npm run compile` |
| Unit tests chức năng và bảo mật | PASS | 41 pass, 0 fail, gồm 14 tests ERC-4337; [unit-results.json](../evidence/unit-results.json) |
| Deploy hai contract lên local EVM | PASS | Receipt và runtime bytecode khớp artifact |
| Local E2E A–E | PASS | [e2e-local.json](../evidence/e2e-local.json), chain 31337 |
| Deploy hai contract lên Fuji | PASS | [fuji.json](../deployments/fuji.json); chain 43113, receipt success và bytecode khớp artifact |
| Fuji E2E A–E | PASS | [e2e-fuji.json](../evidence/e2e-fuji.json); giao dịch success/reverted thực tế |
| Smart account ERC-4337 và AA1–AA7 trên Fuji | PASS | [aa-e2e-fuji.json](../evidence/aa-e2e-fuji.json), [aa-verify-fuji.json](../evidence/aa-verify-fuji.json); nonce 3, storage 1, proposal Executed |
| Đọc lại độc lập receipt/code/state/log Fuji | PASS | [verify-fuji.json](../evidence/verify-fuji.json); storage 2, proposal #0 Executed |
| UI desktop/mobile và luồng owner/agent | PASS | 4 tests gồm EOA, Fuji và AA EIP-712/relay; [ui-results.json](../evidence/ui-results.json), wallet adapter local |
| UI đọc Fuji thật | PASS | [TEST_RESULTS.md](TEST_RESULTS.md), [ui-results.json](../evidence/ui-results.json); storage, địa chỉ và ProposalExecuted |
| Build frontend và typecheck | PASS | Đã chạy, exit code 0 |
| UI bản build qua preview đọc Fuji | PASS | [production-ui.json](../evidence/production-ui.json), EOA storage 2, AA storage 1/nonce 3, relay kết nối, không có page error |
| Khóa không lọt source/bundle | PASS | [secret-scan.json](../evidence/secret-scan.json); .env Git ignore, số file và thời điểm trong JSON |

## 5. Chưa hoàn thành

| Hạng mục | Trạng thái | Lý do |
|---|---|---|
| Ký bằng extension Core/MetaMask thật | NOT TESTED | Playwright dùng adapter chuyển yêu cầu vào node local |
| Explorer source verification | NOT TESTED | Đã deploy, runtime bytecode xác minh qua RPC; chưa xác minh source trên explorer |
| Kiểm UI Explorer | BLOCKED | Web reader không truy cập được hai URL transaction; đã cung cấp liên kết để mở thủ công |
| Audit độc lập, kiểm tải, production | NOT TESTED | Ngoài phạm vi PoC |
| Dependency audit sạch | FAIL | Audit tìm thấy advisory Zod; xem rủi ro bên dưới |

PASS nghĩa đã thực chạy và có kiểm tra; FAIL nghĩa đã chạy nhưng điều kiện kiểm tra thất bại; BLOCKED là thiếu điều kiện bên ngoài; NOT TESTED là chưa chạy. Không coi local EVM là Fuji deployment.

## 6. Khó khăn và cách xử lý

Web reader không đọc được Team1; fetch trực tiếp HTTP 200 cho phép đọc catalog và từng file starter. Hai unit test event ban đầu dùng mặc định khoảng block nên không thấy event cũ; đã chỉ định fromBlock và chạy lại pass. Hardhat CLI node dùng network riêng, vì vậy cấu hình named network `pocLocal` được truyền rõ để nhận receipt của giao dịch cố ý revert. Kiểu viem cần nạp các declaration artifact mà Hardhat sinh ra. UI ban đầu chỉ báo “reverted”; đã decode custom error để hiển thị lý do.

Browser plugin lỗi khởi tạo `node:process`. Cài Chromium Playwright gặp ECONNRESET/DNS; dùng Chrome headless đã cài, không dùng profile cá nhân, kiểm thử thành công. Các vấn đề này đã được xử lý cho local; không biến lỗi tải browser thành lỗi blockchain.

Khi tiếp tục Fuji, owner nhận 0.05 test AVAX nhưng agent ban đầu chưa có gas. Lần E2E đầu dừng ở bước agent, được giữ trong `e2e-fuji-attempt1.json`. Đã chuyển 0.0005 test AVAX từ owner sang agent đã kiểm soát, rồi E2E A–E pass. Thêm preflight agent balance để tránh khởi chạy khi thiếu vốn.

Fuji RPC giới hạn log 100 block/request và trả HTTP 429 với Retry-After 60; browser cũng gặp CORS. Đã chia lô log, không quét trước block deploy, dùng cache tăng dần, gom batch và tránh refresh đồng thời. UI dùng proxy cùng origin của Vite tới RPC Fuji thật và tôn trọng thời gian chờ rate limit. Không thay dữ liệu thật bằng mock khi RPC lỗi.

## 7. Gas đo thực tế

Đây là gas receipt thực đo ở từng mạng; không giả định gas local bằng Fuji:

| Thao tác | Local gas | Fuji gas |
|---|---:|---:|
| Deploy AvalancheStorage | 212119 | 212119 |
| Deploy AgentTreasuryGuard | 847896 | 847896 |
| Storage 0 → 1 | 47419 | 47419 (lần đầu) |
| Storage 1 → 2 | — | 30319 (lần cuối) |
| Agent tạo proposal đầu tiên | 122043 | 122043 |
| Owner approve | 62620 | 62620 |
| Owner execute | 55800 | 58600 |
| Nạp native token | 22491 | 22491 |
| Proposal vượt hạn mức (revert) | 28679 | 75000 |
| Recipient không cho phép (revert) | 26481 | 75000 |

Gas là đơn vị lượng công việc. Phí thực tế = receipt.gasUsed × receipt.effectiveGasPrice, đơn vị wei; 10^18 wei = 1 AVAX. Receipt Fuji của lần chạy này có effectiveGasPrice 160 wei/gas. Tổng phí có tính cả lần demo đầu được ghi chính xác trong [TEST_RESULTS.md](TEST_RESULTS.md) và `evidence/fuji-cost-summary.json`; không chuyển sang VND/USD hay cam kết giá tương lai. Storage từ 0 sang khác 0, giá trị cũ khác, proposal ID và quy tắc mạng có thể làm gas khác nhau. Không có tiền thật hoặc dịch vụ trả phí đã dùng.

## 8. Contract được lưu và chạy như thế nào

Compiler biến Solidity thành bytecode. Giao dịch deploy đưa bytecode và tham số constructor vào mạng. Khi thành công, receipt có địa chỉ contract. Contract lưu code và trạng thái tại địa chỉ đó; giao dịch tiếp theo gọi function sẽ được mạng thực thi. Ví phải trả gas để ghi; đọc thông thường dùng eth_call không cần ký và không phát sinh giao dịch trả gas. RPC vẫn có giới hạn truy cập.

## 9. Ứng dụng giao tiếp với Avalanche

Viem mã hóa lời gọi theo ABI, gửi JSON-RPC. PublicClient đọc chain/block/storage/receipt/log; UI dùng route proxy cùng origin tới Fuji để tránh CORS. WalletClient nhờ ví ký; khóa không có trong React. CLI dùng secret môi trường cục bộ. UI chờ receipt success rồi đọc lại, không dựa vào nút bấm hoặc hash để khẳng định thành công. Explorer là công cụ đối chiếu dữ liệu mạng sau deploy, không thay thế kiểm tra receipt bằng code.

## 10. Khả thi cho AI Agent Security

Đã bổ sung smart account thật: EntryPoint v0.8 xác thực chữ ký EIP-712/nonce/prefund rồi account thực thi batch. Local và Fuji đã chứng minh replay/agent-signature/calldata-tampering bị validation từ chối; failed batch rollback dù outer receipt success. Relay là implementation demo giới hạn, chưa phải public production bundler. Không có session keys/recovery/paymaster; agent vẫn cần owner duyệt. Kết quả và phí: [SMART_ACCOUNT_RESULTS.md](SMART_ACCOUNT_RESULTS.md).

Có bằng chứng local rằng agent có thể đề xuất nhưng không tự chi tiền; owner phải approve và execute. Contract từ chối vượt limit, recipient không cho phép, caller không đúng, proposal đã thực thi, thiếu balance và policy không còn hợp lệ. Thử recipient độc hại cũng không chuyển lặp được. Không cần LLM để kiểm tra ranh giới quyền; LLM sau này chỉ tạo nội dung đề xuất.

## 11. Rủi ro còn lại

- Owner là điểm tin cậy: có thể thay policy, mất khóa hoặc renounce làm khóa quỹ. Cần multisig, chuyển quyền hai bước, pause/recovery trước dùng thật.
- Hạn mức hiện là mỗi giao dịch; không có hạn mức ngày/tổng, expiry, cancel hoặc thu hồi một approval riêng. Nhiều đề xuất có thể cộng thành số lớn nếu owner phê duyệt liên tiếp.
- Policy được kiểm theo giá trị hiện tại; thay rồi khôi phục policy có thể làm đề xuất cũ hợp lệ lại. Cần version policy/approval invalidation nếu sản phẩm yêu cầu.
- Secret CLI dạng môi trường/file chưa phải custody production. Cần quản lý khóa riêng, xác thực API, giới hạn tốc độ và tránh prompt injection nếu bổ sung LLM.
- Hai khóa test được người dùng cung cấp đã xuất hiện trong chat. Chỉ dùng cho PoC không có giá trị; phải thay ví trước mọi mục đích giữ tài sản. Không lưu khóa trong báo cáo/source/bundle; `.env` được Git ignore.
- UI scan event từ block deploy phù hợp PoC ngắn; cần indexer/pagination khi chạy lâu. RPC outage/rate limit, stale data, endpoint giả và extension độc hại cần xử lý vận hành.
- Npm audit hiện trả 5 high trong toàn cây, cùng gốc advisory [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) ở Zod 3.25.76. `--omit=dev` vẫn báo 1 high qua optional peer abitype/viem. Không coi là sạch chỉ vì nằm trong toolchain. Hardhat hiện yêu cầu Zod 3; không dùng force-upgrade Zod 4 trái API. Cần bản dependency tương thích đã vá hoặc tách dependency cây frontend trước production.
- Build hiện có chunk khoảng 570 kB và cảnh báo externalize `node:worker_threads` trong nhánh thư viện ox; UI dev và bản build qua preview đã đọc storage/events/nonce Fuji thành công, không có page error trong bài kiểm tra. Chưa kiểm chứng mọi tính năng thư viện hoặc tải production.
- Chưa audit độc lập; không khẳng định contract an toàn production từ số lượng test.

## 12. Kiến trúc hackathon đề xuất

Giữ Fuji C-Chain; không tạo L1 riêng. Một agent service nhỏ chỉ được ký propose; owner dùng UI riêng. Thêm cancel/expiry, tổng hạn mức ngày, pause và log lý do của agent ngoài chain (chỉ hash bằng chứng lên chain nếu cần). Dùng multisig làm owner khi có thời gian. Tập trung demo một hành vi được phép và ba hành vi bị chặn bằng receipt/explorer, cùng video 2–3 phút và repository rõ cách chạy.

## 13. Kết luận

**GO cho MVP UniHack trên Fuji.** Hai contract đã deploy, receipt success, runtime bytecode khớp artifact; storage được cập nhật thật; proposal #0 được agent tạo, owner approve/execute; C–E bị revert đúng kỳ vọng và không tạo proposal mới. Đọc lại độc lập xác nhận state và events. Xem [TEST_RESULTS.md](TEST_RESULTS.md) cho toàn bộ địa chỉ, hash và số đo.

**NO-GO cho dùng tiền thật/production.** Chưa audit độc lập, dependency audit còn FAIL, ký bằng extension thật và Explorer source verification chưa thực hiện. Bước tiếp theo là người dùng thử owner UI bằng Core/MetaMask, mở các liên kết Explorer, dùng ví mới trước phát triển tiếp và bổ sung daily budget/cancel/expiry/pause/multisig. Vite dev/preview là môi trường demo; hosting khác phải cấu hình proxy RPC, không chỉ upload static files.
