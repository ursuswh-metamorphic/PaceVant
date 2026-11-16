# AI Treasury Security — Execution Plane B

Triển khai phần B theo [guide v1.1](docs/02_GUIDE_PERSON_B_EXECUTION_PLANE.md) và [shared integration contract](docs/03_SHARED_INTEGRATION_CONTRACT.md): swap mock USDC → WAVAX qua `PolicyVault`, EIP-712 PDR, pinned-fork simulation, evidence và FastAPI.

```text
apps/execution-plane/     FastAPI B, builder, simulation, evidence, relayer, chain
contracts/src/           PolicyVault, adapter, interfaces, mock tokens
contracts/test/          Foundry acceptance/security/golden-vector tests
contracts/script/        Deploy.s.sol
packages/contracts-api/  Shared Python DTOs, SDK, JSON Schemas cho A/B
fixtures/                Proposal templates, mock outputs, EIP-712 golden vectors
tests/integration/       Python ↔ viem signature contract test
scripts/                 Foundry runner và secret scan
deployments/             Manifest sinh từ deployment mới
evidence/                Kết quả kiểm chứng phần B
docs/                    Thiết kế, runbook và tài liệu PoC lịch sử
```

Local đã xác nhận swap 200 mock USDC → 10 mock WAVAX và stress revert có rollback. Fuji và SDE/attestor thật của A còn chờ tích hợp; không dùng đây làm tuyên bố đã chạy Fuji.

Cài Node >=22.13 và `uv`, rồi chạy tại root:

```powershell
npm ci --ignore-scripts
npm run setup
npm run check
# Tự compile, khởi động/tái dùng Anvil, bootstrap nếu cần và chạy API:
npm run local
```

`--ignore-scripts` tránh postinstall POSIX của Foundry trên Windows; runner dùng binary đã pin theo OS/CPU.

Hoặc chạy tách từng bước thay cho `npm run local`. Terminal 1:

```powershell
npm run anvil
```

Terminal 2:

```powershell
npm run deploy:local
npm run demo
npm run dev
```

API: `http://127.0.0.1:8001/docs`; dùng `B_API_KEY` trong **`.env` duy nhất**, POST cần `Idempotency-Key`. Local/Fuji có nhóm `B_LOCAL_*` và `B_FUJI_*` riêng. Bootstrap chỉ cập nhật nhóm local và giữ API key để A không phải cấu hình lại. Các biến ví test cũ được giữ lại; Fuji có thể tham chiếu chúng qua `${DEPLOYER_PRIVATE_KEY}` / `${AGENT_PRIVATE_KEY}`.

`npm run local` là cách chạy một lệnh; các terminal/lệnh tách riêng ở trên dành cho khi cần kiểm soát từng bước. `npm run config` / `npm run config:fuji` kiểm tra cấu hình mà không in private key/API key. `npm run dev` theo `B_MODE`; `npm run dev:local`, `dev:fuji`, `deploy:local`, `deploy:fuji` chọn đúng profile mà không phải sửa file hoặc copy key.

Để lên Fuji, bổ sung `B_FUJI_ATTESTOR_ADDRESS` do A cung cấp trong `.env`, kiểm tra test AVAX cho owner/relayer, rồi dùng `npm run deploy:fuji` và `npm run dev:fuji`. Khi merge chỉ commit `.env.example`; `.env` và file khóa cập nhật cấu hình được gitignore.

- [Runbook vận hành, API và cách lấy địa chỉ attestor Fuji](docs/04_PERSON_B_RUNBOOK.md)
- [Cấu trúc sau refactor và cách tham khảo/khôi phục PoC](docs/05_PROJECT_STRUCTURE.md)
- [Shared SDK để A tích hợp](packages/contracts-api/README.md)
- [Bàn giao A/B chi tiết](docs/06_AB_INTEGRATION_HANDOFF.md)
- [Prompt và playbook để AI merge code](docs/07_AI_MERGE_PLAYBOOK.md)
- [Báo cáo tương thích và các gate còn chờ A](docs/08_AB_COMPATIBILITY_AUDIT.md)
- [Kết quả kiểm chứng](evidence/execution-plane-validation.json)

`npm test` chạy Forge, pytest và golden signature test. `npm run check` thêm secret scan. Các alias `b:*` được giữ cho hướng dẫn và lệnh đã dùng trước đó. AI Planner, SDE và dashboard thuộc A; sẽ merge vào `apps/control-plane` và `apps/dashboard` khi có mã của A.
