# Chỉ mục tài liệu

## Đọc để implement và merge A/B

1. [Shared integration contract v1.1](03_SHARED_INTEGRATION_CONTRACT.md): API/units/EIP-712/ownership chuẩn.
2. [Guide A](01_GUIDE_PERSON_A_CONTROL_PLANE.md) và [guide B](02_GUIDE_PERSON_B_EXECUTION_PLANE.md): phạm vi và acceptance tests từng người.
3. [Handoff A/B chi tiết](06_AB_INTEGRATION_HANDOFF.md): code thực tế, SDK, response models, signing, evidence, retries, config và gates.
4. [AI merge playbook/prompt](07_AI_MERGE_PLAYBOOK.md): dùng khi đưa code hai người cho AI ghép.
5. [Compatibility audit](08_AB_COMPATIBILITY_AUDIT.md): bug/mismatch đã xử lý, bằng chứng và phần chưa thể xác nhận khi thiếu code A.
6. [Machine-readable index](handoff/integration-manifest.json): file/route/model/commands cần giữ khi merge.

## Chạy và vận hành B

- [Portfolio / Outcome Monitor v2](PORTFOLIO_OUTCOME_MONITORING.md): snapshot, worker chỉ đọc không cần khóa ký, API và migration SQLite.
- [Báo cáo triển khai và kiểm thử Portfolio/Outcome](PORTFOLIO_OUTCOME_REPORT.md).

- [Runbook B](04_PERSON_B_RUNBOOK.md): local/Fuji, một `.env`, API, cách lấy public attestor address.
- [Cấu trúc repository](05_PROJECT_STRUCTURE.md): source mới, lệnh npm, quy tắc dọn PoC và tình trạng lịch sử Git cũ.
- [System Design v1.0](AI_Treasury_Security_System_Design_v1.0.md): kiến trúc nền; guide/team split v1.1 ưu tiên khi khác nhau.
- [Shared SDK](../packages/contracts-api/README.md), [OpenAPI](../packages/contracts-api/openapi.json), [fixtures](../fixtures/README.md).

## Tài liệu lịch sử — không dùng làm execution path hiện tại

`LEGACY_POC_README.md`, `ARCHITECTURE.md`, `RESEARCH.md`, `FEASIBILITY_REPORT.md`, `SMART_ACCOUNTS.md`, `SMART_ACCOUNT_RESULTS.md`, `TEST_RESULTS.md`, `WALLET_SETUP.md` mô tả các thử nghiệm Avalanche/Hardhat/AA trước khi chuyển sang PolicyVault. Chúng được giữ để tham khảo; các source/manifest/screenshot cũ đã bị loại khỏi working tree. Không lấy địa chỉ Fuji cũ làm địa chỉ PolicyVault mới.
