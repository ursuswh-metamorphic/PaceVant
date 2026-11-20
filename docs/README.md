# Chỉ mục tài liệu

Current Demo User addition: [single account + prepaid-style gas credit design/runbook](demo/DEMO_USER_GAS_CREDIT.md), [implementation test scope](audit/demo-user-gas-credit-validation.json). Full treasury security gates are preserved; public Fuji writes were not used to test this addition.

Live update 2026-11-20: [Circle / Chainlink / full Fuji demo](demo/FUJI_LIVE_END_TO_END.md). Earlier faucet-USDC blockers and controlled/mock descriptions below belong to their historical profiles.


## Nguồn đọc chính cho phiên bản hiện tại

1. [System design V2.1 hiện tại](AI_Treasury_Security_System_Design_v2.1.md): toàn bộ kiến trúc/module, luồng, proof, dữ liệu, quyền, API, storage, env và triển khai.

   Bản phản biện có 20 mục, 10 sơ đồ và [bộ hình SVG độc lập](architecture/diagrams/README.md), cùng threat model, invariants, tradeoffs và câu hỏi review.
2. [Rà soát code và mức sẵn sàng](audit/V2_1_READINESS_REVIEW.md): đối chiếu plan, mock/legacy inventory, lỗi đã sửa, tests và phần chưa chạy thật. [Evidence JSON](audit/validation-summary.json).
3. [Chạy LOCAL / demo Fuji](demo/AVALANCHE_FUJI_DEMO.md), [deploy backend/frontend](../deploy/README.md), [bản đồ module](../backend/MODULES.md).

Thiết kế hiện tại là một FastAPI/Uvicorn, Python backend và Solidity vault; LOCAL có proof/giao dịch/receipt thật trên Anvil với token, adapter và giá demo. Chưa có actual V2 Fuji deployment/receipt hoặc hosted smoke evidence. Các báo cáo migration/validation cũ phía dưới là checkpoint lịch sử; ưu tiên báo cáo rà soát mới khi số test hoặc runtime khác nhau.

## Kiến trúc module và phát triển nhóm

- [Một FastAPI: workflow + execution, module mô phỏng](architecture/UNIFIED_BACKEND.md), [xác minh runtime gộp](architecture/UNIFIED_VALIDATION.md).

- [Kiến trúc mới, đường dẫn trước/sau và luồng](architecture/MODULE_ARCHITECTURE.md).
- [Bản đồ module](../backend/MODULES.md), [quy tắc đóng góp](../CONTRIBUTING.md), [backend](../backend/README.md), [frontend](../frontend/README.md).
- [Deploy backend/frontend](../deploy/README.md), [test](../backend/tests/README.md), [kết quả refactor](architecture/REFACTOR_VALIDATION.md).

README từng module nằm ngay trong folder code của module đó. Guide A/B v1.1 bên dưới là nền giao thức/phân vai lịch sử; cấu trúc mới là nguồn chỉ dẫn đường dẫn hiện tại.

## Vận hành V2.1 hiện tại

- [Groq planner và đồng bộ env/ví](integrations/GROQ_PLANNER_AND_ENV.md): real strict-schema API, independent validation, durable quotas/cache/cooldown, test evidence và phần vẫn mock.
- [Oracle Fuji và LFJ trên V2.1](integrations/FUJI_LFJ_V2_1.md) ghi luồng read-only, đường mô phỏng, phần được chuyển từ main và rào cản định giá trước khi ký.

- [Backend Python trên Render/VPS, không cần Node.js](deployment/PYTHON_BACKEND_RENDER_VPS.md): native Forge/Anvil, Docker build/runtime, persistent storage và secrets không có owner key.

- [Đối chiếu V2.1 và phần còn lại trước tích hợp thực tế](migration/v2_1_readiness_review.md): chức năng đã có, phạm vi MVP, oracle merge, planner/DEX và phần chưa kiểm chứng trên Fuji.

