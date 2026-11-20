# Chạy demo web trên Avalanche Fuji

> **DOC STATUS: CURRENT_RUNBOOK** — Fuji là mặc định; mock/LOCAL là chế độ chọn riêng. Xem [system design](../AI_Treasury_Security_System_Design_v2.1.md) cho trust assumptions và phạm vi chứng minh.

## 1. Khởi động

Từ repository root, dùng `.env` private đã cấu hình:

```powershell
uv sync --locked
uv run --locked treasury doctor --live
uv run --locked treasury serve
```

`serve` mặc định Fuji, sử dụng vault/adapter/policy/session đã deploy, không tự deploy/renew/fund/swap. Mở `http://127.0.0.1:8000`. Chọn **PaceVant - Demo User**; không nhập token, không Connect Wallet. Server tự cấp credential hẹp trong memory của tab. Không cần private key Demo User để sử dụng flow hiện tại.

Không có config hợp lệ thì fail closed, không chuyển về mock. CLI mặc định chọn LFJ cho Fuji deployment; chỉ explicit owner deployment mới có thể tạo contract. Canonical Fuji serving từ chối manifest dùng mock adapter hoặc không bật PDR V2.

## 2. Các kịch bản trên giao diện

| Kịch bản | Làm gì thật? | Có gửi transaction/trừ gas? |
| --- | --- | --- |
| Swap nhỏ | AI/provider thật, full Shield/ITAG/oracle/risk/SMT/sign/preflight pipeline, vault/LFJ Fuji | Có nếu toàn bộ gates pass; phí thực từ receipt |
| Vượt hạn mức | Gửi actual request lớn hơn max swap một base unit; server guard phải trả TRADE_SIZE_LIMIT | Không, bị chặn trước request workflow/ledger |
| Policy/session/credit | Đọc contract policy/session và gas ledger; hiển thị block/hash/expiry/reasons | Không; scope này không chứng nhận oracle/funds/exposure sẵn sàng |
| Replay/calldata/chữ ký | Ba eth_call với một transaction Demo User đã CONFIRMED và fee settled; replay tại inclusion block, tamper/wrong-signer tại parent block | Không; không phải ba public revert transactions |
| Prompt injection | Fixed adversarial TOOL-role challenge gửi real configured Shield model trong session kiểm tra riêng; có trace/model/verdict | Không swap; có thể tốn provider AI quota/chi phí API |

Kết quả được đọc từ actual API/model/chain; không dựng timeline success giả cho các checks không gửi giao dịch. `INCONCLUSIVE` hoặc model không đánh dấu MISALIGNED không được đổi thành pass. Challenge prompt injection là input kiểm thử cố định, không được gọi là market observation thật hoặc toàn bộ attack benchmark.

Swap mẫu là **0.000001 USDC**, tương đương 1 base unit Circle USDC. Giữ amount nhỏ, đọc số dư/exposure trước khi thử tiếp. Các case chỉ đọc có thể chạy mà không cố gửi transaction vi phạm để trả gas.

## 3. Tiền hệ thống và gas credit

Token swap nằm trong vault. Relayer trả AVAX on-chain. Gas credit là sponsor allowance DB, khác AVAX trong ví Demo User và chưa phải customer deposit.

```text
maximum_hold = gasLimit * gasPrice
actual_fee   = gasUsed * effectiveGasPrice
available    = allocation - settled_fees - active_holds
```

Current allocation 0.001 AVAX, cap mỗi transaction 0.0001 AVAX. Demo limit dùng estimateGas với margin 10% + 5000 gas; phí chỉ theo actual gasUsed. Reserve và raw journal commit cùng DB transaction trước broadcast. Thiếu credit/fee cap/relayer AVAX thì không gửi. Success và revert đều trả actual gas; pending/unknown giữ hold. Reorg reverse bằng append event và giữ maximum hold, không refund mù theo timeout.

Đổi initial-credit env, restart hoặc chọn account lại không refill allocation. Không có payment/top-up/refund product. Không dùng số AVAX trong ví Demo User làm gas credit.

## 4. Thiếu vốn vault hoặc hết session

