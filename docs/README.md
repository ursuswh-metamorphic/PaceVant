# Chỉ mục tài liệu PaceVant

> **DOC STATUS: CURRENT_INDEX** — chuẩn hóa 20/11/2026, runtime source baseline `3f9f9af`. Đây là điểm vào để tránh trộn tài liệu cũ với hiện trạng.

## Bộ tài liệu hiện hành

| Tài liệu | Dùng để làm gì? |
| --- | --- |
| [Hồ sơ gửi AI phản biện — một file](PACEVANT_CURRENT_SYSTEM_REVIEW.md) | Bản tự chứa: hiện trạng, từng thành phần/input-output, thật/mock/giả định, bằng chứng, thiếu sót và câu hỏi phản biện |
| [System Design V2.1](AI_Treasury_Security_System_Design_v2.1.md) | Canonical as-built design: kiến trúc, module input/output, dữ liệu, API, security, proof, flows, budgets, accounting/recovery, limitations và evidence |
| [Reviewer Guide](REVIEWER_GUIDE.md) | Gói tham chiếu cho ban giám khảo/AI, thứ tự đọc và câu hỏi phản biện |
| [Demo User runbook](demo/DEMO_USER_GAS_CREDIT.md) | Chọn account không nhập token, gas credit và thao tác demo |
| [Sanitized inventory](current-system-inventory.json) | Cấu hình effective đã lọc, public addresses, 15 modules, source fingerprints; không có secret |
| [API catalog](current-api-catalog.json) | Methods/routes/auth/source trích tĩnh từ canonical composition |
| [Documentation manifest](DOCUMENTATION_MANIFEST.json) | Trạng thái từng tài liệu và SHA-256 của artifacts; đường tới tài liệu thay thế |
| [Module map](../backend/MODULES.md) | Ownership/dependency rules, README cục bộ trong mỗi module |
| [Deploy guidance](../deploy/README.md) | Phạm vi hosting, secret/storage boundaries và template cũ chưa được chuẩn hóa |

Source/config thực tế và evidence đúng scope là căn cứ đối chiếu. Design là bản tổng hợp hiện trạng, không phải chứng nhận độc lập hay lời hứa mọi máy đang sẵn sàng demo. Không có RPC/model/transaction mới trong đợt viết docs này.

## Cách đọc nhãn

| Nhãn | Ý nghĩa |
| --- | --- |
| `CURRENT_SYSTEM_DESIGN` | Một bản mô tả hệ thống hiện tại, có source baseline và giới hạn kiểm chứng |
| `CURRENT_*` | Chỉ mục/runbook/catalog/inventory hiện hành; vẫn đọc phạm vi của từng file |
| `MODULE_REFERENCE` / `COMPONENT_REFERENCE` | Tài liệu cạnh source mô tả interface/ownership; không tự chứng nhận live readiness |
| `HISTORICAL_DESIGN` / `HISTORICAL_RUNBOOK` / `HISTORICAL_REFERENCE` | Bản cũ hoặc snapshot; đọc để hiểu lịch sử, không áp các default/địa chỉ/kết luận cũ cho runtime mới |
| `HISTORICAL_AUDIT` | Báo cáo tại checkpoint, không phải audit lại HEAD |
| `EVIDENCE_ARTIFACT` | Raw JSON/SMT/SVG được giữ nguyên bytes, scope gắn ở manifest/README liên quan |
| `HISTORICAL_TEMPLATE` | Template deployment chưa theo profile hiện tại; không copy để chạy demo Fuji hiện tại |

## Tài liệu cũ được giữ ở đâu?

Tài liệu cũ giữ nguyên đường dẫn để không làm mất liên kết/handoff, nhưng đã thêm banner ngay đầu. [Design trước chuẩn hóa](archive/AI_Treasury_Security_System_Design_v2.1.pre-review-3f9f9af.md) được lưu riêng. [V1 design](AI_Treasury_Security_System_Design_v1.0.md), [implementation plan](IMPLEMENTATION_PLAN_V1_TO_V2_1.md), guide A/B, migration, integration, research và evaluation đều là historical/reference theo manifest; tên file có chữ CURRENT/V2.1 không vượt qua nhãn trạng thái.

[Bộ SVG cũ](architecture/diagrams/README.md) là snapshot kiến trúc trước chuẩn hóa, không có diagram one-click/gas ledger đầy đủ; diagrams mới nằm trực tiếp dưới dạng Mermaid trong canonical design. Không sửa SVG/SMT/receipt cũ để làm giống lần chạy mới.

## Bằng chứng nên xem cùng scope

- [Core Fuji live report](audit/system-security-live-validation.json), [security review](audit/SYSTEM_SECURITY_REAL_DATA_REVIEW.md), [SMT verification](audit/system-security-live-proof/verification.json): core đã chạy Fuji trước Demo User billing.
- [Demo gas credit validation](audit/demo-user-gas-credit-validation.json): offline/Anvil; không có public Fuji write.
- [One-click account validation](audit/demo-account-selection-validation.json): offline auth/API/ledger; không swap và chưa browser visual end-to-end.

Không cộng test counts lặp, không gọi skipped là passed, không lấy receipt core để tuyên bố phần bổ sung demo billing đã được chạy Fuji. Xem design mục 18–20 cho việc còn mở và cách chuẩn bị demo.
