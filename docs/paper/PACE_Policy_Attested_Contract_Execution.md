# PACE: Policy-Attested Contract Execution for Safe AI Agents in Decentralized Finance

## 1. Tổng quan Bài báo & Tóm tắt Kỹ thuật

Bài báo khoa học **"PACE: Policy-Attested Contract Execution for Safe AI Agents in Decentralized Finance"** được nghiên cứu bởi nhóm tác giả **Rabimba Karanjai, Yang Lu, Richard Williamson, Hemanth Hm, Prakhar Mehrotra, Lei Xu, và Weidong (Larry) Shi** (thuộc Đại học Houston, PayPal và Đại học Kent State).

### Vấn đề cốt lõi
Các Agent AI tự hành dựa trên mô hình ngôn ngữ lớn (LLMs) đang dần trở thành giao diện tương tác chính trong tài chính phi tập trung (DeFi) cho các tác vụ như swap token, cho vay (lending), và quản lý lợi suất (yield farming). Tuy nhiên, do phụ thuộc vào LLM để lập kế hoạch giao dịch, các agent này thừa hưởng các lỗ hổng an ninh kinh điển của LLM: dễ bị **Prompt Injection** (trực tiếp và gián tiếp) và **thiếu cơ chế mã hóa mật mã** để buộc phê duyệt của bộ kiểm duyệt phải khớp chính xác với byte giao dịch được thực thi trên blockchain. Khác với câu văn lỗi của chatbot, một giao dịch sai sót của AI agent sẽ lập tức settle on-chain — rút sạch ví hoặc cấp quyền approval vô hạn — trước khi con người kịp can thiệp.

### Giải pháp PACE
Tác giả đề xuất **PACE (Policy-Attested Contract Execution)**, một khung xác thực cấp giao dịch chèn giữa AI Agent và quá trình thực thi on-chain:
- **Typed Transaction Intents**: Định kiểu rõ ràng ý định giao dịch (target, value, calldata, approval, slippage).
- **Deterministic Policy Verifier**: Bộ kiểm duyệt chính sách định tính, đánh giá ý định và mô phỏng tiền thực thi (pre-execution simulation) dựa trên chính sách do người dùng định nghĩa mà không bao giờ truy vấn LLM.
- **Signed Policy Decision Record (PDR)**: Hồ sơ quyết định chính sách được ký số, ràng buộc mật mã giữa intent đã duyệt, policy, báo cáo mô phỏng với byte calldata thực thi thực tế, đi kèm cơ chế chống phát lại (replay) và chống hết hạn.
- **Solidity Smart Account**: Hợp đồng thông minh trên Ethereum tái kiểm tra chữ ký PDR và 9 quy tắc binding on-chain trước khi thực hiện bất kỳ lời gọi ngoại vi nào.

### Kết quả chính
- **Môi trường Sandbox định tính (2,800 trials, 10 seeds)**: PACE đạt **tỷ lệ thực thi không an toàn (unsafe execution rate) 0.00** và **tỷ lệ báo động giả (false-positive rate) 0.00** trên các tác vụ hợp lệ, so với tỷ lệ vi phạm 0.80 của agent không có bảo vệ (Raw baseline).
- **Phân tích thành phần (Ablation Study)**: Xác định cấu hình chính sách cho phép (permissive policy) làm tăng vi phạm +57.5 pp và danh sách hợp đồng cho phép (touched-contract allowlist) làm tăng vi phạm +12.5 pp nếu bị loại bỏ.
- **Overhead On-Chain**: Chi phí gas kiểm tra PDR on-chain đo được qua Foundry đạt **29,826 – 31,822 gas** mỗi giao dịch.
- **Live-LLM Benchmark**: Thử nghiệm trên 3 mô hình thực tế (Gemini 3.1 Flash Lite, DeepSeek V4 Flash, GPT-4o) khẳng định sàn an toàn (verifier safety floor) ngăn chặn 100% tấn công mà LLM đánh giá sai là an toàn.

---

