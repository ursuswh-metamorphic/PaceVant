# Báo cáo rà soát khả năng ghép A/B

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

> Historical / compatibility document. For the current runtime use [V2.1 system design](AI_Treasury_Security_System_Design_v2.1.md) and [readiness audit](audit/V2_1_READINESS_REVIEW.md). Old A/B layouts, PoC evidence and removed pre-refactor paths describe their original checkpoint; they are not current deployment instructions or new validation evidence. References to removed artifacts are retained as plain code text.

Ngày: 16/11/2026. Scope: code B hiện tại đối chiếu guide A/B và shared integration contract v1.1. Code A chưa được cung cấp; chưa có review chéo A.

## 1. Các phát hiện và xử lý

| ID | Phát hiện | Xử lý / bằng chứng |
|---|---|---|
| AB-01 | Hai service đều có Python namespace `app`, dễ import nhầm khi AI nối source | SDK độc lập `treasury_contracts`; consumer chạy `python -I` ở cwd khác, không import `app` |
| AB-02 | Response context/snapshot/submission chưa có model rõ để A generate client | Bổ sung shared `ChainContext`, `OnchainSnapshot`, `ExecutionSubmission`, error models; gắn response_model; export OpenAPI |
| AB-03 | PDR address casing hợp lệ bị so chuỗi khác checksum; web3.py không encode lowercase tự động | Binding bằng exact EIP-712 digest, ABI tuple chuyển checksum; independent consumer ký lowercase và thực thi thành công |
| AB-04 | A cần recheck nonce/policy trước ký nhưng không nên import backend B | Đóng gói ABI trong SDK, thêm read-only `read_approval_state`; test nonce false→true khi execute |
| AB-05 | SDK chỉ ném HTTPStatusError, A phải đoán envelope/correlation | `ExecutionAPIError` là subclass tương thích, expose code/retryable/correlation/status; không tự sign/retry |
| AB-06 | Cached PENDING execute có thể không rebroadcast khi RPC drop trước nhận tx | Execute retry refresh qua durable raw-tx journal; regression test cùng key gửi đúng bytes/cùng hash, daily spend chỉ tăng một lần |
| AB-07 | Node local idle làm context timestamp/deadline stale | `npm run local` mine block rồi bật interval 2s chỉ trên Anvil loopback; startup test quan sát block tăng/timestamp fresh |
| AB-08 | Validator uint256 áp cả opaque numeric IDs | Giới hạn range validator cho amount/uint/delta annotations; test intent ID 100 chữ số vẫn hợp lệ |
| AB-09 | A dễ nhầm B OnchainSnapshot là portfolio có giá | Typed snapshot và handoff ghi rõ prices/history/exposure thuộc A; không thêm giá giả vào response |
| AB-10 | `mandate_version` và Vault `policy_version` không cùng bộ đếm | Ghi rõ mapping qua owner-authorized policyHash; không yêu cầu hai version bằng nhau |
| AB-11 | Fixtures địa chỉ/deadline và source MOCK dễ bị dùng như report thật | Docs/source gates, mock evidence INCOMPLETE; consumer lấy runtime context và dùng real local simulation |
| AB-12 | Dễ merge nhầm root dependencies/lock hoặc khôi phục PoC | Playbook ownership/conflict matrix, giữ root Foundry và uv project riêng, chỉ commit env template |

Không đổi field order/type/domain Approval, không thêm arbitrary execution hoặc endpoint signing vào B. Các model mới mô tả response đã tồn tại; API routes chính và DTO giao dịch v1.1 được giữ.

## 2. Bằng chứng tự động

Lượt kiểm tra gần nhất: **27 Solidity + 34 Python tests pass**, thêm 256 fuzz runs, golden Python/viem/Solidity pass. SDK wheel isolation và independent HTTP consumer đều pass. Đây là kết quả của source B hiện tại; không bao gồm tests A chưa được cung cấp.

| Nhóm | Cách chạy | Ý nghĩa |
|---|---|---|
| Solidity core / golden | `npm run test:contracts` | Permission, nonce, exact call, budgets, rollback, signature Python→Solidity |
| Python/API/schema/config | `npm run test:python` | Strict wire, OpenAPI/ABI export, evidence, relayer, env/profile/lifecycle |
| Python↔viem golden | `npm run test:integration` | Digest, signer, calldata và canonical manifest agreement |
| Independent consumer HTTP | `npm run test:consumer` | SDK-only process đọc/build/sim/verify/preflight/sign/execute qua API thật |
| SDK wheel isolation | `evidence/shared-sdk-package.json` | Wheel cài được trong env không có `app`, ABI được đóng gói |
| Consumer result | `evidence/ab-consumer-acceptance.json` | Test protocol local pass; `a_implementation_exercised=false` |
| Existing execution proof | `evidence/execution-plane-local.json` | B real local swap và stress, không phải A SDE |
| Secret scan | `npm run scan:secrets` | Secrets đang cấu hình không xuất hiện trong source Git-visible |

Các tests thêm trong lần rà soát nằm tại `test_consumer_contract.py`, retry regression trong `test_integration.py`, và local idle regression trong `test_configuration.py`. Handoff manifest/schema/ABI/OpenAPI được test đối chiếu source để AI merge không âm thầm làm lệch interface.

## 3. Chưa kiểm chứng / cần A hoàn thành

| Gate | Trạng thái và việc cần làm |
|---|---|
| G0 shared review | Artifact/schema/ABI/golden đã có; cần A+B review chéo trước merge |
| G1 Vault | B tests pass theo evidence |
| G2 A SDE/risk/Shield | Chưa chạy vì không có source A |
| G3 cross-language signature | Golden và independent Python consumer pass; A attestor thật vẫn phải chạy cùng vector |
| G4 full A+B | Protocol probe pass không thay cho pipeline với immutable decision DB/attestor A thật |
| G5 A semantic negatives | B enforcement có test; injection/UNCERTAIN/stale-price/no-sign tests của A chưa có |
| G6 Fuji | Chưa deploy/execute PolicyVault mới trên Fuji; cần attestor public address, fork fidelity, test AVAX và receipt thật |

Không thể bảo đảm một branch A chưa nhìn thấy sẽ merge không conflict hoặc đúng logic. Có thể xác nhận **hợp đồng giao tiếp đã có test và đường tích hợp khả thi**; khi A tuân theo contract/SDK/playbook, các mismatch phổ biến ở phía B nêu trên đã được xử lý. Nghiệm thu cuối cần test A thật theo checklist trong tài liệu 07.

## 4. Giới hạn vận hành phải giữ khi merge

- Prototype local/Fuji dùng mock tokens/controlled adapter; không phải ERC-4337, không dùng tiền thật.
- Freshness và TTL ngắn cố ý fail closed; UI/LLM chậm phải chạy trước critical path hoặc tạo attempt mới.
- Quote/slippage/minOut và risk USD không phải cùng một loại bằng chứng; A chịu trách nhiệm prices/exposure.
- Stress là scripted state drift, không chứng minh bảo vệ mọi MEV.
- Receipt CONFIRMED mặc định dựa receipt status=1; chưa có chính sách nhiều confirmations/reorg/finality production.
- Snapshot API trả latest pinned read; không có endpoint tùy chọn block trong v1.1. A phải kiểm tra drift và nguồn phù hợp.
- B không giữ/kiểm tra DB SDE của A. Chữ ký trusted attestor là authorization boundary; decision_id không được thêm vào Approval khi chưa version hóa chung.
