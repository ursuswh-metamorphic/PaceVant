# Lưu trữ tài liệu README của PoC trước khi dọn dự án

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

> Historical / compatibility document. For the current runtime use [V2.1 system design](AI_Treasury_Security_System_Design_v2.1.md) and [readiness audit](audit/V2_1_READINESS_REVIEW.md). Old A/B layouts, PoC evidence and removed pre-refactor paths describe their original checkpoint; they are not current deployment instructions or new validation evidence. References to removed artifacts are retained as plain code text.

Tài liệu lịch sử. Source PoC đã được loại khỏi working tree; xem `05_PROJECT_STRUCTURE.md` về khả năng khôi phục nếu còn clone/backup Git cũ. Các lệnh và đường dẫn PoC bên dưới không thuộc dự án hiện tại.

Phần B mới theo kế hoạch ngày 16/11/2026: `PolicyVault`, swap mock USDC → WAVAX, builder deterministic, simulation/stress trên pinned Anvil fork, evidence RFC 8785, relayer EIP-712 và FastAPI tại port 8001.

**Bắt đầu tại [Runbook B & hướng dẫn bàn giao cho A](04_PERSON_B_RUNBOOK.md).** Interface chung: [Integration contract v1.1](03_SHARED_INTEGRATION_CONTRACT.md), [shared Python SDK và JSON Schema](../packages/contracts-api/README.md). Fuji đang chờ địa chỉ public của attestor do A quản lý; cách lấy và cấu hình nằm trong mục 5 của runbook.

```powershell
npm ci --ignore-scripts
npm run b:setup
npm run b:check
# Terminal 1:
npm run b:anvil
# Terminal 2:
npm run b:deploy:local
npm run b:demo
npm run b:api
```

Demo local thực hiện swap qua Vault và xuất [evidence](../evidence/execution-plane-local.json). API sử dụng `X-API-Key` trong `.env.b.local`; mutation cần `Idempotency-Key`. Các lệnh `b:*` là workflow mới. Code cũ bên dưới vẫn được giữ để tham khảo thử nghiệm Avalanche; không thuộc luồng v1.1.

## Legacy: Avalanche UniHack Integration PoC

PoC Solidity + Hardhat 3 + viem + React/Vite cho AI Agent Security. **Chỉ Fuji Testnet và local EVM; không mainnet.**

Đã bổ sung **smart account ERC-4337 v0.8**, EIP-712, relay cục bộ và batch approve+execute. Account Fuji: `0x12a399c202d4090e7cbcda3aa9e281ea5a47930f`. [Cách chạy và phạm vi](SMART_ACCOUNTS.md), [kết quả đo smart account](SMART_ACCOUNT_RESULTS.md). Bộ unit tests hiện có **41 tests**, gồm 14 tests Account Abstraction. Smart account dùng treasury/storage mới; hai contract EOA cũ bên dưới vẫn hoạt động riêng.

Kết quả nền tảng EOA: compile, TypeScript, local deploy và E2E A–E đã chạy thành công. **Hai contract đã deploy và E2E A–E đã PASS trên Fuji chain 43113**, có receipt thực, bytecode khớp artifact và lần đọc lại độc lập. Manifest: `deployments/fuji.json`. Storage: `0xd3361fb2c1547f1fec5f9d877d63e5a3346e4489`; guard: `0x487f648a58f93164b39ddce8db48ae57684c4c65`. Ví UI trong test là adapter cho node local; ký bằng extension thật vẫn chưa kiểm chứng. Xem [test results](TEST_RESULTS.md), [báo cáo khả thi](FEASIBILITY_REPORT.md), [nghiên cứu](RESEARCH.md), [kiến trúc](ARCHITECTURE.md).

## Cài và kiểm tra

Windows PowerShell; Node 24 LTS (máy chạy thực tế: 24.21.0), npm, Git. Không cần Docker/node Avalanche riêng.

```powershell
npm ci
npm run compile
npm test
npm run typecheck
npm run build
npm run check-network
```

Hardhat 3.21.2; Solidity 0.8.38; optimizer 200; `evmVersion: cancun`. ABI frontend được tạo từ artifact sau compile. `npm test` lưu kết quả thực vào `evidence/unit-results.json` và `unit-tests.txt`.

## Demo local

Terminal 1:

```powershell
npm run node
```

Terminal 2:

