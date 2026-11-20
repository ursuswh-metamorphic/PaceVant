# Deployment guidance

> **Current MVP scope (21 November 2026):** follow the [single-tenant runbook](../MVP_DEMO_RUNBOOK.md) and [architecture](../MVP_FINAL_ARCHITECTURE.md). Demo User, HMAC browser personas and customer gas charging below are historical. Canonical runtime disables them. `runtime.env.example` includes the optional signed MVP manifest and explicit live-enable setting. Keep the old public manifest for history, mount the new signed manifest separately after Owner migration, and retain all persistent data. The frontend image now opens the two-operation MVP and proxies `/mvp/`. No new public deployment or container-hosting success is claimed.

> **DOC STATUS: COMPONENT_REFERENCE** — đối chiếu runtime source `3f9f9af`, 20/11/2026. Hosting chưa có end-to-end smoke evidence. [Current design](../docs/AI_Treasury_Security_System_Design_v2.1.md) là nguồn tổng hợp chính.

Backend dùng Python/FastAPI và native Anvil. Dockerfile root compile Solidity trong build stage, runtime dùng artifacts đã build để mô phỏng và tương tác với contracts trên Avalanche. Server không thay blockchain; không cần Node backend. Frontend có thể serve chung API hoặc Nginx/static host riêng.

## Trước khi dùng Compose/Render/VPS

`runtime.env.example` là **HISTORICAL_TEMPLATE**, chưa đủ flag/config của current Fuji profile: defaults session/TTL/provider cũ, thiếu one-click demo/Shield/ITAG settings. Không copy nguyên rồi coi đó là cấu hình hiện tại. Đối chiếu `.env.example`, effective profile trong [sanitized inventory](../docs/current-system-inventory.json), `operations/environments.py` và `operations/container.py`; tạo private runtime config không có owner/deployer/Demo User private key. Không upload root private `.env` lên frontend/hosting.

Runtime cần attestor/relayer keys và các service/model credentials đúng scope. Ba service tokens phải khác nhau; demo signing secret riêng. Bật demo cần required ITAG + wallet_pipeline/wallet_hardened và real execution. Chọn direct Chainlink mapping cho Circle USDC/WAVAX, đúng manifests/policy/session. Đổi env không thay policy đã deploy.

Giữ **một backend instance/worker**, persistent disk cho cả control và execution databases, proofs/artifacts, send/owner journals. Mount public deployment manifest read-only; xác minh chain/vault/code/session trước dùng. Không reset DB hoặc dùng ephemeral storage để chữa pending transaction.

## Files hiện có và phạm vi

| File | Vai trò |
| --- | --- |
| `../Dockerfile` | Foundry build stage + Python/native Anvil runtime |
| `../compose.yaml` | Backend + frontend Nginx, private runtime env, manifest mount, persistent volume |
| `../frontend/Dockerfile` | Static frontend, proxy về cùng backend |
| `runtime.env.example` | Template lịch sử, cần reconcile trước khi sử dụng |
| `../backend/src/treasury_backend/operations/container.py` | Owner-free hosted startup, PORT/data paths |

Backend entrypoint là `python -m treasury_backend.operations.container`. Frontend proxy dùng `BACKEND_URL`; nếu static host khác origin thì public `frontend/assets/config.js` chỉ chứa API base URL và backend bật exact CORS origins. Cần cho phép Authorization/Content-Type/Idempotency-Key. Không đặt bất kỳ key/token nào trong assets.

Render có thể dùng Docker Web Service và persistent disk; VPS có thể dùng Compose cùng HTTPS reverse proxy. Đây là khả năng cấu trúc triển khai, chưa phải xác nhận deployment đã chạy. Cần kiểm image/native binary, startup, secret filtering, session/funding/provider readiness, browser/proxy/CORS, restart/persistence và billing reconciliation trước khi công bố hosting sẵn sàng.

## An toàn thao tác

Build/start container không nên tự deploy contract hoặc chạy goal swap. `/healthz` chỉ liveness. Deployment/renew/setup là lệnh owner có transaction và phí; thực hiện riêng trên máy operator khi cần, không gắn vào container restart. Giữ logs private và không in authenticated RPC URLs/raw tx/keys. Không dùng `docker compose down -v` như thao tác restart vì sẽ xóa persistent state.

Để demo tại máy operator trước khi hosting, dùng [current runbook](../docs/demo/DEMO_USER_GAS_CREDIT.md) và [design mục 20](../docs/AI_Treasury_Security_System_Design_v2.1.md#20-vận-hành-demo-và-chuẩn-bị-phản-biện). Các hướng dẫn hosting cũ trong `docs/deployment/` chỉ là lịch sử.
