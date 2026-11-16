# Kết quả kiểm thử thực tế

Ngày đánh giá: 12/11/2026 (Asia/Saigon). Timestamps JSON dùng UTC.

## Tổng quan

| Kiểm tra | Trạng thái | Bằng chứng |
|---|---|---|
| Unit tests | PASS | 41 pass / 0 fail; unit-results.json |
| Compile Cancun và TypeScript | PASS | Solidity 0.8.38, compile/typecheck exit 0 |
| Frontend production build | PASS | Vite exit 0; còn cảnh báo chunk/worker_threads |
| UI bản build qua preview | PASS | production-ui.json; đọc storage/event Fuji thật |
| Kiểm khóa không lọt source/bundle | PASS | secret-scan.json; .env bị Git ignore |
| Fuji RPC | PASS | Chain 43113, block 60940282; network.json |
| UI Chrome headless | PASS | 4 pass / 0 fail; ui-results.json |
| Fuji E2E A–E | PASS | e2e-fuji.json |
| Đọc lại receipt/code/state/log Fuji | PASS | verify-fuji.json |
| Smart account ERC-4337 Fuji AA1–AA7 | PASS | aa-e2e-fuji.json; SMART_ACCOUNT_RESULTS.md |
| Đọc lại UserOperationEvent/nonce/ownership | PASS | aa-verify-fuji.json |
| Ký bằng Core/MetaMask extension thật | NOT TESTED | UI local dùng wallet adapter; CLI Fuji dùng local signer |
| Explorer source verification | NOT TESTED | Runtime bytecode đã so khớp qua RPC; chưa xác minh source trên explorer |
| npm audit | FAIL | 5 high full tree; 1 high omit-dev, cùng advisory Zod |

## Fuji deployment thực tế

Chain **43113**. Owner/agent là hai ví test được kiểm chứng từ khóa cục bộ; khóa không có trong báo cáo.

