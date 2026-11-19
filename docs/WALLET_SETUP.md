# Tạo ví test Fuji từng bước trên Windows

> Historical / compatibility document. For the current runtime use [V2.1 system design](AI_Treasury_Security_System_Design_v2.1.md) and [readiness audit](audit/V2_1_READINESS_REVIEW.md). Old A/B layouts, PoC evidence and removed pre-refactor paths describe their original checkpoint; they are not current deployment instructions or new validation evidence. References to removed artifacts are retained as plain code text.

Dự án đã hoàn tất local và deploy/demo Fuji thành công; xem [kết quả thực tế](TEST_RESULTS.md). Hướng dẫn này phục vụ tạo bộ ví test mới khi cần. Bạn tự thao tác phần tạo ví và khóa trên máy, không gửi secret vào chat.

## 1. Cài Core trên Chrome

Mở [core.app](https://core.app/), chọn Download và bản extension cho Chrome. Đi từ website này đến Chrome Web Store. Hướng dẫn chính thức: [tạo ví Core](https://support.core.app/en/articles/6100129-core-extension-how-do-i-create-a-new-wallet).

Mở extension → chọn tạo ví mới thủ công (`Manually create new wallet`). Dùng ví mới dành riêng cho PoC. Ghi recovery phrase ở nơi riêng an toàn, xác nhận các từ theo yêu cầu, đặt mật khẩu. Không chụp/gửi recovery phrase, không đưa vào source hoặc `.env`. Chọn tạo thủ công vì CLI PoC cần private key C-Chain; wallet seedless không hỗ trợ xuất private key trực tiếp như wallet mnemonic.

## 2. Tạo hai tài khoản trong ví test mới

Tài khoản đầu đặt tên `UniHack Owner`. Bấm tên account ở đầu extension → My Wallets → chọn ví → Add Account, đặt tên account mới `UniHack Agent`. Hai account có địa chỉ khác nhau, cùng trong ví test vừa tạo; không cần tạo hai seed phrase. Không dùng bất kỳ account nào để giữ tài sản thật.

Nguồn thao tác Add Account: [Core Support](https://support.core.app/en/articles/6105932-what-if-additional-accounts-are-not-showing-a-balance-after-re-installing).

## 3. Chuyển Testnet và lấy địa chỉ C-Chain

Trong Core mở Settings và bật Testnet mode. Chọn Avalanche Fuji, chain ID **43113**. Hướng dẫn: [Core Quickstart](https://docs.core.app/docs/introduction/quickstart/), [Avalanche Academy](https://build.avax.network/academy/avalanche-l1/avalanche-fundamentals/03-multi-chain-architecture-intro/06-setup-core).

Copy địa chỉ **C-Chain/EVM bắt đầu `0x`** của từng account; không dùng địa chỉ `P-…`, `X-…` hoặc `fuji…`. Địa chỉ công khai có thể cung cấp để kiểm balance. Recovery phrase/private key thì không.

Nếu phải thêm mạng thủ công:

| Trường | Giá trị |
|---|---|
| Network | Avalanche Fuji C-Chain |
| RPC | https://api.avax-test.network/ext/bc/C/rpc |
| Chain ID | 43113 |
| Symbol | AVAX |
| Explorer | https://explorer-test.avax.network/c-chain |

## 4. Nhận test AVAX miễn phí

Mở [faucet chính thức](https://build.avax.network/console/primary-network/faucet). Tạo/đăng nhập Builder Hub nếu được yêu cầu, kết nối Core, chọn Fuji **C-Chain** và claim test AVAX. Làm cho cả Owner và Agent theo điều kiện/cooldown faucet thực tế. Không cần token USDC/P-Chain cho PoC này, không dùng nút Buy, không mua AVAX thật.

Kiểm tra cả hai account có balance trên Fuji C-Chain. Nếu faucet hết vốn, rate limit hoặc yêu cầu điều kiện chưa đáp ứng, giữ BLOCKED và nhờ hỗ trợ ban tổ chức/mentor. Không thử trang faucet ngẫu nhiên hoặc trả tiền để mở khóa. [Academy chính thức](https://build.avax.network/academy/avalanche-l1/avalanche-fundamentals/03-multi-chain-architecture-intro/06-setup-core) mô tả Builder Hub account + wallet cho bước claim; điều kiện giao diện có thể thay đổi.

## 5. Cấu hình khóa trên máy, không qua chat

Trong VS Code mở thư mục `D:\Projects\blockchain\test-blockchain` và file `.env`. Đã có file khung nếu trước đó chưa tồn tại. File này được Git ignore.

Với từng account trong Core: bấm tên account → Options cạnh account → Show Private Key → chọn **C-Chain/EVM** → nhập mật khẩu và Reveal. Dán trực tiếp vào `.env` trong editor, không dán terminal/chat. [Hướng dẫn xuất khóa chính thức](https://support.core.app/en/articles/8832783-core-extension-how-do-i-export-my-private-key).

Điền:

| Biến trong `.env` | Giá trị cần đặt cục bộ |
|---|---|
| `DEPLOYER_PRIVATE_KEY` | Private key C-Chain của UniHack Owner, dạng `0x` và 64 ký tự hex |
| `AGENT_PRIVATE_KEY` | Private key C-Chain của UniHack Agent, cùng định dạng |
| `AGENT_ADDRESS` | Địa chỉ công khai `0x…` của UniHack Agent |
| `FUJI_TEST_WALLETS_ONLY` | `true` sau khi xác nhận đây là hai account test |
| `VITE_NETWORK` | `fuji` |

Không nhập recovery phrase vào bất kỳ biến nào. Nếu Core không có Show Private Key, kiểm tra có đang dùng wallet mnemonic vừa tạo hay không; wallet email/seedless và hardware có giới hạn khác. Không dùng công cụ chuyển seed thành key trực tuyến.

Đến đây chỉ cần báo “đã cấu hình ví test và nhận test AVAX”, không gửi nội dung `.env`. Tôi có thể chạy preflight/deploy mà không in khóa.

## 6. Những lệnh tiếp theo

Khi đủ điều kiện, quy trình đã chuẩn bị:

```powershell
npm run check-network
npm run deploy:fuji
npm run demo:fuji
```

Nếu bạn tự chạy, giữ output để xem hash/receipt công khai. Lệnh deploy tự compile/test/typecheck; chain không phải 43113 sẽ bị chặn. Không đặt mainnet RPC. Deployment chỉ được coi PASS khi có receipt success, bytecode và state xác minh qua RPC. Xem [README](../README.md) cho frontend và các kịch bản.
