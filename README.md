# PaceVant · AI Treasury Security

Control plane của thành viên A theo Shared Integration Contract v1.1. Một workflow đi từ đề xuất swap USDC → WAVAX, Task Alignment, build và simulation, đến Economic Risk, SDE, PDR và theo dõi receipt. Bản độc lập dùng mock B, test oracle và khóa attestor sinh riêng khi khởi động.

## Chạy demo

Cần Python 3.12 và uv. Chạy các lệnh sau từ thư mục gốc. [Tài liệu uv](https://docs.astral.sh/uv/)

```powershell
uv sync --locked
uv run --locked python scripts/serve.py
```

Mở [dashboard](http://127.0.0.1:8000/) hoặc [Swagger](http://127.0.0.1:8000/docs). Mỗi lượt mock khởi tạo số dư riêng theo fixture. Workflow và lịch sử các lần đề xuất lưu trong SQLite dưới `data/`.

| Kịch bản | Kết quả của control plane |
|---|---|
| Swap hợp lệ | 500 USDC → `APPROVE` → chữ ký dev → receipt mock `CONFIRMED` |
| Vượt trần WAVAX | 500 USDC lên 28% → `REPLAN` → build và mô phỏng 200 USDC từ đầu → 25% |
| Prompt injection | Recipient ngoài vault → `TASK_MISALIGNED`, `BAD_RECIPIENT` → `REJECT` trước builder |
| Giá đã cũ | `STALE_PRICE` → `ESCALATE` trước attestation |

Có thể chạy kịch bản vượt trần qua API bằng PowerShell.

```powershell
$body = @{
    goal = 'Buy WAVAX with 500 USDC'
    mandate_id = 'mandate_demo'
    scenario = 'exposure_limit'
} | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/workflows/start' -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://127.0.0.1:8000/v1/workflows/$($run.workflow_id)" | ConvertTo-Json -Depth 20
```

Planner deterministic nhận mục tiêu có số lượng rõ ràng như `Buy WAVAX with 200 USDC` hoặc `Mua WAVAX bằng 200 USDC`. Dấu chấm là dấu thập phân, tối đa 6 chữ số sau dấu chấm. Mục tiêu ngoài phạm vi mẫu được xử lý bằng `UNCERTAIN`. Planner ghi phiên bản và lý do đã chuẩn hóa, experience ghi hash market feed và các reason code để replan.

## Kiểm thử

```powershell
uv run --locked python -m pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
forge test -vv
```

`forge test` dùng Foundry 1.7.1 với Solidity 0.8.30. Harness Solidity kiểm tra digest, recover signer, sửa calldata, sửa amount, đổi chain, expiry và replay. Các bài Python kiểm tra A‑01 đến A‑10, HTTP wire qua test double, JCS manifest, thứ tự verdict, SQLite immutability, ngân sách UTC và trạng thái submission.

| Vị trí | Nội dung |
|---|---|
| [apps/control-plane](apps/control-plane) | FastAPI, planner, shield, risk, SDE, attestor và orchestration |
| [apps/dashboard](apps/dashboard) | Trình xem demo và timeline đọc từ backend |
| [packages/contracts-api](packages/contracts-api) | Pydantic wire models và JSON Schema v1.1 |
| [fixtures/mock](fixtures/mock) | Bốn kịch bản chạy độc lập và yêu cầu replay |
| [fixtures/eip712_golden](fixtures/eip712_golden) | Typed data, signature, manifest canonical và report |
| [docs/B_HANDOFF.md](docs/B_HANDOFF.md) | Cách nối B, chi tiết wire còn cần đồng thuận và các gate nghiệm thu |

Tạo lại schema và golden vector bằng `uv run --locked python scripts/generate_contract.py` và `uv run --locked python scripts/generate_golden.py`.