## 2. Bối cảnh & Động lực Nghiên cứu

### 2.1. Cấu trúc Tài chính Phi tập trung (DeFi Primitives)
- **Automated Market Makers (AMMs)**: Các bể thanh khoản Constant-Product (như Uniswap V2) thực thi giao dịch swap qua hằng số $x \cdot y = k$. Tác động giá (price impact) tăng siêu tuyến tính so với quy mô giao dịch. Giao dịch lượng $\Delta x$ vào bể $(R_x, R_y)$ thu về lượng $\Delta y = \frac{R_y \cdot \Delta x \cdot (1 - f)}{R_x + \Delta x \cdot (1 - f)}$ với $f$ là phí giao dịch (vd: 30 bps).
- **Lending Protocols**: Đơn vị như Aave quản lý các khoản vay thế chấp. Hệ số sức khỏe vị thế $h = \frac{C \cdot p \cdot t}{D}$ quyết định rủi ro thanh lý, trong đó $C$ là tài sản thế chấp, $p$ là giá oracle, $t$ là ngưỡng thanh lý, và $D$ là dư nợ.
- **Token Approvals**: Hàm `approve(spender, amount)` của ERC-20 cho phép bên trung gian chuyển token. Quyền duyệt vô hạn (`amount = 2^256 - 1`) là nguyên nhân hàng đầu dẫn đến các vụ rút cạn ví (approval drain) trong lịch sử DeFi.

### 2.2. Tách biệt Tài khoản (Account Abstraction - ERC-4337)
ERC-4337 giới thiệu ví hợp đồng thông minh với logic xác thực lập trình được qua hàm `validateUserOp`. Hệ sinh thái Safe Modules chứng minh khả năng áp dụng hạn mức chi tiêu, allowlist, và logic tùy chỉnh on-chain.

### 2.3. Rủi ro của AI Agent trong DeFi
Khi nhận mệnh lệnh tự nhiên như *"hãy tối ưu lợi suất cho tiền ổn định của tôi"*, AI Agent phải tự dịch thành các chuỗi calldata (swap, approve, deposit). Tuy nhiên, LLM không thể tách biệt hướng dẫn tin cậy và dữ liệu không tin cậy. Kẻ tấn công có thể chèn **Prompt Injection** thông qua tên token, price feed, ghi chú giao dịch hoặc đầu ra của công cụ.

Khác với văn bản sai của chatbot, giao dịch sai của AI Agent được settle tức thì trên blockchain. Việc cấp trực tiếp khóa private key và vốn cho LLM mở ra các hướng tấn công hoàn toàn mới, đòi hỏi cơ chế bảo vệ nằm **bên ngoài mô hình** và **ràng buộc tại thời điểm thực thi**.

### 2.4. Maximal Extractable Value (MEV)
Trong các cuộc tấn công Sandwich, kẻ săn MEV đọc giao dịch pending của victim trong mempool, thực hiện front-run (đẩy giá lên), để victim mua giá đắt, rồi back-run để chốt lời. Mức thiệt hại của victim bị giới hạn bởi tham số trượt giá (slippage tolerance).

---

## 3. Mô hình Đe dọa & Ranh giới Tin cậy

### 3.1. Mô hình Hệ thống (System Model)
Người dùng giao quyền thực thi cho AI Agent. Agent nhận mục tiêu tự nhiên, lập kế hoạch và phát hành chuỗi giao dịch. PACE đóng vai trò là một lớp trung gian interposition kiểm duyệt trước khi broadcast lên mạng lưới.

### 3.2. Mô hình Kẻ tấn công (Adversary Model)
Kẻ tấn công có thể:
1. Chèn ngữ cảnh độc hại qua metadata, lịch sử chat, nguồn dữ liệu ngoài.
2. Điều hướng agent gọi đến hợp đồng độc hại.
3. Front-run giao dịch đang chờ (pending).
4. Sửa đổi calldata trong khoảng thời gian giữa lúc mô phỏng (simulation) và lúc gửi (submission).
5. Phát lại (replay) kết quả mô phỏng đã cũ.

