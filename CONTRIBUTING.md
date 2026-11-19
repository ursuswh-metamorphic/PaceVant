# Phát triển theo module

Chạy mọi lệnh từ root; chỉ có một môi trường Python. Bắt đầu với [backend](backend/README.md), [bản đồ module](backend/MODULES.md) và README của module cần thay đổi.

## Chọn nơi viết code

| Công việc | Nơi sở hữu |
| --- | --- |
| Parser/planner mới | `modules/planning` |
| Alignment, risk, quyết định | module tương ứng |
| Oracle thật | `modules/oracle`; xem quy trình source/policy cutover |
| Use case, retry/monitor | `modules/workflows` |
| Build/simulate/relay | component tương ứng trong `modules/execution` |
| SQL/migration control | `modules/persistence` |
| Route/auth/CORS | `api/app.py`, router tương ứng và `config` |
| Deploy/profile/process | `operations` |
| UI tính năng | `frontend/src/features/<feature>` |
| Wire/ABI/hash/proof math | `packages/contracts-api`, phối hợp Solidity/backend |

Backend paths ở bảng tương đối với `backend/src/treasury_backend`. Không tạo package chung tên `app`, không gom logic vào `utils.py` hoặc handler. Import public API từ module; workflow điều phối giữa các module. Workflow dùng client port; `api/app.py` inject adapter gọi ExecutionService trực tiếp. Không gọi HTTP nội bộ hoặc import execution internals vào workflow. Execution không import signing hay operator. Không đọc `.env` trực tiếp trong domain service.

## Thêm module

Tạo `modules/<name>/` gồm `__init__.py` (export rõ), implementation, `README.md` và `tests/`. Định nghĩa DTO feature tại module; chỉ chuyển loại dùng chung thật sự sang core/SDK. Đăng ký use case/HTTP ở composition phù hợp. Pytest tự tìm test trong modules. Cập nhật MODULES.md và ghi input/output, đơn vị, dependency, lỗi, cấu hình, cách mở rộng và lệnh kiểm tra trong README của module.

Không cam kết một feature luôn chỉ cần một folder: thay đổi signed payload, ABI, policy/session semantics hoặc migration cần review SDK, contracts, backend, fixtures và tests cùng lúc. Người làm các feature độc lập nên hạn chế sửa các file composition dùng chung; tách PR nhỏ với interface ổn định.

## Trước khi bàn giao

```sh
uv sync --locked
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python -m pytest -q
uv run --locked python tools/contracts/foundry.py forge test -vv
uv run --locked python tools/quality/scan_secrets.py
```

Chạy focused tests trong lúc phát triển; cuối thay đổi kiến trúc/protocol chạy regression phù hợp. Frontend: `node tools/quality/check_frontend.mjs` và kiểm tra trình duyệt. Signed fields: chạy cả V1/V2 viem vectors. Không tự regenerate fixtures/schema để che regression. Không chạy formatter vào ignored reference/dependencies/virtualenv.

Giữ README gần code luôn đúng. Nếu thêm env, cập nhật template phù hợp, default/validation, người cần lấy giá trị đó và hướng dẫn deploy. Không in secrets trong test/log/PR. Không deploy Fuji hoặc hosting để kiểm tra refactor local.

## Git và rollback

Checkpoint trước refactor: `19aa935` trên nhánh `feat/pgs-implement-paper`; nhánh refactor: `refactor/modular-backend-frontend`. Có thể xem code cũ bằng `git show 19aa935:<path>` hoặc checkout vào worktree riêng. Không reset/xóa working tree để rollback khi còn thay đổi chưa commit. Code rollback không thay thế khôi phục DB/journal hay đảo giao dịch đã gửi lên chain.
