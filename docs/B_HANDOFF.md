# Chạy Control Plane A với Execution Plane B

**LFJ update:** dùng SDK 1.2.0 cho enum adapter LFJ. Fuji deploy mặc định dry-run; luồng mock trong tài liệu này dành cho Local. Xem [LFJ integration](LFJ_FUJI_INTEGRATION.md) để biết route thật, fork evidence và rào cản định giá khiến Fuji SDE chưa cấp PDR.

A gọi B qua HTTP bằng SDK `treasury_contracts` v1.1. B dùng chain ID `31337` trên Anvil và `43113` trên Fuji. A đối chiếu chain, block, Vault và policy với RPC đã cấu hình. Chứng cứ `REAL_LOCAL_SIM` dành cho Local. Profile Fuji yêu cầu `FORK_SIM` khớp chain, canonical fork block và bytecode.

## Khởi động

1. Chạy `npm ci --ignore-scripts`, `npm run setup` và `uv sync --locked` từ root. Mở một terminal cho `npm run local`. B khởi tạo Anvil, deploy Vault và các mock token, rồi ghi profile local vào `.env`. API B mặc định ở cổng 8001.
2. Giữ cấu hình A trong `.env.local` theo các biến `PACEVANT_*` của [template](../.env.example). Đặt `PACEVANT_MODE=LOCAL`, `PACEVANT_B_URL=http://127.0.0.1:8001` và `PACEVANT_CHAIN_RPC_URL` bằng RPC Anvil của B. `PACEVANT_B_TOKEN` lấy từ `B_API_KEY`. Tạo hai token riêng cho operator và internal API, mỗi token ít nhất 24 ký tự.
3. Lấy địa chỉ relayer công khai từ `deployments/execution-local.json`. Dùng khóa **attestor test local** từ `.execution-data/local-keys.json` cho `PACEVANT_ATTESTOR_KEY`. Owner, relayer và attestor dùng ba địa chỉ khác nhau. Với Fuji, A giữ khóa attestor test riêng và đưa địa chỉ công khai cho B khi triển khai Vault.
4. Tạo mandate local từ [mandate mẫu](../fixtures/mock/mandate.json). Điền `chain_id`, `vault_address`, `owner`, `router`, `token_in`, `token_out` và `policy_hash` từ deployment. Lấy `expires_at` từ `policy_expires_at` trong API chain context của B. Mandate version thuộc A. A đối chiếu policy hash đã đăng ký với Vault. Các giới hạn off-chain do operator đăng ký từ mandate của owner.
5. Tạo oracle local đúng chain và Vault trong `PACEVANT_ORACLE_FILE`. JSON gồm `chain_id`, `vault_address`, `price_usdc_usd_e8`, `price_wavax_usd_e8`, `price_source` và `price_timestamp`. Fixture địa phương dùng `"TRUSTED_TEST_ORACLE"`, `"100000000"` USDC, `"2000000000"` WAVAX và Unix timestamp giây lúc cập nhật giá. A chặn giá cũ hơn 60 giây. Cập nhật giá ngay trước khi gọi workflow.
6. Chạy `uv run --locked --env-file .env.local python scripts/serve.py`. Gọi `POST /v1/workflows/start` với Bearer operator token, `goal` là `Buy WAVAX with 500 USDC` và `mandate_id` là `mandate_demo`. Dùng `GET /v1/workflows/{id}` để xem timeline và đối chiếu receipt. Dashboard trên cổng 8000 dùng profile `MOCK`. Với profile `LOCAL`, dùng API hoặc Swagger.

`npm run test:ab` khởi tạo deployment tạm, hai tiến trình API và credential ngắn hạn tự động. Bộ test chạy swap hợp lệ, replan từ 500 xuống 200 USDC, từ chối oracle cũ và chặn ký lần hai khi receipt đang chờ. [Ca kiểm thử A+B](../apps/execution-plane/tests/test_ab_integration.py)

## Điều kiện ký và xác nhận

- A tải manifest và scenario artifacts từ B qua SDK, đối chiếu hashes JCS, facts mô phỏng, và canonical fork block với RPC. A giữ nguyên build, evidence và domain theo wire contract.
- `POST /v1/approvals/attest` nhận `decision_id` với internal token. A đọc quyết định immutable, kiểm tra lại policy, nonce, signer, bằng chứng, giá và snapshot trước khi ký và gửi. Scope theo chain/Vault giữ chỗ cho tới khi receipt kết thúc hoặc xác nhận approval đã hết hạn. Idempotency key giữ nguyên khi retry.
- A đối chiếu receipt với RPC và kiểm tra hiệu ứng token, block, gas và địa chỉ relayer. Phí ngày là các receipt của workflow đã đối chiếu trong DB A, quy đổi bằng giá oracle hiện tại. Phí giao dịch kế tiếp là ước tính từ gas mô phỏng và gas price RPC. Hạn mức USDC theo UTC lấy từ Vault.
- Khi trạng thái `SUBMITTING` còn chờ hash, tra B bằng khóa `execute-<decision_id>`. Sau khi có hash, chạy `uv run --locked --env-file .env.local python scripts/recover_submission.py <workflow_id> <tx_hash>`. CLI đối chiếu receipt đúng decision/build/chain trước khi cập nhật trạng thái.

Các schema và golden vector dùng chung nằm ở [contracts-api](../packages/contracts-api/README.md) và [fixtures](../fixtures/eip712_golden). Fuji cần nghiệm thu riêng với deployment, attestor test và receipt trên mạng Fuji.
