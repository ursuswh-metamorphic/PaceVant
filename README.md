# PaceVant · AI Treasury Security V2.1

A lập kế hoạch, kiểm tra alignment/economic risk, chứng minh Check/Compile và ký ApprovalV2. B dựng calldata, mô phỏng exact guarded path trên Anvil fork, gửi giao dịch qua `PolicyVault` và theo dõi receipt. Vault enforce signed Phi và ngân sách rủi ro phiên/ngày atomically. Hai dịch vụ dùng chung SDK/schema v1.1 với các model V2 bổ sung; EIP-712 domain của ApprovalV2 là version **2**.

**Bắt đầu tại [hướng dẫn chạy local và Avalanche Fuji](docs/demo/AVALANCHE_FUJI_DEMO.md).** Xem [trạng thái `.env`](docs/demo/ENVIRONMENT_STATUS.md) và [luồng xử lý, ví, vai trò Python/Node.js](docs/CURRENT_SYSTEM_FLOW.md). Máy hiện tại đã được điền đủ cấu hình demo theo ủy quyền người dùng, doctor báo ready; chưa deploy V2.1 lên Fuji. Đây là hệ thống mock testnet/research chưa audit.

Backend/build launcher hiện dùng Python và native Foundry, không cần Node.js để deploy/chạy backend. [Render/VPS và Docker không Node.js](docs/deployment/PYTHON_BACKEND_RENDER_VPS.md) giải thích build-time Solidity compiler, runtime Anvil, persistent disk và env riêng cho server. npm/viem được giữ cho công cụ development và cross-language tests.

## Chạy toàn bộ V2.1

Python 3.12, `uv` và native Foundry v1.7.1. Chạy tại root:

```powershell
uv sync --locked
uv sync --project apps/execution-plane --locked
uv run --locked python scripts/bootstrap.py
uv run --locked python scripts/treasury.py init-env
uv run --locked python scripts/treasury.py local --once
```

Smoke tự compile/deploy Anvil, chạy A+B+oracle, thực hiện workflow qua proof/attestor thật đến receipt và dừng các tiến trình do nó tạo. Không dùng khóa Fuji. Cài native Foundry qua release binaries/foundryup hoặc dùng Docker theo runbook hosting. Máy development đã cài npm trước đây vẫn có thể dùng trực tiếp native binaries sẵn có mà không chạy Node.

Để giữ dashboard hoạt động:

```powershell
uv run --locked python scripts/treasury.py local
```

Mở [dashboard](http://127.0.0.1:8000), nhập `PACEVANT_OPERATOR_TOKEN` từ `.env` trên máy. Token được giữ trong bộ nhớ tab. Goal mẫu: `Buy WAVAX with 200 USDC`. Chiều bán cần owner cho phép cap WAVAX riêng. Ctrl+C dừng stack. Service token thiếu được init sinh cục bộ; khóa ví hiện có được giữ nguyên.

## Demo Fuji

Cần ba ví test khác nhau (owner/attestor/relayer), test AVAX cho owner và relayer, RPC Fuji C-Chain 43113 và sáu thông số risk/session trong `.env`. Máy hiện tại đã có đủ các biến này; không cần nối MetaMask vào dashboard. Mock token được mint khi deploy; không cần USDC thật hoặc LLM API key. Xem đơn vị, biến, faucet, gia hạn và xử lý lỗi trong [runbook demo](docs/demo/AVALANCHE_FUJI_DEMO.md).

```powershell
# Sau khi điền khóa attestor và owner risk settings:
uv run --locked python scripts/treasury.py doctor --network fuji --live
uv run --locked python scripts/treasury.py deploy --network fuji
uv run --locked python scripts/treasury.py serve --network fuji
# Terminal khác, khi stack đã READY:
uv run --locked python scripts/treasury.py demo --network fuji
```

`doctor` chỉ đọc, không gửi giao dịch. `deploy:fuji` gửi giao dịch testnet thật, tạo manifest V2 mới và không ghi đè manifest cũ. Signer từ chối cấu hình `TEST_ONLY` trên Fuji. V2 activation khóa vĩnh viễn entrypoint V1 của deployment đó; không thể nâng một địa chỉ immutable bằng việc thay file ABI.

## Kiểm tra

```powershell
npm run check
uv run --locked python -m pytest -q
npm run benchmark:protocol
```

`check` chạy Forge, execution Python, V1/V2 Python↔viem golden vectors và secret scan. Root pytest chạy A, proof/resource tests và full operator smoke. Benchmark là opt-in, chạy source V1 từ commit gốc và V2.1 qua hai tiến trình A/B thật trên Anvil riêng; không đọc `.env` của bạn hoặc gửi Fuji.

## Mã và tài liệu

```text
apps/control-plane/       A: planner, alignment, risk, proof adapter, SDE, attestor, monitor
apps/execution-plane/     B: builder, fork simulation, extraction, durable relayer
apps/dashboard/           Dashboard của A, MOCK/LOCAL/FUJI
contracts/src/            PolicyVault, allowlisted mock adapter, mock tokens
contracts/test/           Foundry security, atomic rollback, golden/fuzz tests
packages/contracts-api/   Shared SDK, V1/V2 DTO, proof engine, ABI/schema
fixtures/v2_1/            TEST_ONLY local policy và cross-language vectors
scripts/treasury*.py      Profile, doctor, deploy/prepare/serve/demo/renew
```

- [Docs index](docs/README.md), [migration progress và test evidence](docs/migration/v2_1_progress.md), [file thay đổi](docs/migration/v2_1_changed_files.md).
- [Proof assumptions](docs/security/proof_assumptions_v2_1.md), [policy coverage](docs/security/policy_coverage_v2_1.md), [ABI/hash vectors](docs/security/abi_hash_vectors_v2_1.md), [evaluation có phạm vi và denominator](docs/evaluation/v1_vs_v2_1_ablation.md).
- [Migration/rollback](docs/migration/v2_1_runbook.md), [shared integration contract](docs/03_SHARED_INTEGRATION_CONTRACT.md), [shared SDK](packages/contracts-api/README.md), [A/B handoff](docs/06_AB_INTEGRATION_HANDOFF.md).

Các lệnh `local`, `deploy:local`, `deploy:fuji`, `demo`, `dev:*`, `config:*` và alias `b:*` giữ tương thích công cụ **B/legacy**. Chúng không thay thế `treasury:*` khi chạy đầy đủ V2.1. Chi tiết legacy: [runbook B](docs/04_PERSON_B_RUNBOOK.md).

Chỉ commit `.env.example`, không commit `.env`, key files, SQL/journal hoặc thư mục `Proof-Gated-Signing/` tham khảo local. Proof có điều kiện trong modeled price domain; exposure 25% vẫn là pre-sign gate, không phải on-chain allocation guarantee.
