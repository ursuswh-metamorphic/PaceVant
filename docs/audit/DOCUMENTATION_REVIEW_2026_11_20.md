# Documentation review — 20/11/2026

> **DOC STATUS: CURRENT_REVIEW_REPORT** — kiểm tra tài liệu so với runtime source baseline `3f9f9af`. Không phải một security audit hoặc Fuji validation mới.

[Canonical design](../AI_Treasury_Security_System_Design_v2.1.md) được viết lại theo code/config/evidence hiện có: 15 modules, unified API, real Chainlink/LFJ path, Shield/ITAG/SMT/signing, Solidity enforcement, monitoring/recovery, one-click demo và gas accounting. [Reviewer guide](../REVIEWER_GUIDE.md), [index](../README.md), [sanitized inventory](../current-system-inventory.json) và [API catalog](../current-api-catalog.json) tạo thành bộ tham chiếu hiện tại.

Docs cũ có banner `HISTORICAL_*`; README cạnh module/component được đánh dấu reference, không chứng nhận live readiness. Design trước đợt review được [lưu riêng](../archive/AI_Treasury_Security_System_Design_v2.1.pre-review-3f9f9af.md). Không thay đổi raw receipt JSON, SMT queries hoặc SVG lịch sử. [Manifest](../DOCUMENTATION_MANIFEST.json) lưu classification và SHA-256 của artifacts.

Kiểm tra tái lập từ repository root:

```powershell
uv run --locked python tools/quality/check_documentation.py
uv run --locked python tools/quality/scan_secrets.py
git diff --check
```

Checker kiểm classification, current local links/anchors, source fingerprints và artifact hashes/catalog integrity. Nó không render Mermaid hoặc kiểm external URLs, không đọc env/call RPC, không chạy model, browser, full unit suite hay transaction. Secret scanner riêng đọc env cục bộ và chỉ báo đường dẫn vi phạm, không in giá trị.

Kết quả kiểm tra tĩnh: **PASS**, manifest 181 entries, 67 Markdown lịch sử đã đánh dấu, 57 API routes; 21 source fingerprints khớp. Toàn bộ 50 JSON/SMT/SVG cũ giữ nguyên SHA-256 so với trước chỉnh docs. Ruff cho checker và configured-secret scan đều pass; không có configured secret xuất hiện trong file được scan. Liên kết hiện hành không có target/anchor thiếu; năm target evidence thiếu thuộc tài liệu lịch sử được công khai ở dưới.

Hash `sha256`/source fingerprints ghi exact bytes của checkout đã review. Do Git có thể chuyển LF/CRLF giữa Windows/Linux, manifest/inventory còn ghi hash LF cho source và artifact text thông thường. Checker chỉ chấp nhận chuyển đổi line endings đó, không thay nội dung; SMT queries vẫn kiểm exact bytes. Quy tắc này chỉ phục vụ documentation integrity, không thay cách hash source/proof/evidence trong security pipeline.

Một số historical reports trỏ tới evidence local không có trong repository hiện tại: `portfolio-outcome-validation.json`, `task-shield-xingchi-live.json`, `itag-live-model-review.json`, `itag-live-workflow-review.json`, `itag-live-workflow-review-final.json`. Những link thiếu này được checker báo riêng, không tạo file giả để lấp bằng chứng. Không dùng chúng làm nguồn chứng nhận. Bộ current design liên kết tới các artifact thực sự tồn tại.

Known issues về runtime/production được đưa vào design mục 18 thay vì sửa bằng docs: chưa có Fuji transaction riêng cho demo billing/one-click, chưa browser visual verification, session/funding/providers cần kiểm lúc demo, hosting template cũ, shared demo/SQLite và chưa có payment/multi-user/HA/independent audit. Không thay env, policy/session, contracts hoặc runtime logic trong đợt chuẩn hóa này.
