# Cấu trúc repository hiện tại

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

Dự án đã chuyển từ `apps/control-plane`, `apps/execution-plane` và `apps/dashboard` sang một backend Python chia module và một frontend độc lập.

- [Kiến trúc và bảng đường dẫn trước/sau](architecture/MODULE_ARCHITECTURE.md).
- [Bản đồ module và dependency](../backend/MODULES.md).
- [Backend setup](../backend/README.md), [frontend](../frontend/README.md), [Solidity](../contracts/README.md), [tools](../tools/README.md).
- [Quy tắc phát triển nhóm](../CONTRIBUTING.md), [deploy](../deploy/README.md), [test](../backend/tests/README.md).

Một `pyproject.toml`, `uv.lock`, `.venv` ở root. `uv run treasury` là CLI full V2.1; `python -m treasury_backend.operations.execution` giữ CLI B legacy. Scripts cũ chỉ delegate. Không import package chung tên `app`.

Các guide A/B v1.1 mô tả giao thức và phân vai lịch sử; dùng module map để tìm code hiện tại. Không dùng tài liệu PoC cũ làm execution path. Thư mục tham khảo `Proof-Gated-Signing/`, virtualenv, runtime data và secrets vẫn không được commit.