```powershell
npm run deploy:local
npm run demo:local
$env:VITE_NETWORK='local'
npm run dev
```

Mở http://127.0.0.1:5173. Kết quả deploy lưu ở `deployments/local.json`; receipt/bytecode verification và E2E ở `evidence/`. Mặc định UI chỉ đọc; ký cần injected Core/MetaMask. Với ví local, dùng tài khoản test của node local, không nhập secret vào frontend. Tài khoản mặc định Hardhat công khai, tuyệt đối không dùng trên mạng công cộng. Node launcher lọc phần in khóa mặc định. Nếu restart node, deploy lại. Demo E2E có thể chạy lặp lại: tạo ID mới, không cố định proposal ID.

## Chuẩn bị ví Fuji — thao tác cục bộ cần người dùng

Nếu chưa từng tạo ví, xem [hướng dẫn từng bước bằng tiếng Việt](WALLET_SETUP.md).

1. Tạo **hai ví test riêng** trong Core hoặc MetaMask: owner/deployer và agent. Không dùng ví tài sản thật; không dùng tài khoản Hardhat công khai.
2. Chọn/thêm Avalanche Fuji C-Chain: chain ID **43113**, RPC `https://api.avax-test.network/ext/bc/C/rpc`, token test AVAX, [explorer](https://explorer-test.avax.network/c-chain).
3. Dùng [faucet chính thức](https://build.avax.network/console/primary-network/faucet) để cấp test AVAX cho cả hai ví; làm các bước đăng nhập/kiểm tra điều kiện nếu được yêu cầu. Không mua AVAX thật. Có thể xem thêm [Team1 faucet](https://team1vn.xyz/faucet.html). Nếu faucet từ chối, ghi BLOCKED và liên hệ mentor; không chuyển mainnet.
4. `Copy-Item .env.example .env`, mở `.env` bằng editor cục bộ. Điền `DEPLOYER_PRIVATE_KEY`, `AGENT_PRIVATE_KEY`, public `AGENT_ADDRESS`, rồi đặt `FUJI_TEST_WALLETS_ONLY=true` sau khi kiểm tra cả hai là ví test. Có thể đặt secret bằng môi trường tiến trình thay cho file. **Không gửi khóa/seed qua chat, không chạy Get-Content .env, không ghi khóa vào terminal history/log.**
5. `.env` được ignore; chỉ `VITE_*` được Vite công khai. Không bao giờ đặt secret vào biến có tiền tố `VITE_`.

Script chỉ gửi tiền demo về owner có khóa được kiểm soát, amount 0.0001 test AVAX; agent cần vốn trả gas. Deploy ước lượng gas/fee và kiểm balance trước từng contract, chặn budget >0.02 test AVAX/contract. Số dư cần thiết phụ thuộc fee thực tế lúc chạy, không lấy giá local làm báo giá Fuji.

```powershell
npm run check-network
npm run deploy:fuji
npm run fund-agent:fuji
npm run demo:fuji
npm run verify:fuji
npm run report
```

`deploy:fuji` tự compile, test và typecheck trước khi ký. Script xác nhận chain, receipt success, runtime bytecode khớp artifact và đọc owner/trạng thái ban đầu. Sau đó ghi `deployments/fuji.json`, `frontend/public/deployment.fuji.json` và receipt thực. Nếu lỗi sau một contract đã deploy, kiểm các file `evidence/deploy-fuji-*-submitted.json` và receipt trước khi chạy lại để tránh triển khai dư. Chưa có cơ chế resume tự động từng contract.

`fund-agent:fuji` kiểm cả owner/agent khớp manifest rồi bổ sung tối đa đến 0.0005 test AVAX cho agent từ owner; chỉ chuyển giữa hai ví đã kiểm soát. Nếu agent đã đủ mức đó thì bỏ qua. Demo có kiểm agent balance trước khi bắt đầu.

Demo Fuji yêu cầu agent key tương ứng manifest; A cập nhật storage, B nạp/propose/approve/execute và kiểm số dư, C vượt limit, D recipient không cho phép, E agent thực thi trái quyền. C–E có simulate để kiểm đúng lý do và **gửi giao dịch cố ý revert để có receipt**, nên vẫn tốn một ít gas test. Mỗi bước lưu hash/chain/block/status/gas/log vào `evidence/e2e-fuji.json`. Receipt revert là PASS của một kịch bản bảo mật khi đúng điều kiện và count không đổi. `verify:fuji` đọc lại receipt/code/state/log độc lập, không gửi giao dịch; `report` tạo lại TEST_RESULTS.md từ bằng chứng.

## UI Fuji và agent CLI

Terminal mới (hoặc xóa biến môi trường local), sau deploy:

```powershell
Remove-Item Env:VITE_NETWORK -ErrorAction SilentlyContinue
npm run dev
```

Kết nối ví và kiểm đúng chain 43113; tick xác nhận ví test. Owner: sửa storage, quản lý allowlist/limit/agent, nạp 0.0001, approve/execute. Agent: chỉ propose. Đổi account trong ví rồi kết nối lại. Fuji UI chỉ nhận owner/agent từ manifest làm người nhận demo được kiểm soát. Nếu thay agent on-chain, redeploy manifest/điều chỉnh cấu hình demo tương ứng trước khi dùng CLI.

PublicClient đi qua route `/fuji-rpc` của Vite để tránh lỗi CORS thực tế từ RPC công khai; route chỉ chuyển tiếp đến endpoint Fuji thật, không ký hay giả lập dữ liệu. Log query chia lô 100 block, đọc tăng dần các block mới và gom batch request. HTTP 429 tuân thủ Retry-After trước khi gửi lại. Bản build có thể thử bằng `npm run preview` tại http://127.0.0.1:4173. Hosting khác cần cấu hình route `/fuji-rpc` tương ứng; upload static files đơn thuần chưa đủ.

Fuji còn giới hạn tổng range của các log query trong cùng batch: log được gửi riêng và điều tiết tốc độ. Chạy `npm run history:checkpoint` trước khi khởi động lại demo sau thời gian dài để tạo cache lịch sử từ RPC. UI đối chiếu block hash của checkpoint rồi đọc block mới; trạng thái hiện tại luôn lấy qua RPC.

Có thể để owner trên frontend và chạy agent ở terminal:

```powershell
npm run agent:fuji
```

Mặc định propose 0.0001 về owner; `PROPOSAL_AMOUNT`, `PROPOSAL_RECIPIENT` là biến môi trường tùy chọn. Dùng địa chỉ test thuộc quyền kiểm soát. Contract vẫn kiểm policy; CLI agent không có lệnh approve/execute.

## Kiểm thử trình duyệt

Để kiểm tra phần smart account, cần thêm `npm run aa:bundler:local` và `npm run aa:bundler:fuji` ở hai terminal, cùng manifests đã deploy. Test UI ký EIP-712, gửi qua relay thật và đối chiếu nonce/state/receipt bằng local RPC. Có thể chạy `npm run aa:fund:local` trước nếu lặp test nhiều lần làm giảm deposit.

Hai Vite server cần chạy: local ở 5173 theo hướng dẫn trên, Fuji ở 5174 từ terminal khác không có `VITE_NETWORK=local`:

```powershell
npm run dev -- --port 5174
```

Máy hiện có Google Chrome; Playwright dùng `channel: chrome`, không dùng profile cá nhân. Sau local deploy/demo:

```powershell
npm run test:ui
```

Test UI adapter chỉ tồn tại trong `e2e/`, không xuất vào bundle. Mọi RPC gửi vào node thật; không giả lập số dư/receipt. Test có thay đổi local storage và tạo proposal thật. Ảnh desktop/mobile/Fuji và JSON kết quả ở `evidence/`. Việc cài Chromium Playwright gặp lỗi tải mạng trên máy này; Chrome đã cài hoạt động.

## Tra cứu giao dịch

Fuji: explorer `/address/<contract>` để xem code/balance, `/tx/<hash>` để xem status, block, gas, logs. Copy giá trị thực từ `deployments/fuji.json` hoặc `evidence/e2e-fuji.json`. Local không có explorer. Runtime bytecode verification qua RPC đã có; **source verification trên explorer chưa thực hiện**.

## Phạm vi và giới hạn

Đây là agent giả lập quyết định, policy thực thi bằng contract thật. Chưa tích hợp LLM. Chưa audit production, chưa có daily budget/pause/expiry/cancel/recovery/multisig; owner vẫn là điểm tin cậy. Npm audit có advisory ở Zod 3 trong toolchain Hardhat; không ép nâng Zod 4 làm vỡ API. Xem báo cáo cho rủi ro và trạng thái kiểm chứng cụ thể. Không đặt khóa production vào dự án này.
