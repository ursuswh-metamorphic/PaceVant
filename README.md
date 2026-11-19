# PaceVant · AI Treasury Security

`main` là nhánh tích hợp và nhánh mặc định, gồm Control Plane A, Execution Plane B, Fuji Observatory và LFJ. Hai PR [#1](https://github.com/ursuswh-metamorphic/PaceVant/pull/1) / [#2](https://github.com/ursuswh-metamorphic/PaceVant/pull/2) đã được merge, giữ nguyên lịch sử. Xem [trạng thái tích hợp](docs/MAIN_INTEGRATION.md) cho cách chạy và các điều kiện live còn thiếu.

A lập kế hoạch, kiểm tra chính sách và ký EIP-712 khi SDE cấp quyền. B dựng calldata, mô phỏng trên fork, gửi giao dịch qua `PolicyVault` và trả receipt. Hai dịch vụ dùng chung SDK 1.3.0 và schema evidence v1.1. [Hợp đồng tích hợp](docs/03_SHARED_INTEGRATION_CONTRACT.md)

```text
apps/execution-plane/     FastAPI B, builder, simulation, evidence, relayer, chain
apps/control-plane/       FastAPI A, planner, shield, risk, SDE, attestor
apps/dashboard/           Dashboard demo của A
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

Cài Node >=22.13, Python 3.12 và uv. Chạy tại root.

```powershell
npm ci --ignore-scripts
npm run setup
uv sync --locked
npm run check
uv run --locked python -m pytest -q
npm run test:ab
# Tự compile, khởi động/tái dùng Anvil, bootstrap nếu cần và chạy API:
npm run local
```

`--ignore-scripts` tránh postinstall POSIX của Foundry trên Windows; runner dùng binary đã pin theo OS/CPU.

`npm run test:ab` chạy A và B trong hai tiến trình riêng với Anvil tạm thời. Test gọi API A rồi đối chiếu receipt và nonce trên chain. Có thể chạy dashboard mock riêng với `uv run --locked python scripts/serve.py` và mở cổng 8000. [Dashboard](http://127.0.0.1:8000/) · [Cấu hình A nối B](docs/B_HANDOFF.md)

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
- [Báo cáo tương thích của B trước khi tích hợp](docs/08_AB_COMPATIBILITY_AUDIT.md)
- [Kết quả kiểm chứng](evidence/execution-plane-validation.json)

`npm test` chạy Forge, pytest và golden signature test. `npm run check` thêm secret scan. Các alias `b:*` vẫn dùng được. Kiểm thử Fuji cần triển khai riêng với ví test và chứng cứ fork tương ứng.

## Fuji Wallet + Oracle (read-only, testnet-only)

Portfolio schema 2.0 bổ sung nguồn dữ liệu theo block/token, lịch sử SQLite bất biến theo Vault và worker đối chiếu receipt có thể phục hồi sau restart mà không cần khóa ký. Xem [hướng dẫn snapshot, monitor và migration](docs/PORTFOLIO_OUTCOME_MONITORING.md), [audit trước triển khai](docs/PORTFOLIO_OUTCOME_AUDIT.md) và [báo cáo kiểm thử](docs/PORTFOLIO_OUTCOME_REPORT.md). PDR và chốt định giá LFJ faucet USDC giữ nguyên.

The Fuji Observatory reads AVAX, Circle test USDC and WAVAX at a pinned block, Chainlink AVAX/USD and USDC/USD, Witnet and Pyth observations, plus optional PolicyVault state and execution receipts. It exports source and block evidence; prices remain outside SDE/PDR authorization.

```powershell
uv run --locked python scripts/fuji_wallet_read.py 0xYOUR_PUBLIC_FUJI_ADDRESS
```

Run `uv run --locked python scripts/serve.py --fuji-readonly --port 8012` with `PACEVANT_OPERATOR_TOKEN` set locally (24+ characters), then open `http://127.0.0.1:8012/fuji-wallet`. No B service or private key is required. See the [observer guide](docs/FUJI_WALLET_MARKET_READONLY.md) and [live verification report](docs/FUJI_AVALANCHE_INTEGRATION_REPORT.md).

**Important:** Fiat-looking testnet token quantities are not real assets; a real AVAX/USD feed is not sufficient to value a MockUSDC treasury. This reader is intentionally not in the approval path. Do not interpret legacy ERC-4337 Fuji receipts as deployments of the current PolicyVault.

## Real LFJ route on Fuji (live-state fork verified)

`npm run lfj:preflight` reads actual LFJ pools/quotes; `uv run --locked python scripts/lfj_preflight.py` binds the existing Chainlink reader to the same source block. `npm run test:lfj:fork` executes the real V1 route through LFJ LBRouter V2.2 on isolated Anvil forks. See the [LFJ guide](docs/LFJ_FUJI_INTEGRATION.md) and [verification report](docs/LFJ_FUJI_REPORT.md).

`deploy:fuji` now defaults to **dry-run** and the Fuji relayer requires explicit broadcast authorization. LFJ faucet USDC has no verified USD valuation in this integration, so A's SDE keeps escalation and does not sign PDR. Public Fuji deployment/execution remains unverified; fork receipts represent fork execution only.
