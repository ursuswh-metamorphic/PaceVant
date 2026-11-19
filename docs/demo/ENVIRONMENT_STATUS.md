# Trạng thái môi trường demo — cập nhật 19/11/2026

**Không còn biến bắt buộc nào trống cho bước chuẩn bị Fuji.** Lần kiểm tra read-only doctor đã trả `configuration_ready=true`, đúng chain 43113, ba vai trò và historical read hợp lệ. V2 vẫn `NOT_DEPLOYED`: chưa có giao dịch Fuji V2 nào được gửi.

Tài liệu chỉ ghi tên biến/trạng thái; không chứa private key/token hoặc địa chỉ ví cá nhân. Kiểm tra lại cấu hình bằng `uv run --locked python scripts/treasury.py doctor --network fuji`; thêm `--live` nếu muốn đọc RPC.

## Đã tự điền theo ủy quyền của người dùng

Người dùng cho phép tự điền những phần có thể tạo/chọn cục bộ. Đã tạo khóa attestor test riêng trong `.env`, suy ra địa chỉ công khai và điền sáu thông số demo:

| Biến | Giá trị / trạng thái |
|---|---|
| `PACEVANT_ATTESTOR_KEY` | Đã tạo cục bộ, giữ kín |
| `B_FUJI_ATTESTOR_ADDRESS` | Đã suy ra từ khóa attestor |
| `TREASURY_MAX_RELATIVE_LOSS_BPS` | `300` = 3% |
| `TREASURY_MAX_FIXED_LOSS_USD` | `0` |
| `TREASURY_ORACLE_BAND_BPS` | `100` = 1% |
| `TREASURY_POSTCONDITION_TOLERANCE_BPS` | `40` = 0,4% |
| `TREASURY_SESSION_RISK_LIMIT_USD` | `10` |
| `TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD` | `20` |
| `TREASURY_OWNER_POLICY_APPROVED` | `true`, bộ demo đã được ủy quyền chọn |

Đây là cấu hình demo testnet, không phải lựa chọn risk appetite cho tiền thật. Báo cáo cũ ghi các biến còn trống/approval false là checkpoint lịch sử. Fixture LOCAL vẫn giữ `TEST_ONLY`; Fuji nhận `OWNER_APPROVED` từ cấu hình được ủy quyền. Đặt approval trong env không tự deploy hoặc gửi giao dịch.

## Đã có và giữ nguyên

Các khóa owner/relayer, RPC và token dịch vụ cũ được giữ nguyên. `B_FUJI_OWNER_PRIVATE_KEY` dùng cho deployment/gia hạn trên máy quản trị, `B_FUJI_RELAYER_PRIVATE_KEY` cho B và `PACEVANT_ATTESTOR_KEY` cho A.

`B_API_KEY`, `PACEVANT_OPERATOR_TOKEN`, `PACEVANT_INTERNAL_TOKEN` khác nhau và đủ độ dài. Không cần LLM API key, tài khoản database hoặc kết nối MetaMask cho demo hiện tại. RPC public không đòi API key riêng.

Giá controlled oracle vẫn 1 USD/USDC và 20 USD/WAVAX. Session 3.600 giây, oracle age 60 giây, confirmations Fuji 2. `TREASURY_MAX_WAVAX_PER_SWAP=0` giữ chiều bán bị khóa có chủ đích; muốn demo chiều WAVAX→USDC cần chọn cap dương.

## Phần nào có thể cần thao tác bên ngoài?

- Owner/relayer đã có test AVAX ở lần kiểm tra trước. Nếu thiếu gas khi deploy/thực thi, nhận thêm từ [faucet Avalanche](https://build.avax.network/console/primary-network/faucet) hoặc ví test khác. Xem địa chỉ công khai bằng doctor trên máy. Attestor ký offline nên không cần AVAX.
- Nếu public RPC bị rate limit hoặc thiếu historical state để fork, lấy HTTPS RPC thích hợp và cập nhật `B_FUJI_RPC_URL`. Hiện không thiếu RPC credential bắt buộc.
- Không cần faucet USDC/WAVAX: deployment mint mock tokens cho demo.

## Chạy local/deploy backend không cần Node.js

Backend đã chuyển sang Python gọi native Forge/Anvil. Máy development cần Foundry v1.7.1 trên PATH hoặc `.tools/foundry`; dùng `scripts/bootstrap.py` để cài OpenZeppelin. Xem [Render/VPS và Docker](../deployment/PYTHON_BACKEND_RENDER_VPS.md).

Khi đưa backend lên Render/VPS, dùng runtime env riêng từ `deploy/runtime.env.example`, chỉ cấp attestor/relayer keys và service tokens. Không upload root `.env` chứa owner key. Container lấy public owner từ manifest rồi kiểm tra on-chain.

```powershell
uv run --locked python scripts/treasury.py deploy --network fuji
uv run --locked python scripts/treasury.py serve --network fuji
# Terminal khác:
uv run --locked python scripts/treasury.py demo --network fuji
```

Deployment tạo manifest thật `deployments/treasury-fuji-v2.json`; đó là đầu vào cần thiết trước khi chạy container Fuji. Xem [hướng dẫn demo](AVALANCHE_FUJI_DEMO.md) và [luồng hệ thống](../CURRENT_SYSTEM_FLOW.md).
