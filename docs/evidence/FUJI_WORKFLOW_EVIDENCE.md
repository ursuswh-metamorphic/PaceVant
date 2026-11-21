# Từ AI verdict đến giao dịch thật: một chuỗi bằng chứng Fuji

> **Public Fuji · 21/11/2026 · release-specific.** Bản này diễn giải [public acceptance JSON](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/public-fuji-live-acceptance-20261121.json) và [system review](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md); không chạy lại public transaction, không thay thế raw logs hoặc kiểm toán độc lập. [Quay về README](../../README.md).

## Câu hỏi: Có bằng chứng hệ thống đi qua các security gates trước khi ký không?

Có một **record gắn cùng job ID** từ execution report, chứa gate summaries, proof hash, attestation commitments, transaction hash và kết quả on-chain. Đây là **bằng chứng tích hợp từ báo cáo backend + RPC receipt**, mạnh hơn việc chỉ trưng một link Snowtrace; tuy nhiên không phải tất cả input/output từng security gate đều đã được phát hành công khai ở mức raw trace.

### Case A — SWAP_EXACT_IN đã được chấp nhận

- Job ID: `judge_05e0231adab44474a7fff9fcacd7c48e`
- Public receipt: [`0xa708f44e355b6926c02693282f8ca6514fd043199ae8d23d3a031d64f82e4b2d`](https://testnet.snowtrace.io/tx/0xa708f44e355b6926c02693282f8ca6514fd043199ae8d23d3a031d64f82e4b2d)
- Block: **61406870**; receipt status: **1 (success)**
- Domain: **Avalanche Fuji, chain ID 43113**, verifying contract: [PolicyVaultMVP](https://testnet.snowtrace.io/address/0x70e1395f959dba530cf4a53b060c809b715bb6d5)

| Câu hỏi cần kiểm chứng | Dữ liệu ghi trong acceptance JSON | Bằng chứng / giới hạn |
| --- | --- | --- |
| Cùng một luồng đã chạy qua những stage nào? | `OWNER_AUTHORITY` → `AGENT_PROPOSAL` → `BUILD` → `SIMULATION` → `RISK` → `ITAG` → `PROOF` → `SDE` → `ATTESTATION` → `EXACT_SIGNED_PREFLIGHT` → `OUTCOME` → `RECONCILIATION` | **Danh sách stage backend lưu**, không phải log full input/output của từng stage. |
| Economic Risk cho phép? | `risk=PASS` | Summary report; không chứng minh một cách độc lập mọi phép tính nếu thiếu raw risk trace. |
| ITAG chấp thuận? | `itag=PASS`, `semantic=ALIGNED` | Verdict của case **hợp lệ**; không chứng minh phát hiện malicious long-horizon attack trên Fuji. |
| Z3/Phi hợp lệ? | `proof=VERIFIED`, proof hash `0x2fbae3eb85abb9a9e32c127028641dac67fafbd2c154481bc8c70c9277d1244a` | Proof commitment từ backend report; full SMT queries/counterexamples không được nhúng trong JSON này. |
| SDE đưa quyết định gì? | `APPROVE` | Reported security verdict trước attestation. |
| Attestor ký cái gì? | Domain v3; signer `0x5704fa0ff7cbed213f622c99ac6f9d6e5cbf2989`; nonce **1003** | EIP-712 attestation summary; kiểm byte-level cần signature/typed payload và ABI/decoded calldata. |
| Ràng buộc calldata và Phi? | Typed-data hash `0xbb0ecb42f4bf3d6268c9a10ca6fd8687fd2faedc473f94b96f06d8f21c258661`; constraints hash `0xbe365f07bbe2c71488182774c6cb8d29fa71258658c3748b2e3a3954a1cda638` | Hash từ workflow report; để đối chiếu toàn vẹn phải tái lập typed-data theo source/ABI. |
| Blockchain có thực thi? | Receipt status 1; 61406870 | **Public tx** và receipt có thể kiểm từ explorer/RPC. |
| Tài sản thay đổi ra sao? | USDC **-1 base unit**; WAVAX **+13266545691051 wei** | Historical balance delta ghi từ public RPC, không lấy số do UI tự hiện. |
| Ai trả gas? | Relayer; 486946 gas × 160 wei/gas = **77911360 wei AVAX** | Report đã đối chiếu relayer balance debit **77911360 wei**. |

**Giải nghĩa:** AI chỉ đề xuất; quyết định ký đến sau Risk/ITAG/Z3/SDE. EIP-712 hash buộc approval vào operation/constraints cụ thể. Relayer gửi call, Vault kiểm on-chain. Receipt xác nhận token thực sự chuyển, không chỉ là lời khẳng định của dashboard.

**Ranh giới claim:** Khả năng của từng gate không thể xác nhận hoàn toàn từ Snowtrace vì TaskShield/ITAG/Z3 chạy off-chain. Chỉ khẳng định **có các stage/summary được lưu và có settlement public**; cần raw stage records + signature reconstruction để kiểm chứng end-to-end độc lập mạnh hơn.

### Case B — USDC_PAYMENT thành công

- Job: `judge_629e24508c1a45a59f2c188d8bf6f521`
- [Public payment receipt](https://testnet.snowtrace.io/tx/0x8f3c1b8f045bc80eeb49df2a85f45feb2fea07957402220ab60cd011a5b02642), block **61405956**, status **1**
- Người nhận được ghi nhận: `0x607bd883bd3621378812cf5b4b8ddccfaebbab1b`; **10000 USDC base units = 0,01 test USDC**.
- Gate summary: Risk **PASS**, ITAG **PASS**, Semantic **ALIGNED**, Z3 **VERIFIED**, SDE **APPROVE**.
- Dữ liệu tương tự đã được đối chiếu với recipient delta và relayer gas debit trong acceptance.

### Case C — Policy refusal: không có transaction là điều mong muốn

- Job: `judge_f1d45f6cc8414f62b22a9f86a1923daf`
- Reason: `PAYEE_NOT_ALLOWED`
- Status: `REJECTED`; `public_chain_broadcast=false`.
- Stage history: `OWNER_AUTHORITY` → `AGENT_PROPOSAL` → `REJECTION_OR_RECOVERY`.

Đây là **policy guard refusal**, không phải một long-horizon semantic attack. Vì bị từ chối trước ký, sẽ **không có transaction hash của hành động bị từ chối trên Snowtrace**. Đừng dùng screenshot explorer trống để suy ra hệ thống đã chặn prompt injection.

## Liên kết giữa proof và receipt: chỗ nào còn thiếu?

| Có thể xác minh trực tiếp ngay | Cần artifact/giải mã bổ sung |
| --- | --- |
| Public transaction hash, block, receipt status | Raw authenticated user task và toàn bộ planner/tool traces được chia sẻ an toàn |
| Token Transfer logs, balance deltas, gas | Raw TaskShield/ITAG graph, evidence catalog và semantic responses |
| Gọi đến PolicyVault/Adapter, on-chain events nếu ABI/topic được giải mã | SMT query/assumptions và Phi encoding đầy đủ |
| Hashes, signer, nonce có trong acceptance JSON | Independently reconstruct EIP-712 typed hash + signature from calldata |

**Không diễn giải sai:** `proof_hash` trong JSON không phải chứng nhận cryptographic on-chain proof; EVM không chạy Z3. Public Testnet receipts không phải independent audit hay kiểm thử tấn công adversarial trên Fuji.

## Cách tái kiểm tra (read-only)

1. Mở [swap tx](https://testnet.snowtrace.io/tx/0xa708f44e355b6926c02693282f8ca6514fd043199ae8d23d3a031d64f82e4b2d) và [payment tx](https://testnet.snowtrace.io/tx/0x8f3c1b8f045bc80eeb49df2a85f45feb2fea07957402220ab60cd011a5b02642). Kiểm status, to-address và token transfers.
2. Đối chiếu job ID cùng `gate_summary`, `attestation`, `vault_delta_base_units` trong [source JSON](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/public-fuji-live-acceptance-20261121.json).
3. Mở [Solidity implementation](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/contracts/src/PolicyVaultV3.sol) để hiểu vì sao nonce, domain, signature và Phi postconditions bắt buộc.
4. Muốn tái dựng EIP-712 byte-for-byte, phải dùng raw operation/Phi + ABI và đúng deployment. Chưa có full reproducer độc lập được cung cấp trong tài liệu này.

[Quay lại README](../../README.md) · [Kiến trúc giải thích đủ 16 bước](../architecture/ARCHITECTURE_EXPLAINED.md) · [Research Catalog](../research/EXPERIMENT_CATALOG.md).
