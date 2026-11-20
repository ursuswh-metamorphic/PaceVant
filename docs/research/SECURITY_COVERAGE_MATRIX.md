# Ma trận bao phủ bảo mật PaceVant

> **Nguyên tắc:** bảng này phân biệt **có defense trong code**, **có regression**, **có local evidence**, và **có public Fuji evidence**. Một defense hiện diện không đồng nghĩa đã ngăn được mọi trường hợp tấn công trong thực tế.

## 1. Ranh giới tin cậy và tài sản

- **Owner / Treasury Mandate:** quản trị chính sách, token/router allowlist, sessions, pause, exposure và các giới hạn cấp cao. Owner compromise nằm ngoài bảo đảm “LLM không tự ý chuyển tiền”.
- **Authenticated operator / user task:** phát sinh IntentSpec, deadline, revision và ngân sách. **Chỉ nguồn đã xác thực được quyền thay đổi task.**
- **AI Planner / semantic evaluator:** nguồn đề xuất và đánh giá ngữ nghĩa, **không giữ signing key** và không được cấp quyền khi thiếu deterministic verification.
- **TOOL-role content / retrieved text:** nguồn không đáng tin cậy; có thể chứa prompt injection hoặc giả mạo quyền.
- **Execution, proof, price, attestor:** các dịch vụ off-chain có trust assumptions; data/evidence hashes gắn với build/session/call. Một proof có điều kiện không kiểm toán toàn bộ dịch vụ.
- **PolicyVault:** on-chain final boundary; kiểm chữ ký, commitments, session/caps/replay và postcondition enforce được; không diễn giải ý nghĩa ngôn ngữ tự nhiên.
- **Relayer và gas-credit:** relayer trả AVAX; sponsor gas credit trong DB không phải ví token của người dùng.

## 2. Threat → Detection → Enforcement → Evidence

| Threat / failure mode | Detection layer | Chặn tại đâu? | Bằng chứng đã lưu | Khoảng trống / giới hạn |
| --- | --- | --- | --- | --- |
| Swap sai token in/out / direction | TaskShield normalized constraint | TaskShield → SDE (pre-sign) | [300-case ablation](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md) | Benchmark chỉ là adapted Uniswap V2 component tests |
| Sai amount / đổi đơn vị | Source-bound constraints + decoder | Pre-sign | [Hybrid error analysis](../evaluation/HYBRID_TASK_ALIGNMENT_ERRORS.md) | Ngôn ngữ “khoảng”, USD/token ambiguities có thể UNCERTAIN |
| Wrong minOut / deadline | Constraint checks + proof/preflight | Pre-sign / guarded call | [Hybrid results](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md) | Quote/temporal context phải authoritative |
| Recipient redirection | User-source binding + deterministic recipient check | Pre-sign | [Web attack runbook](../demo/LIVE_WEB_DEMO.md) | Một số prompt-injection tests dùng lab; không chứng minh mọi variants |
| Forged user message in tool output | Authenticated provenance, semantic checks | TaskShield/ITAG pre-sign | [TaskShield design](../security/HYBRID_TASK_ALIGNMENT.md) | Context boundary/LLM may produce uncertainty |
| Unrelated positive score hides violation | Strict fusion mandatory veto | TaskShield | [A/B/C/D](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md) | Sửa aggregation đơn giản làm tăng false rejects |
| Multi-task action hijack | Task ID/revision binding, ITAG | TaskShield/ITAG | [Hybrid design](../security/HYBRID_TASK_ALIGNMENT.md) | Multi-intent ambiguity requires clarification |
| Cumulative task budget exceeded | ITAG deterministic history+reservation | Pre-sign and revalidation | [LOCAL budget isolation](../evaluation/itag-final/ANVIL_BUDGET_ISOLATION.json) | Test theo task rules; không khẳng định toàn bộ strategy |
| Invalid ordered dependency | Temporal verifier | Pre-sign | [ITAG final validation](../evaluation/itag-final/FINAL_VALIDATION.md) | Fixture authored, chưa independent benchmark |
| Purpose conflict within numeric bounds | Graph-aware semantic AI + evidence catalog | ITAG/SDE | [Semantic reliability](../evaluation/itag-semantic-reliability/FINAL_REPORT.md) | Small repeated samples; output schema/evidence failures |
| Exposure / economic drawdown | Portfolio+Chainlink, Economic Risk | SDE / on-chain caps | [System design](../AI_Treasury_Security_System_Design_v2.1.md) | Oracle/market risk assumptions |
| Slippage / sandwich-like stress | Anvil baseline + hypothetical reserve shocks | Simulation/risk/preflight | [Simulation module](../../backend/src/treasury_backend/modules/execution/simulation/README.md) | Stress scenarios not exhaustive MEV model |
| Replayed approval | Signed nonce/session/caps | **PolicyVault** | [Contract tests](../../contracts/test/README.md), [Web report](../audit/WEB_DEMO_LIVE_REVIEW.md) | Historical eth_call ≠ on-chain attack transaction |
| Modified calldata / signer | EIP-712 commitment, vault check | **PolicyVault** | [Web live review](../audit/WEB_DEMO_LIVE_REVIEW.md) | Attestor/key assumptions remain |
| Stale evidence / task revision | Pre-sign task + decision revalidation | Attestor / final preflight | [ITAG module](../../backend/src/treasury_backend/modules/temporal/README.md) | Time-of-check-to-use risk remains conditional |
| Receipt missing / RPC inconsistency | Durable journal, monitor, canonicality | Hold/retry/reconcile; no blind new write | [Web live review](../audit/WEB_DEMO_LIVE_REVIEW.md) | RPC can lag; cannot guarantee instant finality |
| Gas debit inaccurate / double charge | Reserve, settlement, idempotency, reorg ledger | Ledger consistency gate | [Web gas report](../audit/WEB_DEMO_LIVE_REVIEW.md) | Shared sponsor demo, not billing product |
| Model unavailable / invalid schema | Strict JSON + catalog grounding | UNCERTAIN / ESCALATE, **no signing** | [Semantic reliability](../evaluation/itag-semantic-reliability/FINAL_REPORT.md) | Safety preserved at expense of liveness |