| Contract | Address | Deploy transaction | Block | Gas used | Fee test AVAX |
|---|---|---|---:|---:|---:|
| AvalancheStorage | [0xd3361fb2c1547f1fec5f9d877d63e5a3346e4489](https://explorer-test.avax.network/c-chain/address/0xd3361fb2c1547f1fec5f9d877d63e5a3346e4489) | [0xd15c7f5d889b3966765d09d4cacb94c4a78fc8b588c5bbb8ecf971a28870dc26](https://explorer-test.avax.network/c-chain/tx/0xd15c7f5d889b3966765d09d4cacb94c4a78fc8b588c5bbb8ecf971a28870dc26) | 60940172 | 212119 | 0.00000000003393904 |
| AgentTreasuryGuard | [0x487f648a58f93164b39ddce8db48ae57684c4c65](https://explorer-test.avax.network/c-chain/address/0x487f648a58f93164b39ddce8db48ae57684c4c65) | [0x5f4b3ccccd05f2d06f5859f687c7168d6c208ca6e505e14a1b6d1a558973a4b3](https://explorer-test.avax.network/c-chain/tx/0x5f4b3ccccd05f2d06f5859f687c7168d6c208ca6e505e14a1b6d1a558973a4b3) | 60940175 | 847896 | 0.00000000013566336 |

## Fuji E2E A–E

| Thao tác | Receipt status | Block | Gas used | Fee test AVAX | Transaction hash |
|---|---|---:|---:|---:|---|
| A: storage update | success | 60940246 | 30319 | 0.00000000000485104 | [0x58dd4840933e36181ae20055e5e8dba57d5f967568c33298d525be740ad3e4b5](https://explorer-test.avax.network/c-chain/tx/0x58dd4840933e36181ae20055e5e8dba57d5f967568c33298d525be740ad3e4b5) |
| B: allow controlled owner recipient | success | 60940249 | 28033 | 0.00000000000448528 | [0xfb58294cf9320cb2b02c0120477389711ee56abda771a4048fda0ed3230bef9b](https://explorer-test.avax.network/c-chain/tx/0xfb58294cf9320cb2b02c0120477389711ee56abda771a4048fda0ed3230bef9b) |
| B: set small limit | success | 60940252 | 26959 | 0.00000000000431344 | [0xea8731c12a98c011b79f4a24503068f0fc79925b65551379e7503142a499655a](https://explorer-test.avax.network/c-chain/tx/0xea8731c12a98c011b79f4a24503068f0fc79925b65551379e7503142a499655a) |
| B: treasury deposit | success | 60940258 | 22491 | 0.00000000000359856 | [0xe67f6af3ec50df8389aacb0c0acb86b69442bc86753e469b139411282ac93885](https://explorer-test.avax.network/c-chain/tx/0xe67f6af3ec50df8389aacb0c0acb86b69442bc86753e469b139411282ac93885) |
| B: agent proposes | success | 60940262 | 122043 | 0.00000000001952688 | [0xb57bc656d4d7cb9f21cd6fd4cf5a2d73829350f66ef49c07cda11ea8a4a94faa](https://explorer-test.avax.network/c-chain/tx/0xb57bc656d4d7cb9f21cd6fd4cf5a2d73829350f66ef49c07cda11ea8a4a94faa) |
| B: owner approves | success | 60940263 | 62620 | 0.0000000000100192 | [0x7de62e00b3a9b0944e94c70048c01bd2563485650fbde6b737df075c8be87aaf](https://explorer-test.avax.network/c-chain/tx/0x7de62e00b3a9b0944e94c70048c01bd2563485650fbde6b737df075c8be87aaf) |
| B: owner executes | success | 60940270 | 58600 | 0.000000000009376 | [0xd397f12b2f4ae8ced51b309153429187207574d3a8265584f52be6695f964974](https://explorer-test.avax.network/c-chain/tx/0xd397f12b2f4ae8ced51b309153429187207574d3a8265584f52be6695f964974) |
| C: above limit rejected | reverted | 60940279 | 75000 | 0.000000000012 | [0x88d6151941be0aee3061201667babd84223b2cb768302bd9658c0828ec3d9778](https://explorer-test.avax.network/c-chain/tx/0x88d6151941be0aee3061201667babd84223b2cb768302bd9658c0828ec3d9778) |
| D: agent recipient disabled | success | 60940286 | 28021 | 0.00000000000448336 | [0x6deb8c6fe735b78f699dc6d9d63400a650e6fb502062ea0b4fa3963809902c7b](https://explorer-test.avax.network/c-chain/tx/0x6deb8c6fe735b78f699dc6d9d63400a650e6fb502062ea0b4fa3963809902c7b) |
| D: disallowed recipient rejected | reverted | 60940287 | 75000 | 0.000000000012 | [0x66437cf30aa56ae6faa294cef0d033364768f6465504668490bdd5740b825e0f](https://explorer-test.avax.network/c-chain/tx/0x66437cf30aa56ae6faa294cef0d033364768f6465504668490bdd5740b825e0f) |
| E: agent cannot execute | reverted | 60940290 | 75000 | 0.000000000012 | [0x2e85f1010059cd9134c80c623d356363b41de9b5247d3a57a356023a66c93cd7](https://explorer-test.avax.network/c-chain/tx/0x2e85f1010059cd9134c80c623d356363b41de9b5247d3a57a356023a66c93cd7) |

A kiểm giá trị storage và event ValueChanged. B kiểm Pending → Approved → Executed, balance treasury giảm đúng amount và balance owner tăng amount trừ phí execute. C/D/E kiểm đúng lỗi bằng eth_call, gửi giao dịch revert thật, đối chiếu receipt và proposalCount không đổi. Revert đúng kỳ vọng là PASS của kịch bản bảo mật, vẫn tốn gas.

Đọc lại độc lập tại block **60940386**: storage **2**, proposalCount **1**, proposal cuối status **2 (Executed)**, treasury **0.0001 test AVAX**. Bytecode cả hai contract khớp artifact. Các event Created/Approved/Executed đều có trên RPC.

Tổng phí của **18 giao dịch Fuji** được lưu (gồm deploy, funding, lần demo đầu dừng do agent thiếu gas và lần demo cuối): **0.00000000029278448 test AVAX**. Đây là số đo receipt tại thời điểm chạy, không phải báo giá tương lai. Transfer funding 0.0005 sang ví agent và balance 0.0001 còn trong treasury không phải gas.

## Local và giao diện

Local chain **31337**, E2E A–E: PASS. Receipt local ở evidence/deploy-local-*.json và e2e-local.json; không dùng làm bằng chứng Fuji.

Danh sách unit tests: [unit-tests.txt](../evidence/unit-tests.txt). UI: [ui-results.json](../evidence/ui-results.json), [desktop](../evidence/dashboard-desktop.png), [mobile](../evidence/dashboard-mobile.png), [Fuji](../evidence/fuji-dashboard.png). UI đối chiếu storage Fuji trực tiếp với RPC, hiển thị hai địa chỉ contract và event ProposalExecuted; không dùng private key trong trình duyệt.

## Khó khăn đã xử lý

Agent ban đầu không có gas: lần demo đầu dừng, bằng chứng giữ ở e2e-fuji-attempt1.json. Sau đó funding 0.0005 test AVAX từ owner đã kiểm soát sang agent đã kiểm soát; receipt ở fund-agent-fuji.json. Demo đã có preflight agent balance để chặn trước khi bắt đầu lần sau.

Public Fuji RPC thực tế giới hạn eth_getLogs tối đa 100 block/request. Verifier và UI ban đầu dùng range lớn hơn nên thất bại; đã chia lô 100 block, storage không quét trước block deploy, và chạy lại phần bị ảnh hưởng. Trình duyệt gặp CORS/HTTP 429: đã dùng proxy cùng origin, batch, cache block mới, tránh refresh đồng thời và tôn trọng Retry-After 60 giây. Gas revert Fuji đo được khác local; báo cáo dùng receipt thực từng mạng.

Web reader không truy cập được các URL Explorer deployment trong lần thử. Liên kết công khai ở trên có thể mở thủ công; không báo đã kiểm UI Explorer/source verification. Runtime/state/log đã đối chiếu trực tiếp với RPC.
