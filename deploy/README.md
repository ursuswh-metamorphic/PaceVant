# Triển khai backend và frontend

Backend là Python + native Anvil, Solidity đã compile trong image build; frontend là static ES modules qua Nginx. Backend/Frontend có Dockerfile riêng và build context đều là repository root. Không cần Node trên server.

## Chuẩn bị một lần

1. Deploy contracts V2 Fuji từ máy quản trị theo [runbook](../docs/demo/AVALANCHE_FUJI_DEMO.md). Lệnh deploy gửi giao dịch thật trên testnet; serving container không deploy.
2. Lưu manifest tạo được thành `deploy/treasury-fuji-v2.json`. Đây là manifest public, không có private key. Kiểm tra đúng chain/vault/session/code hashes.
3. Copy `runtime.env.example` thành `runtime.env` (được Git ignore). Điền actual values, không dùng alias `${...}`. Chỉ đưa attestor/relayer keys lên server; owner key giữ ở máy quản trị. Risk settings phải khớp on-chain policy.
4. Cấp persistent volume `/var/data` và chạy một backend instance. Giữ SQLite, proof/audit, artifacts và relay journal qua restart; không xóa để xử lý giao dịch pending.

## VPS với Compose

```sh
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 backend
```

Compose đọc `deploy/runtime.env`, mount manifest read-only và volume `treasury-data`. Frontend tại http://127.0.0.1:8080 proxy tới backend ở mạng Docker; không còn B server/cổng API nội bộ. Chỉ fork Anvil dùng loopback tạm trong backend container. Đặt reverse proxy HTTPS của VPS trước cổng 8080 khi public. Nginx proxy cả `/v1`, `/v2`, `/execution` tới cùng một backend; không cần CORS vì cùng browser origin.

Sau startup xem `/healthz`, đăng nhập dashboard bằng operator token và chạy một workflow có scope phù hợp. Health OK chỉ phản ánh API đang chạy; không chứng minh mọi proposal đủ policy/session/risk budget. Sau restart kiểm tra journal/history còn nguyên trước khi gửi tiếp. Dừng bằng `docker compose down`; tránh `down -v` vì xóa dữ liệu.

## Render hoặc frontend khác host

Render backend: Docker Web Service, Dockerfile `Dockerfile`, giữ CMD mặc định `python -m treasury_backend.operations.container`, health `/healthz`, một instance, persistent disk `/var/data`, secret file manifest tại `/etc/secrets/treasury-fuji-v2.json`. Điền runtime env từ template; không upload root `.env`. Xem [runbook hosting đầy đủ](../docs/deployment/PYTHON_BACKEND_RENDER_VPS.md).

Frontend: publish folder `frontend/` lên static hosting; không cần build command. Đặt public API URL trong `frontend/assets/config.js`, rồi đặt `PACEVANT_CORS_ORIGINS=https://frontend-domain` trên backend và giữ `PACEVANT_SERVE_FRONTEND=false`. Không dùng wildcard, không đưa token/private key vào frontend config. Hoặc chạy Nginx image với `BACKEND_URL` trỏ API và dùng cùng origin. Static hosting không có proxy cần API link trỏ trực tiếp backend nếu muốn mở Swagger.

## Biến mới trong refactor

Không thêm secret bắt buộc và không sửa `.env` đang có. Các biến tùy chọn có default:

| Biến | Default / cách dùng |
| --- | --- |
| `PACEVANT_SERVE_FRONTEND` | `true` local; Docker/Compose đặt `false` |
| `PACEVANT_CORS_ORIGINS` | trống; danh sách exact HTTP(S) origins phân cách bằng dấu phẩy khi frontend khác origin |
| `TREASURY_ORACLE_MODE` | `demo`; `external` ngăn demo writer ghi đè file oracle |
| `TREASURY_ORACLE_SOURCE_ID` | `TRUSTED_TEST_ORACLE`; nguồn mới phải được review và cập nhật owner policy |
| `BACKEND_URL` | chỉ Nginx frontend container; default `http://backend:10000` |

Backend hiện là một FastAPI/Uvicorn. Attestor và relayer cùng process; owner key vẫn không đưa lên server. `TREASURY_B_PORT`, `PACEVANT_B_URL`, `PACEVANT_B_TOKEN` là cấu hình legacy, không cần cho runtime gộp. `B_API_KEY` vẫn bảo vệ endpoint execution. Xem [kiến trúc backend gộp](../docs/architecture/UNIFIED_BACKEND.md).

Runtime secrets/config đầy đủ nằm trong [template](runtime.env.example). Thiếu manifest Fuji thật thì chưa thể chạy hosted Fuji, dù env đầy đủ. Oracle thật chưa merge: external mode là giao diện tích hợp, không tự tạo market feed.

## Giới hạn xác minh

Python/local chain và contract tests được chạy trên máy phát triển. Docker engine local chưa hoạt động nên chưa build/run hai image hoặc deploy Render/VPS; CI đã có build và kiểm tra runtime riêng. Cần thực hiện image smoke, restart/persistence và một workflow Fuji sau khi có manifest/secrets/hạ tầng thật. Không có giao dịch Fuji hay thay đổi hosting trong refactor này.
