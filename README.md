# PaceVant — AI Treasury Security V2.1

Đã tích hợp ITAG từ `main@70bf6c7`: intent budget, ordered tasks, temporal graph và viewer `/itag`. [Cấu hình opt-in và giới hạn V2 đang còn](docs/integrations/ITAG_MAIN_SYNC.md).

Đã tích hợp tính năng mới từ `main@08c35df` vào cấu trúc module: Task Shield, portfolio history và outcome reconciliation có hỗ trợ PDR V2. [Chi tiết thay đổi, cấu hình và kiểm chứng](docs/integrations/MAIN_SYNC_2026_11_20.md). Task Shield LLM hiện **chưa bật** trong `.env`; các gate deterministic/proof/on-chain vẫn giữ nguyên.

Cập nhật 20/11/2026: [demo toàn hệ thống trên Fuji thật](docs/demo/FUJI_LIVE_END_TO_END.md) dùng Circle USDC/WAVAX, direct Chainlink và ba ví đã cấu hình. [Report nghiệm thu](docs/integrations/fuji-live-validation.json) có receipt public, proof và các phép kiểm âm.


Đọc trước: [System design V2.1 hiện tại](docs/AI_Treasury_Security_System_Design_v2.1.md). Live Fuji đã xác nhận workflow đầy đủ; MOCK/LOCAL còn để regression. [Audit cũ](docs/audit/V2_1_READINESS_REVIEW.md) giữ checkpoint trước live cutover. Production/hosting vẫn cần kiểm chứng riêng.

Hệ thống treasury dùng Python để lập kế hoạch, kiểm tra alignment/risk, chứng minh điều kiện an toàn, ký và gửi giao dịch qua Solidity `PolicyVault`. Frontend là HTML/CSS/JavaScript chạy trong trình duyệt. Backend không cần Node.js.

Repository được chia theo năng lực nghiệp vụ để nhiều người phát triển song song. Các module **control/workflow** và **execution** chạy trong **một ứng dụng FastAPI, một process Uvicorn, một cổng API**, dùng chung một package Python, `pyproject.toml`, `uv.lock` và `.venv`. Luồng nội bộ gọi module trực tiếp, không chạy execution server riêng.

## Bắt đầu

Máy phát triển cần Python 3.12, uv và native Foundry v1.7.1. Chạy từ root:

```powershell
uv sync --locked
uv run --locked python tools/contracts/bootstrap.py
uv run --locked treasury init-env
uv run --locked treasury local --once
```

Lệnh cuối chạy toàn bộ workflow trên Anvil local tới receipt rồi dừng các process do nó tạo. Dùng `uv run --locked treasury local` để giữ dashboard tại http://127.0.0.1:8000. Nhập `PACEVANT_OPERATOR_TOKEN` của máy vào form kết nối; token chỉ nằm trong bộ nhớ tab. Goal mẫu: `Buy WAVAX with 200 USDC`.

Xem UI/logic ở MOCK, không cần chain: `uv run --locked python -m treasury_backend.api.serve`. MOCK dùng fixture V1, không chạy proof/Phi/session V2.1. Dùng LOCAL để kiểm chứng đầy đủ lõi V2.1.

## Cấu trúc để phát triển

```text
backend/
  src/treasury_backend/
    modules/         planning, alignment, portfolio, oracle, risk, proof,
                     decision, signing, persistence, experience, workflows,
                     execution/{chain,transaction,simulation,evidence,relaying}
    core/            DTO ứng dụng, lỗi, JSON nghiêm ngặt
    config/          đọc và kiểm tra settings
    api/             HTTP, auth, lifecycle
    operations/      CLI, profile, deploy, quản lý process
  tests/             control, execution, integration, architecture
frontend/            assets + src/{api,shared,features}
contracts/           Solidity source, tests, deploy helper
packages/contracts-api/  protocol SDK, schemas, hashes, proof engine dùng chung
tools/               contracts, quality, evaluation, operations
deploy/              cấu hình runtime mẫu; compose.yaml ở root
docs/                kiến trúc, luồng, demo, bảo mật, vận hành
scripts/             entrypoint tương thích lệnh cũ
```

Mỗi module/thành phần có README riêng. Đọc [bản đồ module](backend/MODULES.md), [kiến trúc một backend](docs/architecture/UNIFIED_BACKEND.md), [quy tắc đóng góp](CONTRIBUTING.md), [backend](backend/README.md) và [frontend](frontend/README.md). Tính năng thường chỉ sửa trong module sở hữu; thay đổi ABI/schema/chữ ký cần phối hợp các phần dùng chung.

## Demo Fuji và triển khai

Đường LFJ và oracle đọc thật đã vào FastAPI gộp. Dashboard có trang **Ví và oracle Fuji**. `uv run --locked treasury lfj-preflight` đọc quote và Chainlink tại cùng block. Public LFJ signing đang bị chặn bởi định danh tài sản. [Tích hợp Fuji/LFJ V2.1](docs/integrations/FUJI_LFJ_V2_1.md).

Theo [runbook local/Fuji](docs/demo/AVALANCHE_FUJI_DEMO.md). Cần ba ví test khác nhau: owner, attestor và relayer; owner/relayer có test AVAX. Không cần kết nối Core/MetaMask vào dashboard hoặc USDC thật. [Groq/env integration](docs/integrations/GROQ_PLANNER_AND_ENV.md) đã có real bounded LLM planner; chọn `groq` cần API key, `rules` là offline option. Private env đã cập nhật theo ba ví người dùng cấp và bật Groq, không ghi secret vào template/source; xem [trạng thái môi trường](docs/demo/ENVIRONMENT_STATUS.md).

Backend Dockerfile ở root; frontend Dockerfile riêng trong `frontend/`. [Hướng dẫn deploy](deploy/README.md) có Compose cho VPS và cấu hình frontend/API khác origin. [Runbook Render/VPS](docs/deployment/PYTHON_BACKEND_RENDER_VPS.md) giải thích compile Solidity trong build, runtime Python/Anvil, persistent storage và runtime env không chứa owner key.

Hiện chưa deploy V2 lên Fuji hoặc hosting. Oracle vẫn là controlled demo; module [oracle](backend/src/treasury_backend/modules/oracle/README.md) có hướng dẫn tích hợp nguồn thực. Planner là template/regex; DEX thực chưa tích hợp. Đây là mock treasury phục vụ testnet/research, chưa audit.

## Kiểm tra

```powershell
uv run --locked python -m pytest -q
uv run --locked python tools/contracts/foundry.py forge test -vv
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python tools/quality/scan_secrets.py
```

Module [mô phỏng](backend/src/treasury_backend/modules/execution/simulation/README.md) đã có Anvil fork, baseline/stress và final Phi preflight. Node/viem chỉ cần khi chạy đối chiếu chữ ký bằng ngôn ngữ khác hoặc kiểm tra cú pháp frontend: `npm ci --ignore-scripts`, `npm run test:integration`, `npm run check:frontend`. [Chi tiết kiểm thử](backend/tests/README.md), [chỉ mục docs](docs/README.md), [giả định proof](docs/security/proof_assumptions_v2_1.md).

Code trước refactor được lưu ở commit `19aa935`. Không commit `.env`, khóa ví, SQL/journal, artifacts runtime hay thư mục tham khảo local `Proof-Gated-Signing/`.
