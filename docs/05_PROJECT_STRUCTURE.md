# Cấu trúc dự án sau refactor — Person B v1.1

Dự án hiện tại chỉ chứa Execution Plane B và interface dùng chung để merge với A. Hợp đồng chuẩn vẫn là `03_SHARED_INTEGRATION_CONTRACT.md`; không đổi route, Approval field order, schema hay hash trong lần refactor này.

```text
apps/
  execution-plane/
    app/
      api/              # FastAPI trên port 8001
      chain/            # RPC context, pinned block, portfolio chain reads
      transaction/      # Builder exact calldata
      simulation/       # Isolated Anvil forks và fixed stress scenarios
      evidence/         # Receipt/trace/token effects extractor
      execution/        # Verify PDR, relay, receipt monitor
      store.py          # SQLite records, nonce allocator, artifact storage
      settings.py       # B_* settings, tách owner key khỏi API model
      cli.py            # Deploy/local test demo/schema commands
    tests/              # Python unit + HTTP E2E, tự tạo Anvil riêng
    pyproject.toml
    uv.lock
contracts/
  src/
    PolicyVault.sol
    interfaces/ISwapAdapter.sol
    adapters/MockSwapAdapter.sol
    mocks/MockUSDC.sol
    mocks/MockWAVAX.sol
  test/                 # Vault, adversarial adapter, golden-vector tests
  script/Deploy.s.sol
packages/contracts-api/ # Shared DTO, EIP-712/JCS helpers, SDK, JSON Schemas
fixtures/               # Input templates, MOCK_FIXTURE, golden bytes/signature
tests/integration/      # Python-produced vector checked by viem
scripts/                # Pinned Foundry runner, secret scan
deployments/            # Chỉ manifest PolicyVault mới, sinh khi deploy
evidence/               # Chỉ kết quả xác minh Execution Plane
docs/                   # Thiết kế mới + tài liệu thử nghiệm cũ
.github/workflows/      # CI cho Execution Plane
foundry.toml
package.json
package-lock.json
.env.example
```

`apps/control-plane/` và `apps/dashboard/` thuộc A và sẽ được thêm khi merge mã của A. Không tạo skeleton hay API giả cho phần của A.

## Các lệnh chính

| Lệnh | Công dụng |
|---|---|
| `npm ci --ignore-scripts` | Cài đúng dependency lock, chạy được trên Windows |
| `npm run setup` | Cài Python environment theo uv.lock |
| `npm run compile` / `npm run build` | Build Foundry contracts |
| `npm test` | Forge, pytest, Python–viem golden vector |
| `npm run check` | Toàn bộ test + secret scan |
| `npm run anvil` | Local chain 31337 |
| `npm run local` | Một lệnh compile → Anvil → bootstrap nếu cần → API |
| `npm run deploy:local` | Deploy mock tokens/adapter/vault, tạo cấu hình local |
| `npm run demo` | Local test signed PDR → real simulation → receipt |
| `npm run dev` | FastAPI B theo B_MODE trong `.env` |
| `npm run dev:local` / `dev:fuji` | Chọn profile local/Fuji rõ ràng |
| `npm run config` / `config:fuji` | Kiểm tra cấu hình, không in secrets |
| `npm run deploy:fuji` / `npm run dev:fuji` | Dùng B_FUJI_* trong `.env`, cần địa chỉ attestor của A |
| `npm run schemas` / `golden` / `fixtures` | Sinh lại schema và fixtures dùng chung |

Alias `b:*` từ phiên trước vẫn dùng được; chúng chỉ gọi các lệnh chuẩn tương ứng. Npm còn 4 direct dependencies: Foundry forge/anvil, OpenZeppelin và viem. Python dependencies và lockfile không đổi trong lần refactor.

## Đã loại bỏ

- React/Vite frontend, Playwright dashboard E2E, shared TypeScript của PoC.
- Hardhat config/plugins, TypeScript config/toolchain và các tests PoC.
- `AgentTreasuryGuard`, `AvalancheStorage`, `UniHackSmartAccount`, LocalEntryPoint và adversarial recipient cũ.
- Các script deploy/fund/agent/bundler/report/export riêng của PoC.
- Manifest Fuji cũ, screenshots/raw evidence PoC và output/cache build cũ. Chỉ giữ evidence/manifest của PolicyVault mới.
- Dependency React/Vite/Hardhat/Playwright/TypeScript/ERC-4337 không còn được package hiện tại sử dụng.

Sau bước dọn source, cấu hình đã được gộp theo yêu cầu tiếp theo vào **`.env` duy nhất**. Biến PoC cũ vẫn được giữ; `B_LOCAL_*` chứa local relayer/RPC, `B_FUJI_*` tách riêng Fuji. Ví Fuji có thể tham chiếu biến owner/agent test cũ qua `${...}`. API key local được giữ nguyên khi gộp và khi bootstrap. `.env.b.local` cũ đã được bỏ; `.env.example` là template duy nhất cần commit khi merge. Không deploy hay chuyển test AVAX trong các bước cấu hình này.

## Tài liệu PoC được giữ để tham khảo

`LEGACY_POC_README.md`, `ARCHITECTURE.md`, `RESEARCH.md`, `FEASIBILITY_REPORT.md`, `SMART_ACCOUNTS.md`, `SMART_ACCOUNT_RESULTS.md`, `TEST_RESULTS.md`, `WALLET_SETUP.md` là tài liệu lịch sử. Các lệnh/địa chỉ và đường dẫn tới source, manifest hay screenshot cũ trong các file đó không thuộc bản triển khai hiện tại.

Trước khi khởi tạo lại Git, workspace từng tham chiếu commit `824cbff` (`Initial commit: PaceVant blockchain PoC`). Thư mục `.git` của bản cũ không còn trong workspace khi repository hiện tại được khởi tạo; commit này **không được bảo đảm có trong lịch sử mới**. Nếu bạn còn một clone/backup chứa commit đó, có thể đọc từng file từ clone đó mà không đổi working tree:

```powershell
git show 824cbff:contracts/UniHackSmartAccount.sol
git show 824cbff:package.json
git show 824cbff:scripts/deploy-smart-account.ts
```

Tham khảo tài liệu PoC đã giữ trong `docs/`, hoặc source từ clone/backup cũ nếu có; không trộn dependency hay execution path ERC-4337 vào PolicyVault MVP. Repository mới bắt đầu bằng source hiện tại, không bao gồm lịch sử Git cũ.
