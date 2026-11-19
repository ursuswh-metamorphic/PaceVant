# Chỉ mục tài liệu

## Vận hành V2.1 hiện tại

- [Backend Python trên Render/VPS, không cần Node.js](deployment/PYTHON_BACKEND_RENDER_VPS.md): native Forge/Anvil, Docker build/runtime, persistent storage và secrets không có owner key.

- [Đối chiếu V2.1 và phần còn lại trước tích hợp thực tế](migration/v2_1_readiness_review.md): chức năng đã có, phạm vi MVP, oracle merge, planner/DEX và phần chưa kiểm chứng trên Fuji.

- [Luồng xử lý, ví và vai trò Python/Node.js](CURRENT_SYSTEM_FLOW.md): kiến trúc thực tế, hai lớp chữ ký, proof/SDE/vault, trạng thái và công cụ phát triển.

- [Chạy toàn bộ local và demo Avalanche Fuji](demo/AVALANCHE_FUJI_DEMO.md): cài đặt, ba ví, env/đơn vị, deploy, dashboard, gia hạn và xử lý lỗi.
- [Trạng thái môi trường và phần cần thao tác bên ngoài nếu có](demo/ENVIRONMENT_STATUS.md): đã điền đủ cấu hình demo, không chứa secret.
- [Migration/rollback](migration/v2_1_runbook.md), [tiến độ/test evidence](migration/v2_1_progress.md), [file thay đổi](migration/v2_1_changed_files.md).
- [Proof assumptions](security/proof_assumptions_v2_1.md), [policy coverage](security/policy_coverage_v2_1.md), [ABI/hash vectors](security/abi_hash_vectors_v2_1.md).
- [Original V1/V2.1 full-protocol comparison](evaluation/full_protocol_results.md), [four-mode ablation](evaluation/v1_vs_v2_1_ablation.md), raw results đi kèm trong cùng thư mục.

Các guide/handoff v1.1 bên dưới giữ vai trò tài liệu nền và API legacy. Dùng `treasury:*` trong runbook demo để chạy full V2.1.

## Đọc để implement và merge A/B

1. [Shared integration contract v1.1](03_SHARED_INTEGRATION_CONTRACT.md): API/units/EIP-712/ownership chuẩn.
2. [Guide A](01_GUIDE_PERSON_A_CONTROL_PLANE.md) và [guide B](02_GUIDE_PERSON_B_EXECUTION_PLANE.md): phạm vi và acceptance tests từng người.
3. [Handoff A/B chi tiết](06_AB_INTEGRATION_HANDOFF.md): code thực tế, SDK, response models, signing, evidence, retries, config và gates.
4. [AI merge playbook/prompt](07_AI_MERGE_PLAYBOOK.md): dùng khi đưa code hai người cho AI ghép.
5. [Compatibility audit](08_AB_COMPATIBILITY_AUDIT.md): bug/mismatch đã xử lý, bằng chứng và phần chưa thể xác nhận khi thiếu code A.
6. [Machine-readable index](handoff/integration-manifest.json): file/route/model/commands cần giữ khi merge.

## Chạy và vận hành B

- [Runbook B](04_PERSON_B_RUNBOOK.md): local/Fuji, một `.env`, API, cách lấy public attestor address.
- [Cấu trúc repository](05_PROJECT_STRUCTURE.md): source mới, lệnh npm, quy tắc dọn PoC và tình trạng lịch sử Git cũ.
- [System Design v1.0](AI_Treasury_Security_System_Design_v1.0.md): kiến trúc nền; guide/team split v1.1 ưu tiên khi khác nhau.
- [Shared SDK](../packages/contracts-api/README.md), [OpenAPI](../packages/contracts-api/openapi.json), [fixtures](../fixtures/README.md).

## Tài liệu lịch sử — không dùng làm execution path hiện tại

`LEGACY_POC_README.md`, `ARCHITECTURE.md`, `RESEARCH.md`, `FEASIBILITY_REPORT.md`, `SMART_ACCOUNTS.md`, `SMART_ACCOUNT_RESULTS.md`, `TEST_RESULTS.md`, `WALLET_SETUP.md` mô tả các thử nghiệm Avalanche/Hardhat/AA trước khi chuyển sang PolicyVault. Chúng được giữ để tham khảo; các source/manifest/screenshot cũ đã bị loại khỏi working tree. Không lấy địa chỉ Fuji cũ làm địa chỉ PolicyVault mới.