**Phạm vi không bao gồm**: Kẻ tấn công không thể sửa đổi chính sách người dùng (User Policy), Verifier, hoặc logic Smart Account. Kẻ tấn công không có quyền truy cập khóa private key của Owner hoặc luồng thực thi thô (raw execution path) dành riêng cho Owner.

### 3.3. Ranh giới Tin cậy (Trust Boundaries)
- **Thành phần Tin cậy (Trusted)**: User Policy (do người dùng/admin cài đặt), Policy Verifier (định tính), và Simulator (định tính, có thể kiểm toán).
- **Thành phần Không tin cậy (Untrusted)**: LLM/Agent, Transaction Intent phát hành, và toàn bộ hợp đồng thông minh bên ngoài.
- **Nguyên lý bảo vệ cốt lõi**: Verifier **không bao giờ truy vấn LLM**. Mọi kiểm tra là các phép so sánh định tính đối với chính sách do người dùng khai báo. PACE hướng tới **Tính đúng đắn (Soundness)**: Mọi giao dịch được thực thi đều bảo đảm thỏa mãn chính sách, bất kể hành vi của LLM bị thao túng đến đâu.

### 3.4. Các Nhóm Tấn công trong Benchmark
Benchmark gồm 40 tác vụ chia làm 5 nhóm (mỗi nhóm 8 tác vụ):
1. **Prompt Injection**: Thao túng câu lệnh gián tiếp và trực tiếp.
2. **Unsafe Contracts**: Gọi hợp đồng chưa được xác minh hoặc độc hại.
3. **DeFi Exploits**: Các mẫu khai thác phê duyệt vô hạn, vay nhanh (flash loan), thao túng giá.
4. **MEV / Slippage**: Trượt giá cực đoan, tấn công sandwich.
5. **Benign Utility**: Các tác vụ hợp lệ (Negative Control).

---

## 4. Kiến trúc Hệ thống PACE

Khung kiến trúc PACE gồm 3 lớp bảo vệ chính nối tiếp nhau:

```
User Goal -> [LLM Agent -> Typed Intent] (Untrusted)
          -> [Simulator -> Policy Verifier -> Signed PDR] (Trusted, Deterministic)
          -> [PACE Smart Account] (On-chain)
          -> Execute / Reject
```

### 4.1. Typed Transaction Intents
Cấu trúc dữ liệu đại diện cho hành động on-chain của Agent gồm:
- `chainId`: ID của mạng lưới blockchain.
- `sender`, `target`: Địa chỉ gửi và nhận.
- `value`: Số lượng ETH/native token.
- `selector`, `calldata`: Hàm và dữ liệu mã hóa.
- `approvals`: Danh sách các cấp quyền token (`TokenApproval`: token, spender, amount, unlimited flag).
- `slippage`: Mức trượt giá cho phép.
- `metadata`: Từ điển dữ liệu bổ trợ.

Mỗi intent có định dạng Canonical JSON chuẩn hóa (sắp xếp key, phân cách nén) và chuỗi băm SHA-256 (`hash_intent`). Trường `calldata` có mã băm riêng (`calldata_hash`).

### 4.2. User Policy (Chính sách Khai báo)
Bao gồm các tập quy tắc:
- Allowlists: Địa chỉ hợp đồng target, selector hàm, địa chỉ token.
- Value limits: Hạn mức ETH tối đa mỗi giao dịch, hạn mức chi tiêu từng token.
- Approval controls: Chặn cấm tuyệt đối cấp quyền vô hạn `2^256 - 1`.
- Slippage bound: Mức trượt giá tối đa cho phép.
- Function blocklist: Danh sách hàm bị cấm (như `flashLoan`, `delegateCall`).
- Simulation requirements: Yêu cầu bắt buộc mô phỏng và thời gian hiệu lực tối đa của báo cáo (freshness).
- Post-state thresholds: Hệ số sức khỏe tối thiểu ($h$), mức thua lỗ tối đa (maximum loss).
- Metadata regexes: Biểu thức chính quy lọc nội dung metadata.

