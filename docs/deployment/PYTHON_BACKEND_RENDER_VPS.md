# Backend Python trên Render hoặc VPS, không cần Node.js

Backend A/B, CLI vận hành và build launcher hiện chạy bằng Python. Solidity giữ nguyên. Node/npm chỉ còn là lựa chọn cho các lệnh development cũ và golden tests đối chiếu `viem`; Docker backend không cài hoặc gọi Node.js/npm.

## Compile Solidity ở đâu?

| Giai đoạn | Công cụ / kết quả |
|---|---|
| Build | Native **Forge** gọi **solc 0.8.38** để compile Solidity, tạo ABI/bytecode/storage layout trong `out/` |
| Deploy contract | Python/Web3.py gửi bytecode bằng ví owner lên Fuji; lưu manifest địa chỉ/code hash/policy/session |
| Chạy backend | Python gọi các contract đã deploy qua RPC. Không compile Solidity mỗi request và không cần Forge/solc trong runtime image |
| Mô phỏng trước ký | Vẫn cần native **Anvil** để tạo pinned fork, thực thi guarded swap và stress/preflight. Đây là binary native, không phải Node.js |

Hợp đồng sau deployment chạy trên **Avalanche Fuji EVM**, không chạy trong Python server hoặc Render. Dockerfile compile hợp đồng ở build stage và chỉ giữ Anvil cho runtime. Backend vẫn cần các artifacts `out/` để có ABI, bytecode và storage layout phục vụ deploy/simulation; không được chỉ copy Python rồi bỏ artifacts.

## Chạy bằng Python trên máy phát triển