Session browser, task intent, approval TTL và on-chain session là các đối tượng khác nhau. Browser hết hạn chỉ cần chọn account lại. On-chain session hết hạn cần owner renewal có transaction; env change không tự renew. Giữ policy limits và TTL 300s, không sửa signed deadline hoặc stamp fresh vào giá cũ.

WAVAX exposure guard hiện tại là 25% trước ký. Một swap làm vault tăng WAVAX; đủ gas credit chưa đồng nghĩa đủ USDC/exposure room. Nạp đúng **Circle Fuji USDC `0x5425890298aed601595a70AB815c96711a31Bc65`** vào vault khi cần; LFJ faucet token khác địa chỉ không được thay thế chỉ vì cùng symbol.

Operator có lệnh bổ sung vốn nhỏ, **có gửi giao dịch owner**:

```powershell
uv run --locked treasury fund-demo
```

Lệnh này tính thiếu bao nhiêu Circle USDC để một swap 1 base unit tiếp theo còn trong exposure 25%, dùng token owner nếu có; nếu cần mua thì cap native purchase **0.004 AVAX, gas thêm riêng**, sau đó chuyển ít USDC vào vault. Không nới policy, không deploy, không auto chạy khi serve. Journals là một lần/resumable và không tự xoay để mua lặp khi gọi lại; nếu vốn đã tiêu hoặc giá đổi thì báo cần Circle faucet/funding operator thay vì tự mua liên tiếp. Đây là testnet pool purchase, không phải phí gas hoặc chứng minh giá trị USD kinh tế.

Ưu tiên Circle faucet để có đủ vốn cho nhiều lượt. Lệnh fund-demo không cam kết hỗ trợ vô hạn swaps; mỗi lượt vẫn qua full gates. Giữ journals, kiểm hash/receipt trước khi xử lý timeout.

## 5. Timeout và resume

Trong lúc POST chạy, UI poll request ID để hiển thị timeline thật. Chỉ POST goal một lần; không tự tạo giao dịch mới khi request chưa rõ. Sau reload chọn lại account rồi dùng **Kiểm tra yêu cầu đã gửi**. GET resume không ký/broadcast. Đừng xóa DB/sessionStorage để ép một pending request thành request mới.

Core pipeline có thể tốn vài phút do fork/RPC. Các idempotent GET qua local execution adapter retry tối đa một lần với Web3 RPC/transport failure; không retry mutation ở lớp này. Mọi hash/freshness/policy checks sau đọc vẫn chạy. RPC/round unavailable có thể làm workflow ESCALATED đúng; lúc đó xem reason codes, không gọi đó là transaction revert nếu chưa broadcast.

## 6. Mock và LOCAL tách riêng

```powershell
# Fixture UI, không model/RPC/signing/gas credit thật
uv run --locked treasury mock

# EVM/contract/proof tests trên Anvil với demo assets/prices, không public Fuji
uv run --locked treasury local
```

Hai lệnh mặc định cùng port 8000 với live backend; dừng service đang dùng trước khi chuyển mode. MOCK được gắn nhãn rõ và không thể tự thành Fuji khi lỗi. LOCAL chọn rules/controlled oracle, disabled semantic Shield và không bật demo billing; đây không phải evidence cho real provider hoặc public execution. Không dùng kết quả hai mode này để tuyên bố dữ liệu thị trường thật.

## 7. Smart account và giới hạn

Account thực thi hiện tại là **PolicyVault smart-contract treasury** có owner/policy/session/nonce/caps/Phi enforcement. Không triển khai ERC-4337 bundler/Paymaster hoặc SmartAccount PoC cũ trong pipeline này. Demo wallet là identity; backend attestor/relayer thực hiện flow được giới hạn, không “connect ví rồi trao key cho model”.

Backend một instance/worker, hai SQLite stores bền vững; không xóa data dirs để gỡ pending. Chưa multi-user/payment/HA/mainnet/independent audit. USD từ Chainlink là policy reference cho test assets; stress là hypothetical scenario trên concrete EVM fork. Hosted image/proxy/persistence vẫn cần smoke test riêng nếu chuyển từ máy operator sang hosting.