## 3. Những điều on-chain enforcement **thực sự** bảo đảm

Trong cấu hình contract/policy đang deploy, khi vault chấp nhận một call, nó có thể kiểm điều kiện **mã hóa được trong EVM**: signer/session/caps, target/adapter và calldata commitment, nonce/replay, và những token delta / allowance postconditions đã biên dịch.

Nó **không** tự chứng minh rằng:
- LLM hiểu đúng user goal, purpose hoặc tool content.
- Graph model đã phân loại đúng semantic attack.
- Chainlink quote phản ánh giá trị kinh tế thực/redeemability của test assets.
- Mọi MEV/market manipulation đã được mô phỏng.
- Trusted owner/attestor/process/operator/key không bị xâm phạm.
- Z3 conditional proof bao trùm mọi trạng thái chain hoặc mọi hành vi arbitrary contracts.

Vì vậy câu claim được phép dùng là **“off-chain evidence-bound authorization + final on-chain policy enforcement trong phạm vi route/contract được hỗ trợ”**, không phải “AI đảm bảo giao dịch an toàn tuyệt đối”.

## 4. Các mức bằng chứng cần gắn với claim

| Mức | Ví dụ | Được phép suy ra |
| --- | --- | --- |
| Source only | File implementation có module/rule | Có code; chưa khẳng định pass |
| Unit/integration test | pytest/Forge | Property được test đạt trong environment |
| Scripted scenario | canned LLM/fixtures | Wiring, invariant và deterministic behavior |
| Real-model lab | DeepSeek evaluation traces | Model response trên đúng scenarios đã đo |
| LOCAL Anvil | Actual local receipts/revert/nonce | Enforcement trên local EVM context |
| Public Fuji receipt | Confirmed tx + verified effects | Một execution thực trong checkpoint cụ thể |
| Independent external audit | Chưa có | **Không được tuyên bố** |

## 5. Kiểm định còn mở

1. Independent adversarial evaluation với những mẫu chưa dùng để thiết kế parser/prompt.
2. Public Fuji end-to-end smoke trên bản Hybrid TaskShield mới nhất, tách với historical receipts.
3. Đo chất lượng semantic interpretation (không chỉ schema validity); báo cáo false interventions / uncertainty.
4. Kiểm tra hoạt động trên nhiều protocol/route và session ownership độc lập trước khi mở rộng quyền.
5. Review chuyên sâu owner/attestor compromise, secret isolation, RPC/oracle trust, reorg, PDR/call binding và concurrency.
6. Kiểm toán độc lập trước bất kỳ bản mainnet hoặc tài sản thật nào.

[Research Index](RESEARCH_INDEX.md) · [Technology Inventory](TECHNOLOGY_INVENTORY.md) · [Full system design](../AI_Treasury_Security_System_Design_v2.1.md)