Yêu cầu Python 3.12, `uv` và native Foundry **v1.7.1**. [Foundry installation](https://www.getfoundry.sh/introduction/installation) hỗ trợ foundryup, release binaries và Docker, không cần npm. Linux/macOS có thể dùng foundryup với phiên bản đã pin; Windows có thể đặt release executables trong `.tools/foundry/` hoặc PATH. Foundryup trên Windows cần Git Bash/WSL theo tài liệu chính thức.

```powershell
uv sync --locked
uv sync --project apps/execution-plane --locked
uv run --locked python scripts/bootstrap.py
uv run --locked python scripts/foundry.py forge build
uv run --locked python scripts/treasury.py local
```

`bootstrap.py` tải OpenZeppelin 5.6.1 trực tiếp từ source commit `5fd1781b1454fd1ef8e722282f86f9293cacf256`, kiểm SHA-256 archive rồi cài vào ignored `lib/openzeppelin-contracts/`. Không cần `npm install`. Existing unrecognized source directories không bị ghi đè. Native binary resolver ưu tiên cấu hình explicit, PATH, `.tools/foundry`; có fallback tới native binaries trong node_modules cũ để máy development hiện tại tiếp tục hoạt động mà không gọi Node.

Có thể cấu hình `TREASURY_FOUNDRY_BIN_DIR` hoặc `TREASURY_FORGE_BINARY`/`TREASURY_ANVIL_BINARY` nếu binary ở nơi khác. Chúng là cấu hình máy/công cụ tùy chọn, không phải khóa ví hoặc thông tin bắt buộc mới trong `.env` demo.

## Kiến trúc Docker được chuẩn bị

Một container, một instance:

```text
Internet / HTTPS của Render hoặc reverse proxy VPS
    → API A: 0.0.0.0:$PORT (mặc định 10000)
       → API B: 127.0.0.1:8001
          → Anvil fork: các cổng loopback tạm thời
          → Fuji RPC và PolicyVault đã deploy

/var/data/control/fuji   : SQLite, proof queries, mandate/oracle, logs
/var/data/execution     : B artifacts, SQLite và raw-transaction journal
```

A/B vẫn là hai process Python có trách nhiệm riêng; entrypoint Python quản lý vòng đời và dừng stack khi một process thoát. Chỉ A public, B và Anvil không public. `SIGTERM` được xử lý để cleanup process con. API `/healthz` là health check; readiness không bảo đảm mọi swap sẽ vượt qua policy/session/exposure gates.

Trong runtime container chỉ cung cấp private key **attestor và relayer**, không cung cấp owner/deployer private key. Public owner lấy từ manifest và được kiểm tra lại với vault on-chain. Container từ chối khởi động nếu nhận owner private key qua các biến đã biết. Owner deploy/renew policy/session từ máy quản trị riêng; giữ nguyên giới hạn quyền owner của vault.

## Chuẩn bị trước khi deploy backend

1. Trên máy quản trị, deploy V2 Fuji bằng `uv run --locked python scripts/treasury.py deploy --network fuji`. Đây là giao dịch testnet có phí. Các lần thay đổi backend thông thường không cần deploy contract mới.
2. Giữ manifest thật `deployments/treasury-fuji-v2.json`. Hiện workspace **chưa deploy V2 Fuji**, nên chưa có manifest này để chạy server Fuji.
3. Tạo file env runtime riêng từ [deploy/runtime.env.example](../../deploy/runtime.env.example). Điền actual attestor/relayer keys, ba service tokens và các nonsecret risk settings khớp policy đã deploy. **Không upload nguyên root `.env`**, vì file đó chứa owner key và các alias `${...}` chỉ được xử lý trong local dotenv.
4. Cấp persistent storage. SQLite, proof/audit và raw-tx journal phải còn sau restart/redeploy. Không xóa chúng để giải quyết pending/reorg hoặc policy quarantine.

Các secret cần trên server:

```dotenv
B_FUJI_RELAYER_PRIVATE_KEY=<actual relayer test private key>
PACEVANT_ATTESTOR_KEY=<actual attestor test private key>
B_API_KEY=<backend service token>
PACEVANT_OPERATOR_TOKEN=<dashboard/operator token>
PACEVANT_INTERNAL_TOKEN=<internal signer token>
```

Mỗi service token ít nhất 24 ký tự và khác nhau. RPC URL và nonsecret policy/env defaults xem template. Render environment variables cần actual values; không dùng `${AGENT_PRIVATE_KEY}` hoặc `${B_API_KEY}` như một cơ chế interpolation giữa các biến của hosting.

Entrypoint không deploy hợp đồng, không tự tạo session mới và không compile khi khởi động. Nếu manifest/config/session không hợp lệ thì fail closed trước khi phục vụ workflow.

## Render

Render có [Docker Web Services](https://render.com/docs/docker) và hỗ trợ [FastAPI](https://render.com/docs/deploy-fastapi). Docker phù hợp với dự án này vì có thể đóng gói native Anvil và artifacts cùng hai Python environments. Native Python runtime cũng có thể cài các binary tương tự, nhưng Docker giúp giữ toolchain thống nhất.

Cấu hình dịch vụ:

| Setting | Giá trị |
|---|---|
| Service | Web Service, Docker runtime, repo root |
| Dockerfile | `Dockerfile` |
| Docker command | Giữ CMD mặc định: `python scripts/container.py` |
| Health check | `/healthz` |
| Public port | Render cấp `$PORT`; entrypoint bind A lên `0.0.0.0` |
| Persistent disk | Mount `/var/data` |
| Instances | **1**, không autoscale với SQLite/journal hiện tại |
| Manifest | [Secret file](https://render.com/docs/configure-environment-variables#secret-files) tên `treasury-fuji-v2.json`; `TREASURY_FUJI_DEPLOYMENT_FILE=/etc/secrets/treasury-fuji-v2.json` |
| Environment | Actual runtime values từ template, không có owner key |

Render filesystem mặc định là ephemeral. [Persistent disks](https://render.com/docs/disks) hiện có trên các service trả phí; chỉ dữ liệu dưới mount path được giữ, disk chỉ gắn một instance và không truy cập được trong build/pre-deploy. Vì thế artifacts được compile trong image build, còn DB/journal chỉ tạo/đọc trong runtime. Free service không có persistent disk không phù hợp để duy trì journal của hệ thống hiện tại.

Cần đủ CPU/RAM cho Anvil fork + Z3 và RPC phục vụ historical state. Chưa benchmark resource/latency trên Render; không có bảo đảm một plan cụ thể sẽ đáp ứng deadline ký 30 giây. Đo bằng workflow thật sau khi deploy thay vì tăng TTL hoặc bỏ gate để bù máy/RPC chậm.

## VPS dùng Docker

Build image từ root:

```bash
docker build -t pacevant-backend .
```

Tạo `deploy/runtime.env` cục bộ từ template, copy manifest public thật vào `deploy/treasury-fuji-v2.json`, rồi chạy trên VPS Linux:

```bash
docker run -d --name pacevant-backend --restart unless-stopped \
  --env-file deploy/runtime.env \
  --mount type=volume,source=pacevant-data,target=/var/data \
  --mount type=bind,source="$(pwd)/deploy/treasury-fuji-v2.json",target=/etc/secrets/treasury-fuji-v2.json,readonly \
  -p 127.0.0.1:10000:10000 \
  pacevant-backend
```

Dùng reverse proxy HTTPS trên VPS trỏ đến `127.0.0.1:10000`. Không mở B/Anvil ra Internet. Runtime không cần cài Node, npm, Rust compiler hoặc Solidity compiler trên host; Docker image đã mang Python, Anvil và precompiled artifacts.

## Vận hành sau deployment

- Session mặc định chỉ 1 giờ. Owner chọn thời hạn phù hợp trước deploy hoặc gia hạn từ máy quản trị: `uv run --locked python scripts/treasury.py renew-session --network fuji`. Cập nhật manifest mới trên host/Render và restart backend vì B cache session lúc startup. Global/day counters không reset khi đổi session.
- Khi đổi policy/source oracle, owner thực hiện cấu hình phù hợp rồi đồng bộ manifest/mandate/server settings. Không đưa owner key lên web service để tự gia hạn.
- Oracle trong entrypoint vẫn là controlled demo heartbeat. Sau khi merge oracle thực tế, thay writer/interface theo [oracle merge review](../migration/v2_1_readiness_review.md); không để demo writer ghi đè dữ liệu thật.
- Backup volume bằng phương thức phù hợp SQLite và giữ raw journal/audit. Kiến trúc này chưa có shared PostgreSQL hoặc multi-instance locking để chạy HA/autoscaling.

## Trạng thái xác minh

Native compile và kiểm thử Python/local đã chạy trên máy development. Full operator smoke có test chạy khi PATH không có Node. Dockerfile và container preflight tests đã được chuẩn bị; **Docker Desktop Linux engine trên máy này chưa chạy, nên chưa build/run được image local hoặc xác minh một deployment Render thật**. CI có job build image và kiểm tra không có Node/npm/Forge ở runtime; job này chỉ có kết quả sau khi chạy trên CI. Không có giao dịch Fuji hay thay đổi dịch vụ hosting trong lần chuyển toolchain này.