### 4.3. Deterministic Policy Verifier
Verifier là một hàm thuần túy (pure function), không kết nối mạng và không hỏi LLM. Verifier duyệt giao dịch nếu không có vi phạm nào. Khi yêu cầu mô phỏng, Verifier xác nhận báo cáo thành công, độ tươi (freshness), các hợp đồng bị chạm (touched contracts), và đặc biệt là **sự trùng khớp giữa `intent_hash` trong báo cáo mô phỏng và `intent_hash` được gửi lên**, ngăn chặn việc sửa đổi calldata sau khi mô phỏng.

### 4.4. Policy Decision Record (PDR) & On-Chain Enforcement
PDR là một bằng chứng chứng thực bất biến (immutable attestation) liên kết: intent đầy đủ, policy áp dụng, simulation report, quyết định (Approve/Reject), chuỗi vi phạm, mã băm SHA-256 của intent/policy/calldata, và nhãn thời gian.

- **Chỉ ký khi Approve**: Verifier chỉ ký PDR nếu quyết định là `Approve`. Quyết định `Reject` được lưu off-chain để kiểm toán nhưng không bao giờ được ký.
- **On-chain Re-check**: Smart Account `PaceSmartAccount` khôi phục chữ ký ECDSA trên digest `keccak256` của PDR (tiền tố Ethereum Signed Message) và kiểm tra lại 9 điều kiện:
  1. `signer == verifier`
  2. `chainId` khớp với mạng hiện tại
  3. `account` khớp với địa chỉ ví
  4. `target` khớp với hợp đồng nhận
  5. `value` khớp với số ETH gửi
  6. `keccak256(data)` khớp với calldata gửi kèm
  7. `nonce` chưa được sử dụng
  8. `validAfter` $\le$ thời gian hiện tại
  9. `validUntil` $\ge$ thời gian hiện tại

Nếu tất cả 9 điều kiện vượt qua, nonce được đánh dấu đã dùng theo mẫu CEI (Checks-Effects-Interactions) trước khi thực hiện lời gọi ngoại vi.

---

## 5. Triển khai Kỹ thuật & Mô phỏng

### 5.1. Reference Implementation & DeFi Simulator
Hệ thống được viết bằng Python 3.11+ sử dụng Pydantic v2. Bộ mô phỏng DeFi trong bộ nhớ (in-memory simulator) thực thi các nguyên mẫu:
- Token ERC-20 (số dư, cấp quyền, chuyển khoản).
- Constant-Product AMM ($x \cdot y = k$, phí 30 bps, bể 10,000 WETH / 10,000,000 DAI).
- Lending Pool với hệ số sức khỏe oracle (giá 1,000 DAI/ETH, LTV 0.75, ngưỡng thanh lý 0.80).
- Malicious Router (chạm hợp đồng ẩn khi delegatecall) và Approval Drainer.

### 5.2. Các Agent Baseline So sánh
1. **Raw**: Thực thi mọi intent do LLM tạo ra.
2. **Prompt-Only**: Sử dụng regex/LLM để lọc từ khóa trong prompt.
3. **Sim-Only**: Từ chối nếu mô phỏng trả về revert.
4. **WalletGuard**: Kiểm tra target allowlist + hạn mức ETH value.
5. **StaticGuard**: Kiểm tra đầy đủ quy tắc chính sách, không mô phỏng.
6. **SimGuard**: Kiểm tra đầy đủ chính sách + mô phỏng, nhưng **không có PDR calldata binding**.
7. **PACE**: Đầy đủ Mô phỏng + Policy + PDR Binding on-chain.

---

## 6. Đánh giá Thực nghiệm & Kết quả Chi tiết

### 6.1. Hiệu năng Tổng thể trên Benchmark (2,800 Trials)

