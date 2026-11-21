# Thư viện nghiên cứu PaceVant — Chỉ mục đầy đủ

## Cập nhật công khai — nguồn current trước khi đọc báo cáo lịch sử

Tại checkpoint **21/11/2026**, PaceVant đã có [website public](https://pacevant.live) với **PolicyVaultMVP** và các operation giới hạn **USDC_PAYMENT / SWAP_EXACT_IN**. Giao dịch payment và swap trên Fuji được đối soát bằng [public acceptance report](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/public-fuji-live-acceptance-20261121.json). Frontend dùng React/TypeScript/Vite; `develop` là nhánh public deploy; `main` cung cấp source/docs mới để review, còn nhánh README này giữ code ở checkpoint cũ và **không merge**.

**Đọc trước các nguồn hiện hành:** [System Review 21/11](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md) · [Public Fuji Runbook](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PUBLIC_FUJI_RUNBOOK.md) · [EVM / Vault Code](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/contracts/src/PolicyVaultMVP.sol) · [Economics & proof audit](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/MVP_ECONOMIC_RISK_AUDIT.md).

**Nghiên cứu được kế thừa và phân biệt novelty:** [PACE — Policy-Attested Contract Execution](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/paper/PACE_Policy_Attested_Contract_Execution.md) và [Proof-Gated Signing](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/paper/Proof_Gated_Signing_Solver_Checked_Transaction_Guards.md). ITAG + evidence-grounded semantic purpose là hướng khác biệt nhóm đang kiểm chứng; PDR, simulation và Z3 không được tự nhận là phát minh hoàn toàn mới.

**E08–E09 — Public acceptances và merger provenance:** [Experiment Catalog](EXPERIMENT_CATALOG.md#e08--current-public-mvp-paymentswap-fuji-21112026). Giữ các research topics R01–R13 dưới đây làm **bản đồ tích lũy**, bao gồm những module không thuộc current public route.

---



> **Trạng thái:** REVIEW INDEX, tổng hợp từ source/doc/evidence của repository tại checkpoint 21/11/2026. Đây là chỉ mục nghiên cứu, **không** thay thế raw evidence hay tuyên bố kiểm toán độc lập. Các tài liệu lịch sử có checkpoint riêng; không đồng nhất kết quả cũ với source HEAD.

## Mục tiêu của thư viện

PaceVant không chỉ là một demo blockchain. Đây là chuỗi nghiên cứu và triển khai về **AI Agent Security cho tài sản số**: làm sao một AI Agent có thể lập kế hoạch nhưng không tự mở rộng quyền, làm sai mục tiêu, bị prompt injection dẫn dắt hoặc gây thiệt hại kinh tế dù transaction hợp lệ.

Mỗi hướng nghiên cứu được lưu với bốn lớp:

1. **Vấn đề và threat model:** kẻ tấn công có quyền gì, người dùng đã ủy quyền điều gì?
2. **Phương pháp:** thuật toán, kiến trúc, dữ liệu, boundary và assumptions.
3. **Thực nghiệm:** baseline, ablation, số mẫu, real/scripted inference, run commands, artifacts.
4. **Kết luận và giới hạn:** cải tiến nào thực sự có bằng chứng; kết quả nào chưa khái quát được?

## Bản đồ nghiên cứu

| ID | Chủ đề | Đóng góp đã xây dựng | Tài liệu nguồn |
| --- | --- | --- | --- |
| R01 | Single-transaction intent alignment | TaskShield gốc → Hybrid source-bound TaskShield, binding/constraints/semantic/fusion | [Thiết kế](../security/HYBRID_TASK_ALIGNMENT.md), [Kết quả](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md), [Lỗi](../evaluation/HYBRID_TASK_ALIGNMENT_ERRORS.md) |
| R02 | Long-horizon task / budget verification | Authenticated IntentSpec, graph, history, step/task budget, revalidation | [Temporal module](../../backend/src/treasury_backend/modules/temporal/README.md), [Final evaluation](../evaluation/itag-final/FINAL_VALIDATION.md) |
| R03 | Graph-aware semantic purpose verification | Evidence catalog, typed nodes/edges, real-model semantic reasoning, strict fusion | [Semantic reliability report](../evaluation/itag-semantic-reliability/FINAL_REPORT.md) |
| R04 | Adversarial tool-output security | Task authority, provenance, tool interception, recipient/policy/forged-user injection | [Alignment module](../../backend/src/treasury_backend/modules/alignment/README.md), [Web demo](../demo/LIVE_WEB_DEMO.md) |
| R05 | Forked execution & baseline simulation | Exact calldata, pinned fork, balance/allowance/log differences | [Simulation](../../backend/src/treasury_backend/modules/execution/simulation/README.md), [System design](../AI_Treasury_Security_System_Design_v2.1.md) |
| R06 | MEV / economic stress | Adversarial reserve-shift scenarios, 20/200-bps stresses, effect bounds | [Simulation](../../backend/src/treasury_backend/modules/execution/simulation/README.md), [System design](../AI_Treasury_Security_System_Design_v2.1.md) |
| R07 | Portfolio and economic risk | Exposure, budget, oracle price provenance, economic gating | [Risk module](../../backend/src/treasury_backend/modules/risk/README.md), [Oracle](../../backend/src/treasury_backend/modules/oracle/README.md) |
| R08 | Bounded formal verification | Z3, Phi, bounded token deltas/allowances, conditional proof | [Proof module](../../backend/src/treasury_backend/modules/proof/README.md), [Contracts API](../../packages/contracts-api/README.md) |
| R09 | Authenticated decisions & enforcement | SDE, signed PDR V2, attestor, PolicyVault/adapter, anti-replay | [Contracts](../../contracts/README.md), [Signing](../../backend/src/treasury_backend/modules/signing/README.md) |
| R10 | End-to-end consistency | Task/decision revalidation, calldata binding, final preflight, reservation | [System design](../AI_Treasury_Security_System_Design_v2.1.md), [Workflows](../../backend/src/treasury_backend/modules/workflows/README.md) |
| R11 | Public testnet evidence | Fuji swap, Chainlink, LFJ, verified receipt/effects | [Live web review](../audit/WEB_DEMO_LIVE_REVIEW.md), [Fuji evidence](../audit/web-demo-fuji-chain-evidence.json) |
| R12 | Reliability and recoverability | Raw-tx journal, idempotency, pending/reorg, gas credit accounting | [Web review](../audit/WEB_DEMO_LIVE_REVIEW.md), [Gas credit](../../backend/src/treasury_backend/modules/gas_credit/README.md) |
| R13 | Engineering & modular security design | One FastAPI app, typed ports, import boundaries, automated regression | [Module map](../../backend/MODULES.md), [Architecture](../architecture/UNIFIED_BACKEND.md) |

### R01 — Vì sao TaskShield phải đổi thuật toán?

Bản đầu dùng **tổng contribution scores**: một deadline đúng có thể bù cho token đích sai. Sau khi phát hiện lỗi trên benchmark 300 mẫu, nhóm thử sửa aggregation nhưng tạo ra nhiều false rejects. Thiết kế Hybrid hiện tại dùng trusted user-source envelope, action-task binding, mandatory constraint verifier, semantic model và **strict fusion**. Baseline vs C/D: 49,00% → 95,67% accuracy; C và D bằng nhau trên cùng tập regression. [Xem chi tiết](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md).

**Bài học nghiên cứu:** model không nên tự chấm phép toán xác minh được; mục tiêu của AI là nhận diện ngữ nghĩa và drift, trong khi deterministic gate bảo vệ yêu cầu bắt buộc. Không dùng benchmark đã quan sát để tuyên bố generalization.

### R02–R03 — Temporal graph và đóng góp AI

Thử nghiệm ban đầu 24 trajectories: 8/12 adverse được ITAG deterministic chặn/can thiệp; 12/12 benign được giữ nguyên. Các purpose conflicts trong giới hạn số học là gap cần semantic reasoning. Bản graph model đầu tiên có **0 valid semantic findings** do lỗi evidence binding/schema; các phiên bản v3.x cải tiến bằng graph-bound evidence catalog, field selectors và factual grounding.

Kết quả cuối v3.2: 7/8 semantic conflict observations có lift hợp lệ, 9/10 benign approvals, nhưng có lặp và chưa có nhãn kiểm duyệt độc lập. Để chứng minh novelty nghiêm ngặt, cần **độc lập hóa cặp adverse/benign** và benchmark baseline deterministic + full semantic ở cùng điều kiện. [Final validation](../evaluation/itag-final/FINAL_VALIDATION.md) · [Reliability history](../evaluation/itag-semantic-reliability/FINAL_REPORT.md).

### R04 — Prompt injection và ranh giới quyền

Nguồn TOOL-role là **dữ liệu**, không phải user instruction. Chỉ authenticated user update / IntentSpec revision mới được cấp hay sửa quyền; model output không thể tạo task authority. Các bài lab dùng real configured provider cho một số challenge cố định, và offline/scripted cases cho workflow. Mỗi claim phải kèm cấu hình, model, trace và môi trường tương ứng. Không suy rộng thành “ngăn mọi prompt injection”.

### R05–R08 — Simulation → Risk → Proof

**Baseline simulation:** thực thi exact guarded call trên pinned Anvil fork, thu thập before/after, allowances, logs, revert và hashes. **Stress:** dựng actor giả định và perturb liquidity/reserve trên local fork; không biến giả định stress thành giá thị trường thực. **Risk:** dùng portfolio/chain/oracle/effect bounds; kiểm exposures và loss bound. **Proof:** Z3 giải bài toán hữu hạn trên assumptions cụ thể; Phi được biên dịch thành giới hạn enforce được trong PolicyVault.

Cần phân biệt bốn khái niệm: tính đúng của state diff, độ hợp lý của stress, tính hợp lệ có điều kiện của proof, và việc transaction thực sự thành công khi được include. Chúng không đồng nghĩa.

### R09–R12 — Từ quyết định đến giao dịch thật

Attestor ký PDR V2 chỉ sau revalidation; smart contract kiểm replay, sessions, caps, call commitment và postcondition tại execution. Relayer giữ raw tx journal, dành gas trước send và đối soát receipt/canonicality sau send. Demo User có sponsor allowance off-chain; không phải mô hình tiền gửi hay trả phí production.

**Public receipt:** [Snowtrace Fuji](https://testnet.snowtrace.io/tx/0x315a9bff8ba111487d295903ebd0f6389b1baefd40ea9526fc33bc014a9656ba) và [live report](../audit/WEB_DEMO_LIVE_REVIEW.md). Đây là checkpoint lịch sử có giá trị, không chứng minh code HEAD đã được chạy lại trên Fuji.

## Khuyến nghị cách đọc

- **Giám khảo hackathon (5 phút):** [README chính](../../README.md) → [Fuji evidence](../audit/WEB_DEMO_LIVE_REVIEW.md) → [TaskShield ablation](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md) → [ITAG final](../evaluation/itag-final/FINAL_VALIDATION.md).
- **AI Security researcher:** [TaskShield design](../security/HYBRID_TASK_ALIGNMENT.md) → [ITAG reliability](../evaluation/itag-semantic-reliability/FINAL_REPORT.md) → [Experiment Catalog](EXPERIMENT_CATALOG.md).
- **Blockchain/security auditor:** [System Design V2.1](../AI_Treasury_Security_System_Design_v2.1.md) → [Coverage Matrix](SECURITY_COVERAGE_MATRIX.md) → [Contracts](../../contracts/README.md) → [Fuji reports](../audit/WEB_DEMO_LIVE_REVIEW.md).
- **Người triển khai:** [Live runbook](../demo/LIVE_WEB_DEMO.md) → [Module map](../../backend/MODULES.md) → [Technology Inventory](TECHNOLOGY_INVENTORY.md).

## Bảo tồn nguồn gốc và tránh mất dữ liệu nghiên cứu

**Không xóa hoặc ghi đè raw logs, frozen labels, artifacts, historical docs** chỉ để README nhất quán với số liệu mới. Hãy phân biệt: (a) docs hiện hành cho architecture, (b) reports gắn checkpoint, (c) scripted tests, (d) real-model observations, (e) public chain receipts, (f) giả thuyết chưa kiểm thử. [Documentation manifest](../DOCUMENTATION_MANIFEST.json) và [docs index](../README.md) là cổng đi tới những tài liệu lịch sử còn lại.

Danh mục phương pháp, implementation và artifact được bổ sung trong [Technology Inventory](TECHNOLOGY_INVENTORY.md), [Experiment Catalog](EXPERIMENT_CATALOG.md) và [Security Coverage Matrix](SECURITY_COVERAGE_MATRIX.md). Những báo cáo này là **chỉ mục bổ sung**; không thay đổi bằng chứng gốc.
