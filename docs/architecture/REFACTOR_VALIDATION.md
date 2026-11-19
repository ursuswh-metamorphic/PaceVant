# Xác minh refactor module — 19/11/2026

> Báo cáo dưới đây ghi nhận lần refactor trước khi gộp API. Checkpoint runtime một FastAPI nằm trong [UNIFIED_VALIDATION.md](UNIFIED_VALIDATION.md); kết quả audit cuối nằm tại [readiness review](../audit/V2_1_READINESS_REVIEW.md).

Checkpoint trước refactor: `19aa935`, nhánh `feat/pgs-implement-paper`. Công việc refactor nằm trên `refactor/modular-backend-frontend`. [Kiến trúc](MODULE_ARCHITECTURE.md), [bản đồ module](../../backend/MODULES.md), [deploy](../../deploy/README.md).

## Kết quả đã chạy

| Kiểm tra | Kết quả | Phạm vi |
| --- | --- | --- |
| Toàn bộ Python | **144 passed, 1 skipped** | Một root environment; control, execution, integration, architecture và oracle colocated tests. Bao gồm full local operator workflow khi không có Node trên PATH |
| Focused control + architecture sau dọn import | **49 passed** | Workflow, gate, revalidation và dependency direction |
| Solidity Foundry | **49 passed** | Vault V1/V2, signatures, atomic rollback, Phi/budgets, directional caps và fuzz/golden cases |
| V1 và V2 viem vectors | **PASS** | Python/JavaScript digest, signer, calldata/canonical hashes; V2 Phi ABI và version isolation |
| Frontend syntax | **8 files passed** | Tất cả browser JS modules/config |
| Chrome headless | **4 scenarios passed** | MOCK normal -> CONFIRMED; exposure -> replan rồi CONFIRMED; injection -> REJECTED; stale price -> ESCALATED. Không có uncaught JavaScript exception |
| Desktop/mobile | **PASS** | Xem ảnh ở 1440×1100 và 390×844; không tràn ngang. Hồ sơ trình duyệt tạm, không dùng session cá nhân |
| Full protocol comparison | **14/14 outcomes matched** | Original V1 từ commit `1b09bd8dd04fd74868f30634abeec93276522d36` và code V2.1 hiện tại, trên owned Anvil 31337 |
| Ruff | **PASS** | `backend/src backend/tests tools` theo cấu hình exclusions hiện tại |
| Secret scan | **PASS** | Source tracked/unignored không chứa giá trị secret cấu hình; private paths vẫn được ignore |
| Source preservation | **PASS** | SHA256 `.env` khớp backup trước refactor; file implementation plan gốc giữ nguyên bytes |

Một test LOCAL ablation opt-in (`RUN_V2_ABLATION`) được skip có chủ đích; không có live Fuji smoke trong default suite. Hai warning Python còn lại là deprecation từ websockets/Starlette dependencies; không có test failure.

Trong quá trình di chuyển đã sửa tham chiếu consumer probe, handoff manifest, V2 viem fixture và tool generators sang đường dẫn mới. Không thay wire schema/ABI/proof formulas để làm tests pass. B OpenAPI và packaged ABI vẫn được consumer regression đối chiếu với implementation/artifacts.

## Bằng chứng và chạy lại

Lệnh chuẩn trong [backend tests](../../backend/tests/README.md). Tóm tắt benchmark mới được lưu tại [refactor-protocol-summary.json](refactor-protocol-summary.json); đây là regression giới hạn 7 records mỗi cấu hình, không phải load test hoặc bằng chứng production latency. Kết quả đo lịch sử trong `docs/evaluation/` không bị ghi đè.

Artifacts riêng trên máy, được Git ignore:

- `.control-data-v2/refactor-tests-release.log`: full Python suite cuối.
- `.control-data-v2/refactor-final-focused.log`, `refactor-forge.log`: kiểm tra focused và contracts.
- `.control-data-v2/refactor-protocol-results.json`: raw benchmark 14 records; logs/state dưới `evaluation/run-20261119-122838`.
- `.control-data-v2/refactor-ui.json`: kết quả browser; `.control-data-ui/refactor-desktop.png` và `refactor-mobile.png`: ảnh đã xem.
- `.control-data-v2/refactor-backup-20261119-115430`: backup trước refactor. `.control-data-v2/legacy-app-caches`: virtualenv/cache cũ được lưu lại, không được runtime sử dụng.

## Phần chưa xác minh

Docker Desktop Linux engine local chưa hoạt động nên chưa build/run backend/frontend image hoặc Compose. CI đã cập nhật build và kiểm tra runtime không có Node/npm/Forge, cùng kiểm tra Nginx config; chưa có kết quả CI từ thay đổi này. Cần image smoke, restart/persistence và host health/workflow test trước khi tuyên bố deploy thành công.

Không gửi giao dịch Fuji, không deploy Render/VPS và chưa có manifest V2 Fuji thật. Oracle thật của cộng tác viên chưa merge; provider/external writer seam không phải bằng chứng đã tích hợp market feed. DEX thật và planner LLM chưa có. Chạy một backend instance vì SQLite/journal hiện tại chưa hỗ trợ HA.