Dưới đây là bảng so sánh hiệu năng của 7 baseline trên 2,800 lượt thử nghiệm (10 seeds, 40 tác vụ/seed):

| Agent | Correct Rate (%) | Unsafe Exec Rate | Attack Success Rate | Dangerous Block Rate | False Positive Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Raw** | 20.0% | 0.80 | 1.00 | 0.00 | 0.00 |
| **Prompt-Only** | 41.2% | 0.59 | 0.73 | 0.27 | 0.00 |
| **Sim-Only** | 27.5% | 0.72 | 0.91 | 0.09 | 0.00 |
| **WalletGuard** | 75.0% | 0.25 | 0.31 | 0.69 | 0.00 |
| **StaticGuard** | 95.0% | 0.05 | 0.06 | 0.94 | 0.00 |
| **SimGuard** | 97.5% | 0.03 | 0.03 | 0.97 | 0.00 |
| **PACE** | **100.0%** | **0.00** | **0.00** | **1.00** | **0.00** |

**Nhận xét**:
- **PACE** đạt tỷ lệ chính xác tuyệt đối 100%, tỷ lệ vi phạm 0.00 và không bị báo động giả trên các tác vụ hợp lệ.
- Baseline mạnh nhất ngoài PACE là **SimGuard** (có mô phỏng và chính sách nhưng thiếu PDR calldata binding) vẫn bỏ sót tác vụ sửa đổi calldata sau mô phỏng (Calldata Mutation attack `da_08`), dẫn đến tỷ lệ tấn công thành công 0.03.

### 6.2. Phân tích Thành phần (Ablation Study)

Thử nghiệm Ablation trên 320 lượt thử (seed 42) đánh giá vai trò của từng thành phần trong PACE:

| Biến thể Ablation | Correct Rate (%) | Unsafe Exec Rate | Reject Rate | False Positive Rate |
| :--- | :---: | :---: | :---: | :---: |
| `pace_baseline` | 100.0% | 0.000 | 0.800 | 0.000 |
| `pace_no_sim` | 95.0% | 0.050 | 0.750 | 0.000 |
| `pace_no_metadata` | 100.0% | 0.000 | 0.800 | 0.000 |
| `pace_no_touched` | 87.5% | 0.125 | 0.675 | 0.000 |
| `pace_no_calldata_bind` | 97.5% | 0.025 | 0.775 | 0.000 |
| `pace_no_freshness` | 97.5% | 0.025 | 0.775 | 0.000 |
| `pace_permissive` | 42.5% | 0.575 | 0.225 | 0.000 |
| `pace_conservative` | 95.0% | 0.000 | 0.850 | 0.250 |

**Kết luận quan trọng từ Ablation**:
1. **Cấu hình Policy (`pace_permissive`)**: Việc chuyển sang chính sách nới lỏng khiến tỷ lệ vi phạm tăng vọt lên **+57.5 pp** (từ 0.00 lên 0.575). Điều này khẳng định an toàn của hệ thống phụ thuộc lớn nhất vào bản thân thông số chính sách do người dùng thiết lập.
2. **Touched-contract allowlist (`pace_no_touched`)**: Loại bỏ danh sách kiểm tra các hợp đồng bị tương tác trong mô phỏng khiến tỷ lệ vi phạm tăng **+12.5 pp**.
3. **Calldata binding & Freshness**: Loại bỏ kiểm tra ràng buộc mã băm calldata hoặc kiểm tra độ tươi làm gia tăng **+2.5 pp** vi phạm cho mỗi thành phần.

### 6.3. Chi phí Gas & Độ trễ (Gas Overhead & Latency)
Đo lường trên Foundry (Solidity 0.8.24, optimizer 200 runs):
- Chi phí gas bổ sung cho quá trình kiểm tra xác thực PDR on-chain: **29,826 – 31,822 gas** mỗi giao dịch.
- Chi phí này chiếm phần lớn bởi thao tác khôi phục chữ ký `ecrecover` (~3,000 gas) và lưu trữ trạng thái nonce `SSTORE` (~20,000 gas).
- Tỷ lệ chi phí tương đối: Chiếm 91.7% gas của một lệnh ERC-20 approval thô, 78.9% gas lệnh transfer, và 50.5% gas của một lệnh swap AMM.
- Độ trễ quyết định off-chain của Verifier cực nhanh: chỉ **~0.04 ms**.

