# Avalanche Integration: kết quả và kịch bản demo

Kiểm chứng ngày **19/11/2026 (giờ Việt Nam)**, cho [Team1 Vietnam UniHack](https://team1vn.xyz/). Trang cuộc thi công bố Avalanche Integration **25/100 điểm** và chấp nhận Fuji. Không có tiêu chí chi tiết công bố về số oracle phải tích hợp; thiết kế dưới đây ưu tiên hành vi có thể trình diễn và đối chiếu.

## Thay đổi hoàn thành

1. Sửa SyntaxError của reader cũ khiến import API thất bại.
2. Tách bounded RPC, oracle adapters, cache/rate-limit service và routes. Observer chạy riêng chỉ cần operator token; không phụ thuộc triển khai B.
3. Thêm hai Chainlink feeds từ registry chính thức và Pyth AVAX, giữ Witnet kèm trạng thái lỗi rõ ràng.
4. Thêm PolicyVault view và receipt evidence: policy, ngân sách UTC, token đúng địa chỉ Vault, SwapExecuted, nonce đã dùng và phí AVAX.
5. Dashboard có explorer/registry links, tuổi và heartbeat từng feed, BigInt cho balance/round, export JSON kèm observation hash; responsive cho điện thoại.
6. CI kiểm tra toàn bộ A tests/lint/format bên cạnh pipeline B hiện có.

## Lượt đọc Fuji thật

Artifact: [fuji-oracle-readonly-live.json](../evidence/fuji-oracle-readonly-live.json).

- Thời điểm: **2026-11-19 02:50:27 +07:00** / 2026-11-18 19:50:27 UTC.
- Block: **61298356**, hash `0xe36feb93d7ae7520360da67e08aaaa592c568484e59cce32382b055b992baf93`.
- [Đối chiếu block trên explorer](https://explorer-test.avax.network/c-chain/block/61298356).
- Địa chỉ đọc: zero address công khai để kiểm tra; **không phải ví hay treasury của người dùng**.
- Thời gian lượt đọc: khoảng 5 giây, mọi balance/call pin cùng block và recheck hash.
- Snapshot thu qua RPC thật, không có fallback số dư/giá giả.

| Nguồn Fuji | Kết quả tại snapshot | Đánh giá cho demo |
|---|---|---|
| Chainlink AVAX/USD | $6.95722562; tuổi 364 giây; heartbeat 600 giây | Trong heartbeat, dùng trình diễn nguồn oracle |
| Chainlink USDC/USD | $0.99975185; tuổi 70608 giây; heartbeat 86400 giây | Trong heartbeat nhưng gần 20 giờ; cần ngưỡng giao dịch riêng |
| Witnet Price-AVAX/USD-6 | ERC-2362 status 404, updated_at=0 | Chưa có cập nhật hợp lệ cho truy vấn này, không hiển thị giá |
| Pyth AVAX/USD lưu trên Fuji | $8.87482253; publish 2026-03-08; tuổi khoảng 255 ngày | STALE; đọc contract không tự cập nhật pull feed |
| CoinGecko Demo | NOT_CONFIGURED | Tùy chọn off-chain, chưa kiểm chứng live bằng key |

Đây là trạng thái của **các địa chỉ/feed ID cụ thể trong artifact**, không phải kết luận mọi feed cùng nhà cung cấp đều hoạt động hay hỏng. Registry URLs và addresses được ghi trong [hướng dẫn](FUJI_WALLET_MARKET_READONLY.md).

Chainlink hiện phù hợp nhất để trình diễn read-only từ dữ liệu kiểm chứng. Nếu tiếp tục Pyth cần lấy payload cập nhật phù hợp contract, kiểm tra phí rồi submit update có chủ đích trên testnet. Chronicle có Fuji AVAX/USD theo Avalanche docs, cần kiểm tra quyền đọc/heartbeat trước khi thêm. Không tăng số nhà cung cấp chỉ để có logo.

## Demo gắn với kiến trúc A/B

| Bước trình diễn | Bằng chứng | Trạng thái |
|---|---|---|
| Đọc ví Fuji và oracle | Block hash, contract address, round/timestamp, JSON tải xuống | Đã đọc live qua CLI và dashboard |
| Kiểm tra tài sản và mandate Vault | usdc/wavax của Vault, policy hash, owner/attestor, budget UTC | Code + transport tests; cần địa chỉ PolicyVault Fuji |
| Kiểm tra một lần execute | Receipt, SwapExecuted, evidenceRoot, usedNonce, gas AVAX | Code + transport tests; cần tx hash Fuji đúng deployment |
| A đánh giá, PDR ký, B thực thi và monitor | Workflow + EIP-712 + pre/post guards | Hệ thống A/B hiện có; kiểm thử hồi quy local Anvil, không đồng nghĩa swap Fuji live |
| Dùng oracle live để APPROVE | Policy giá theo đúng token, ràng buộc block/evidence, recheck trước ký | Chưa nối; mọi observation hiện usable_for_decisions=false |

Để tăng sức thuyết phục cho Avalanche Integration, phần tiếp theo có giá trị nhất là **một vòng A → PDR → PolicyVault → receipt/monitor thật trên Fuji**. Cần deployment manifest đúng phiên bản, địa chỉ Vault/token/router, thanh khoản/adapter phù hợp và ví test đã nạp gas. Sau đó trình diễn cả giao dịch hợp lệ và nonce replay/policy guard bị chặn, lưu receipt và đối chiếu explorer. Không dùng receipt ERC-4337 cũ để đại diện PolicyVault hiện tại.

## Kiểm tra và phản biện

- A: **55 tests passed** trên Windows; Ruff check/format và JavaScript syntax check passed.
- Dashboard: đọc live, auth lỗi hiển thị đúng, download JSON được và hash kiểm tra lại khớp. Ở viewport 390px, document width = scrollWidth = 375px, không tràn ngang.
- Unit/transport tests cố định dữ liệu để tái hiện chain mismatch, RPC/ABI lỗi, reorg, stale/future update, invalid Chainlink round, malformed receipt, cache, rate/concurrency limit, deadline và header API-key isolation.
- Snapshot và JSON tải từ dashboard đã kiểm tra lại Keccak/JCS. Đây là kiểm tra tính toàn vẹn artifact, chưa phải chữ ký tin cậy.
- Vault/receipt getter đã đối chiếu với interface PolicyVault.sol. Kiểm tra ABI thành công không thay thế xác thực deployment.
- Một RPC và cache theo process đủ cho demo loopback; production cần chính sách xác minh RPC, registry/implementation governance, ngưỡng giá theo chiến lược và limiter dùng chung.
- Giữ nguyên trust boundary: LLM đề xuất; SDE/risk/evidence deterministic; attestor ký; PolicyVault cưỡng chế cuối cùng. Module quan sát không tự tạo quyền giao dịch.
