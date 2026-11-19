# Xác minh backend một FastAPI — 19/11/2026

> Checkpoint gộp API trước lượt audit cuối. Kết quả mới và lỗi đã sửa nằm tại [readiness review](../audit/V2_1_READINESS_REVIEW.md); không cộng/trộn các lần chạy.

Kiến trúc hiện tại: [UNIFIED_BACKEND.md](UNIFIED_BACKEND.md). Checkpoint code trước refactor vẫn là `19aa935`; các thay đổi refactor/gộp API nằm trong working tree của nhánh `refactor/modular-backend-frontend`, chưa commit thêm.

| Kiểm tra đã chạy | Kết quả |
| --- | --- |
| Full Python suite | **146 passed, 1 skipped**, hai dependency deprecation warnings; không có failure |
| One-app composition | Một app/OpenAPI có workflow và `/execution` routes; auth operator/execution không thay thế nhau; shared execution instance, direct module injection và không có internal HTTP client pool |
| Full local operator | Compile/deploy -> alignment/risk/proof -> revalidation/Phi preflight -> signature -> durable relay -> receipt. Đạt khi PATH không có Node và cổng execution cũ đang bị chiếm; backend log chỉ có một Uvicorn startup |
| Full protocol regression | **14/14 outcomes matched**; original V1 hai API từ commit gốc, V2.1 một FastAPI với execution gọi trong process |
| Chrome headless | Bốn MOCK scenarios đạt: normal/exposure sau replan CONFIRMED, injection REJECTED, stale ESCALATED; không có uncaught JS exception |
| Desktop/mobile | Kiểm tra 1440×1100 và 390×844, không có horizontal overflow |
| Ruff, secret scan, diff whitespace | **PASS**; không có configured secret trong tracked/unignored source |
| `.env` hiện tại | Giữ nguyên bytes so với backup trước refactor; không cần secret mới |

Test bị skip là LOCAL ablation opt-in (`RUN_V2_ABLATION`), không phải Fuji smoke. Không có giao dịch Fuji hoặc deploy hosting. Solidity và shared proof formulas không đổi trong lần gộp API. Kết quả 49 Forge tests trước đó nằm ở [báo cáo refactor](REFACTOR_VALIDATION.md); không coi đó là một lần Forge rerun mới. Docker engine local chưa hoạt động: chưa build/run image/Compose hoặc kiểm chứng Render/VPS; CI đã có container jobs.

## Lệnh và artifacts

```sh
uv run --locked python -m pytest -q
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python tools/quality/scan_secrets.py
uv run --locked python tools/evaluation/evaluate_protocol.py --output .control-data-v2/unified-protocol-results.json
```

[Tóm tắt protocol](unified-protocol-summary.json) ghi metadata, scope và outcomes của lần chạy mới; giữ nguyên các benchmark lịch sử trong `docs/evaluation`. Đây là regression 7 records mỗi cấu hình trên owned Anvil, không phải load benchmark hoặc dự báo hiệu năng Fuji/Render.

Artifacts local được Git ignore: `.control-data-v2/unified-all-tests.log`, `unified-protocol.log`, `unified-protocol-results.json`, `unified-ui.json`; ảnh `.control-data-ui/unified-desktop.png`, `unified-mobile.png`. UI dùng hồ sơ Chrome tạm và MOCK, không đọc session cá nhân. Full protocol dùng local identities riêng, không đọc root `.env` hoặc gửi Fuji.

## Giới hạn kiến trúc

Một runtime có attestor + relayer keys; module separation không phải process isolation. Owner key vẫn bị loại khỏi serving environment. Simulation dùng Anvil fork process tạm và vẫn cần native Anvil trên server. Oracle thực tế chưa merge, DEX/planner LLM chưa tích hợp. SQLite và relay journal vẫn yêu cầu một instance/worker và durable storage.