### 6.4. Đánh giá Live Multi-Model LLM
Thử nghiệm 595 trials trên 3 mô hình ngôn ngữ thực tế qua API tương thích OpenAI:

| Model | Correct Rate (%) | LLM-Only Atk Success | PACE Atk Success | False Positive Rate |
| :--- | :---: | :---: | :---: | :---: |
| `gemini-3.1-flash-lite` | 97.5% | 0.000 | **0.000** | 0.125 |
| `DeepSeek-V4-Flash` | 97.4% | 0.026 | **0.000** | 0.128 |
| `gpt-4o` | 99.0% | 0.069 | **0.000** | 0.050 |

**Kết quả**: Ngay cả khi các mô hình thương mại như `gpt-4o` bị lừa đánh giá 6.9% cuộc tấn công là an toàn, Verifier của PACE đã **chặn 100% các cuộc tấn công này**, đưa tỷ lệ tấn công thành công của PACE về đúng **0.000**.

### 6.5. Đánh giá Tấn công Thích ứng (Adaptive Adversary)

| Agent | Evasion Blocked (8 tasks) | Policy-Valid Harm Admitted (8 tasks) |
| :--- | :---: | :---: |
| **PACE** | **8/8 (1.00)** | **8/8 (1.00)** |
| **SimGuard** | 7/8 (0.88) | 8/8 (1.00) |
| **StaticGuard** | 7/8 (0.88) | 8/8 (1.00) |
| **WalletGuard** | 2/8 (0.25) | 8/8 (1.00) |

- **Né tránh (Evasion attacks)**: PACE ngăn chặn 8/8 thủ thuật cố tình vượt rào (sửa calldata, trượt giá sát biên, địa chỉ typo-squatted).
- **Tổn hại hợp lệ (Policy-valid harm)**: Các giao dịch gây thiệt hại kinh tế nhưng nằm hoàn toàn *trong ranh giới* chính sách (ví dụ: chia nhỏ giao dịch dưới hạn mức, trượt giá đúng bằng mức max) được PACE và mọi baseline cho phép 8/8. Điều này làm rõ ranh giới: PACE đảm bảo **Tính đúng đắn theo chính sách (Soundness)** chứ không đảm bảo **Tính toàn vẹn kinh tế tuyệt đối (Completeness)** nếu chính sách quy định chưa đủ chặt chẽ.

---

## 7. Thảo luận, Giới hạn & Hướng phát triển

### 7.1. Bài học Cốt lõi
An toàn của các hành động on-chain do AI Agent thực hiện có thể được **tách rời khỏi độ tin cậy của bản thân mô hình LLM**. Bằng cách coi toàn bộ đầu ra của LLM là không tin cậy và áp dụng cơ chế xác thực quyết định chính sách được ký số cả off-chain lẫn on-chain, PACE tạo ra một **sàn an toàn (safety floor)** không bị suy giảm khi hành vi của mô hình biến động.

### 7.2. Hướng phát triển Trong Tương lai (Future Work)
1. **Đối thủ thích ứng nâng cao**: Nghiên cứu các đối thủ học hỏi qua nhiều vòng đấu với verifier và các vòng lặp multi-step agent.
2. **Nâng cao hạ tầng mô phỏng**: Chạy mô phỏng trace-based trên môi trường Mainnet Fork thực tế để phát hiện reentrancy phức tạp.
3. **Chuẩn hóa ERC-4337 & EIP-712**: Nâng cấp định dạng băm PDR sang dữ liệu có cấu trúc EIP-712 và tích hợp vào quy trình `validateUserOp` dưới dạng module tiêu chuẩn của tài khoản ERC-4337 / ERC-7579.