- [Luồng xử lý, ví và vai trò Python/Node.js](CURRENT_SYSTEM_FLOW.md): kiến trúc thực tế, hai lớp chữ ký, proof/SDE/vault, trạng thái và công cụ phát triển.

- [Chạy toàn bộ local và demo Avalanche Fuji](demo/AVALANCHE_FUJI_DEMO.md): cài đặt, ba ví, env/đơn vị, deploy, dashboard, gia hạn và xử lý lỗi.
- [Trạng thái môi trường và phần cần thao tác bên ngoài nếu có](demo/ENVIRONMENT_STATUS.md): đã điền đủ cấu hình demo, không chứa secret.
- [Migration/rollback](migration/v2_1_runbook.md), [tiến độ/test evidence](migration/v2_1_progress.md), [file thay đổi](migration/v2_1_changed_files.md).
- [Proof assumptions](security/proof_assumptions_v2_1.md), [policy coverage](security/policy_coverage_v2_1.md), [ABI/hash vectors](security/abi_hash_vectors_v2_1.md).
- [Original V1/V2.1 full-protocol comparison](evaluation/full_protocol_results.md), [four-mode ablation](evaluation/v1_vs_v2_1_ablation.md), raw results đi kèm trong cùng thư mục.

Các guide/handoff v1.1 bên dưới giữ vai trò tài liệu nền và API legacy. Dùng `treasury:*` trong runbook demo để chạy full V2.1.

## Tài liệu nền/compatibility A/B — không phải layout deploy hiện tại

1. [Shared integration contract v1.1](03_SHARED_INTEGRATION_CONTRACT.md): API/units/EIP-712/ownership chuẩn.
2. [Guide A](01_GUIDE_PERSON_A_CONTROL_PLANE.md) và [guide B](02_GUIDE_PERSON_B_EXECUTION_PLANE.md): phạm vi và acceptance tests từng người.
3. [Handoff A/B chi tiết](06_AB_INTEGRATION_HANDOFF.md): code thực tế, SDK, response models, signing, evidence, retries, config và gates.
4. [AI merge playbook/prompt](07_AI_MERGE_PLAYBOOK.md): dùng khi đưa code hai người cho AI ghép.
5. [Compatibility audit](08_AB_COMPATIBILITY_AUDIT.md): bug/mismatch đã xử lý, bằng chứng và phần chưa thể xác nhận khi thiếu code A.
6. [Machine-readable index](handoff/integration-manifest.json): file/route/model/commands cần giữ khi merge.

## Runbook/thiết kế V1 và B-only lịch sử

- [Runbook B](04_PERSON_B_RUNBOOK.md): local/Fuji, một `.env`, API, cách lấy public attestor address.
- [Cấu trúc repository](05_PROJECT_STRUCTURE.md): source mới, lệnh npm, quy tắc dọn PoC và tình trạng lịch sử Git cũ.
- [System Design v1.0](AI_Treasury_Security_System_Design_v1.0.md): kiến trúc nền; guide/team split v1.1 ưu tiên khi khác nhau.
- [Shared SDK](../packages/contracts-api/README.md), [OpenAPI](../packages/contracts-api/openapi.json), [fixtures](../fixtures/README.md).

## Tài liệu lịch sử — không dùng làm execution path hiện tại

`LEGACY_POC_README.md`, `ARCHITECTURE.md`, `RESEARCH.md`, `FEASIBILITY_REPORT.md`, `SMART_ACCOUNTS.md`, `SMART_ACCOUNT_RESULTS.md`, `TEST_RESULTS.md`, `WALLET_SETUP.md` mô tả các thử nghiệm Avalanche/Hardhat/AA trước khi chuyển sang PolicyVault. Chúng được giữ để tham khảo; các source/manifest/screenshot cũ đã bị loại khỏi working tree. Không lấy địa chỉ Fuji cũ làm địa chỉ PolicyVault mới.
