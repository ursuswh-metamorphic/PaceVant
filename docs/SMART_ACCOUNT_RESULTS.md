# Kết quả tích hợp smart account ERC-4337

> **DOC STATUS: HISTORICAL_AUDIT - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

> Historical / compatibility document. For the current runtime use [V2.1 system design](AI_Treasury_Security_System_Design_v2.1.md) and [readiness audit](audit/V2_1_READINESS_REVIEW.md). Old A/B layouts, PoC evidence and removed pre-refactor paths describe their original checkpoint; they are not current deployment instructions or new validation evidence. References to removed artifacts are retained as plain code text.

Ngày đánh giá 12/11/2026, Asia/Saigon. Dữ liệu đo lấy từ JSON evidence, không giả lập blockchain.

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Unit tests | PASS | 41 pass / 0 fail, gồm 14 tests ERC-4337 |
| Local AA1–AA7 | PASS | aa-e2e-local.json |
| Deploy Fuji | PASS | aa-deploy-fuji-status.json |
| Fuji AA1–AA7 | PASS | aa-e2e-fuji.json |
| Đọc lại code/owner/nonce/receipt độc lập | PASS | aa-verify-fuji.json |
| UI | PASS | 4 pass / 0 fail; ui-results.json |
| Extension wallet thật | NOT TESTED | Browser test dùng adapter, EIP-712 được ký qua node local thật |
| Public production bundler, paymaster, session keys, recovery | NOT TESTED | Chưa triển khai; relay hiện tại là demo loopback tối giản |

## Deployment Fuji · chain 43113

| Thành phần | Address |
|---|---|
| account | [0x12a399c202d4090e7cbcda3aa9e281ea5a47930f](https://explorer-test.avax.network/c-chain/address/0x12a399c202d4090e7cbcda3aa9e281ea5a47930f) |
| storage | [0xa3ed358087891cc31d257bbcf145c1442cfbae3c](https://explorer-test.avax.network/c-chain/address/0xa3ed358087891cc31d257bbcf145c1442cfbae3c) |
| treasury | [0xb0929efaa3b407fcf748408e2ba97b8bc2ab720e](https://explorer-test.avax.network/c-chain/address/0xb0929efaa3b407fcf748408e2ba97b8bc2ab720e) |
| entryPoint | [0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108](https://explorer-test.avax.network/c-chain/address/0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108) |

Deploy account: [0xef533787c097dbd8c0aa3867d72dd6f2b078c2b5ada1883d3aa07ab8f516d2d3](https://explorer-test.avax.network/c-chain/tx/0xef533787c097dbd8c0aa3867d72dd6f2b078c2b5ada1883d3aa07ab8f516d2d3).

| Deploy contract | Gas used | Transaction |
|---|---:|---|
| UniHackSmartAccount | 792746 | [0xef533787c097dbd8c0aa3867d72dd6f2b078c2b5ada1883d3aa07ab8f516d2d3](https://explorer-test.avax.network/c-chain/tx/0xef533787c097dbd8c0aa3867d72dd6f2b078c2b5ada1883d3aa07ab8f516d2d3) |
| AvalancheStorage | 212119 | [0x98ccb1bd02c22e8b07003cc208c7dc721a8ca1b639c8d342a293f74e8737456f](https://explorer-test.avax.network/c-chain/tx/0x98ccb1bd02c22e8b07003cc208c7dc721a8ca1b639c8d342a293f74e8737456f) |
| AgentTreasuryGuard | 847896 | [0x677ec48ea77b65694f9e703308b3ff27fc8722bb732dfece5313e47e117d178e](https://explorer-test.avax.network/c-chain/tx/0x677ec48ea77b65694f9e703308b3ff27fc8722bb732dfece5313e47e117d178e) |

## UserOperations Fuji

| Kịch bản | UserOp success | UserOp hash | Transaction hash | Gas EntryPoint tính cho op | Phí account trả | Outer transaction fee |
|---|---|---|---|---:|---:|---:|
| AA1: owner-signed storage update through relay and EntryPoint | true | `0x9cb567cc10883aca2c5876196ea2dc6f7afd01cb1a324e5fbffe5742ba028774` | [0xde96202655ccd75d30f3199ae47b8be540bb36e2e19f2b395a93ba3cab62b91d](https://explorer-test.avax.network/c-chain/tx/0xde96202655ccd75d30f3199ae47b8be540bb36e2e19f2b395a93ba3cab62b91d) | 208568 | 0.00000000003337088 | 0.00000000007894864 |
| AA3: owner approves and executes atomically in one UserOperation | true | `0x5d2535ea0b2c5142dcf86887163de8e9ebc9339377efd2a1485ef01903f70c81` | [0x99a7b3fcbba4aa67f07bf861c2f01e22ce9ddac25842347293ff08fa1a8c153e](https://explorer-test.avax.network/c-chain/tx/0x99a7b3fcbba4aa67f07bf861c2f01e22ce9ddac25842347293ff08fa1a8c153e) | 221590 | 0.0000000000354544 | 0.00000000007780192 |
| AA7: failed batch has UserOp success=false and rolls back storage | false | `0xac96be498b771902e6bee0747527a87d0f6c4d23b848cb18bfb40eb8fe1e37fa` | [0x50e0cfb659a281c63ab581407eab18932aeb7bdafdedd6beb760e77f7af596f5](https://explorer-test.avax.network/c-chain/tx/0x50e0cfb659a281c63ab581407eab18932aeb7bdafdedd6beb760e77f7af596f5) | 191153 | 0.00000000003058448 | 0.0000000000778112 |

Ba UserOperations trong demo: account được EntryPoint tính **0.00000000009940976 test AVAX**; tổng outer transaction fee đo được **0.00000000023456176 test AVAX**. Đây là hai đại lượng có khoản reimbursement giữa account và relayer, không cộng lại như hai khoản phí mạng độc lập. Trong lần đo Fuji, outer fee lớn hơn reimbursement, relayer phải bù chênh lệch **0.000000000135152 test AVAX**. Không khẳng định gasless hoặc relayer được hoàn đủ phí.

AA1 cập nhật storage qua relay và EntryPoint. AA2 agent EOA tạo proposal vào treasury mới. AA3 owner ký một batch approve+execute. AA4 replay, AA5 agent giả signer, AA6 sửa calldata: bị EntryPoint eth_call validation từ chối trước khi broadcast, nonce không đổi. AA7 cố ý làm lệnh thứ hai lỗi: outer receipt success nhưng event success=false, storage rollback và nonce tăng. Đây là PASS của kịch bản kiểm tra rollback, không phải một operation thành công.

Đọc lại: signer **0x607bd883bd3621378812CF5B4B8dDcCFAeBbab1b**, nonce **3**, storage **1**, proposal status **2 (Executed)**, deposit **0.00099999990059024 test AVAX**. Account/storage/treasury runtime bytecode và ownership được xác minh qua RPC.

Xem [SMART_ACCOUNTS.md](SMART_ACCOUNTS.md) để chạy lại và hiểu phạm vi. Các contract EOA cũ không được chuyển ownership; treasury AA mới có địa chỉ riêng và owner là smart account. Session key, passkey, recovery, multisig, account factory, ERC-1271 và paymaster chưa có.
