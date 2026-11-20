# Proof-Gated Signing: Solver-Checked Transaction Guards that Hold Under State Drift for Onchain AI Agents

## 1. Tổng quan Bài báo & Phát hiện Cốt lõi về State Drift

Bài báo khoa học **"Proof-Gated Signing: Solver-Checked Transaction Guards that Hold Under State Drift for Onchain AI Agents"** được tác giả độc lập **Bravish Ghosh** công bố (Preprint, tháng 9/2026).

### Khái niệm "State Drift" (Biến động Trạng thái)
Khi các AI Agent nắm giữ ví tiền mã hóa đọc nội dung từ bên ngoài (email, tài liệu, output của tool), chúng dễ bị lừa đề xuất các giao dịch độc hại. Chốt chặn bảo vệ cuối cùng hiện nay thường là kiểm tra trước khi ký (pre-signing check) dưới 3 dạng:
1. **Static Allowlist**: Danh sách hợp đồng/hàm cố định.
2. **LLM Reviewer**: Mô hình LLM thứ hai đánh giá lại giao dịch.
3. **Transaction Simulation**: Mô phỏng giao dịch để xem trước số dư thay đổi ("bạn sẽ gửi X và nhận Y").

Tác giả chỉ ra một **khe hở chí mạng** mà cả 3 giải pháp trên đều mắc phải: Một kiểm tra pre-signing chỉ là bằng chứng về trạng thái của blockchain **tại thời điểm kiểm tra (check time)**. Nhưng giao dịch lại được thực thi ở một trạng thái muộn hơn trên chain mà kẻ tấn công có thể dễ dàng thao túng thông qua:
- **Front-running / MEV Sandwich**: Chen lệnh làm thay đổi giá bể AMM.
- **Contract Upgrade**: Admin hợp đồng proxy thay đổi mã thực thi ngay trước khi giao dịch được đưa vào block.
- **Fee Parameter Change**: Chủ sở hữu token thay đổi phí giao dịch (fee-on-transfer) đột ngột.

Sự khác biệt giữa trạng thái lúc kiểm tra và trạng thái lúc thực thi được gọi là **State Drift (Biến động trạng thái)**. Dưới tác động của State Drift, kiểm tra pre-signing dù hoàn toàn chính xác tại thời điểm kiểm tra vẫn khiến giao dịch được thực thi bị tổn hại nghiêm trọng.

### Giải pháp Proof-Gated Signing (PGS)
PGS giải quyết triệt để vấn đề State Drift bằng cách **biên dịch các giả định của chứng minh mật mã thành các điều kiện hậu thực thi (post-conditions) bắt buộc on-chain**:
1. Guard mô phỏng giao dịch đề xuất và trích xuất vector hiệu ứng (effects vector).
2. Sử dụng bộ giải SMT Solver (Z3) để chứng minh chính sách giá trị và quyền hạn đối với mọi mức giá nằm trong dải biến động oracle (oracle uncertainty band).
3. Trích xuất các ngưỡng ràng buộc on-chain (post-conditions $\Phi$): số dư tối thiểu của ví, biên nhận chuyển tiền cho người thụ hưởng (payee receipts), hạn mức cấp quyền (allowance caps), và quyền sở hữu hợp đồng (ownership).
4. Ví hợp đồng thông minh (`AgentWallet`) thực thi giao dịch cùng tập hậu điều kiện $\Phi$ này trong **một giao dịch nguyên tử (atomic call)**. Nếu trạng thái chuỗi bị drift làm vi phạm bất kỳ hậu điều kiện nào, toàn bộ giao dịch sẽ lập tức bị **Revert on-chain**.

### Kết quả Thực nghiệm Chính
- trên bộ testbed gồm **260 kịch bản thử nghiệm** (14 họ tấn công = 140 kịch bản; 12 họ hợp lệ = 120 kịch bản):
  - **Tỷ lệ ngăn chặn tấn công (Attack Prevention Rate - APR)**: PGS ngăn chặn **93.6%** (131/140 kịch bản tấn công, 95% CI 88–97%).
  - **Tỷ lệ thông qua tác vụ hợp lệ (Benign Pass Rate - BPR)**: PGS cho phép **97.5%** (117/120 kịch bản hợp lệ).
  - **Tấn công State Drift**: Trong tất cả **50/50 kịch bản drift**, kẻ tấn công thu về lợi nhuận là **$0** (40 kịch bản bị revert on-chain, 10 kịch bản executed nhưng không thể khai thác).
  - So sánh: Kiểm tra mô phỏng đơn thuần (Simulation-only) chỉ ngăn được 57.9% tấn công, danh sách tĩnh (Static Allowlist) ngăn được 71.4%.
  - Overhead gas trung vị: **41.1k gas** (+46%) và độ trễ khoảng **0.1–0.2 giây** cho mỗi đợt kiểm tra.

---

## 2. Mô hình Đe dọa, Chính sách An toàn & Định lý Soundness

### 2.1. Mô hình Hệ thống & Đối thủ (Adversary Model)
- **Hệ thống**: Agent đề xuất chuỗi lời gọi $b = (c_1, \dots, c_k)$ tới ví `W`. Guard giữ private key ký giao dịch và kiểm tra policy trước khi ký lệnh `W.executeChecked(b, \Phi)`.
- **Đối thủ**: Có thể (i) chèn nội dung thao túng agent đề xuất bất kỳ lệnh nào; (ii) hành động on-chain trong khoảng thời gian giữa lúc Guard kiểm tra và lúc giao dịch được đóng block (front-run, back-run, upgrade hợp đồng, đổi phí token). Đối thủ có thể đọc mempool để biết trước các hậu điều kiện $\Phi$.
- **Thành phần Tin cậy**: Mã nguồn Guard và khóa ký, logic thực thi `executeChecked` của ví, các hợp đồng token được theo dõi báo cáo đúng số dư, oracle cung cấp giá thực nằm trong dải $[\underline{p_a}, \overline{p_a}]$, và chính sách do người dùng định nghĩa.

### 2.2. Chính sách Giá trị & Chính sách Cấu trúc

#### Định nghĩa 1 (Value Policy - Chính sách Giá trị)
Thiệt hại chưa giải thích ($L$) và giá trị dòng tiền ra ($V$) đối với tập tài sản $A$ được tính theo công thức:
$$L(\Delta, p) = - \sum_{a \in A} \Delta_a p_a - \sum_{a \in A} \pi_a p_a$$
$$V(\Delta, p) = \sum_{a \in A} \max(-\Delta_a, 0) - \sum_{a \in A} \pi_a p_a$$
Trong đó $\Delta_a$ là thay đổi số dư tài sản $a$, và $\pi_a$ là giá trị được ghi nhận thanh toán cho người thụ hưởng hợp lệ (allowlisted payees).

Giao dịch đạt chính sách giá trị nếu:
1. $L \le s \cdot V + f$ (ngưỡng tổn hại tương đối $s$ kèm sàn $f$, ví dụ $s = 3\%, f = \$25$).
2. $W_{\text{spent}} + L \le W_{\text{max}}$ (ngân sách tổng cho toàn bộ phiên làm việc $W_{\text{max}}$, ví dụ $\$5,000$).

#### Định nghĩa 2 (Structural Policy - Chính sách Cấu trúc)
- **S1**: Giá trị chuyển đến tài khoản cá nhân (EOA) chỉ được gửi đến danh sách địa chỉ thụ hưởng cho phép (allowlisted payees) trong hạn mức.
- **S2**: Không spender không tin cậy nào giữ quyền approval dương sau giao dịch.
- **S3**: Các hợp đồng do ví sở hữu phải giữ nguyên quyền sở hữu.
- **S4**: Không có dòng luân chuyển của các token chưa được định giá (untracked tokens) vào/ra ví.

### 2.3. Ranh giới Bảo đảm (Guarantee Boundary)

Bảng dưới đây tổng kết ranh giới bảo đảm của Định lý Soundness trong PGS:

| Phạm vi Bảo đảm (Guaranteed) | Giới hạn (Bounded, Not Prevented) | Không bao quát (Not Covered) |
| :--- | :--- | :--- |
| • Chính sách giá trị cho mọi tài sản được theo dõi trong dải giá oracle.<br>• Người thụ hưởng nhận đúng số tiền tối thiểu $\pi_{a,q}$.<br>• Hạn mức approval không vượt quá giá trị mô phỏng.<br>• Hợp đồng sở hữu giữ nguyên chủ.<br>• **Giữ nguyên hiệu lực dưới mọi biến động State Drift**. | • Tổn hại nằm *trong* chính sách (phí giao dịch, trượt giá hợp lệ, rút tiền dưới ngưỡng): bị giới hạn bởi ngân sách phiên $W_{\text{max}}$.<br>• Biến động trạng thái trong ngưỡng trượt giá cho phép $\tau$. | • Các tài sản chưa được định giá/theo dõi (NFTs, vị thế không có balance view).<br>• Chữ ký off-chain (EIP-712 permits).<br>• Giao dịch ETH nội bộ trong hợp đồng (nếu không quan sát được).<br>• Nhập sai chính sách hoặc dải oracle sai. |

### 2.4. Định lý Tính đúng đắn (Theorem 1: Soundness of Assert Mode)
Nếu SMT Solver xác nhận $\forall p \in [\underline{p}, \overline{p}], \forall \Delta \ge c: L(\Delta, p) \le s V(c, p) + f$ và $W_{\text{spent}} + L(\Delta, p) \le W_{\text{max}}$, đồng thời ví `W.executeChecked(b, \Phi)` thực thi thành công không bị revert on-chain, thì đối với mọi vectơ giá trong dải, thay đổi số dư thực tế **chắc chắn thỏa mãn chính sách giá trị**. Điều này đúng dưới mọi chuỗi biến động trạng thái giữa thời điểm mô phỏng và thời điểm giao dịch được đưa vào block.

---

## 3. Kiến trúc Kỹ thuật của PGS

### 3.1. Quy trình Thực thi (Pipeline)
1. **Simulate**: Tạo snapshot môi trường local fork, chạy giao dịch từ khóa agent, ghi nhận hiệu ứng $E$, sau đó revert snapshot.
2. **Extract Effects**: Trích xuất biến động số dư $\Delta_a$, residual allowances, quyền sở hữu hợp đồng, tiền chuyển đến EOA, và các khoản thanh toán $\pi_a$.
3. **Prove Policy (Z3 SMT Solver)**: Kiểm tra mệnh đề $\exists p \in \text{band}: \neg \text{Policy}(\Delta_{\text{sim}}, p)$. Nếu tìm thấy nghiệm (sat), trả về counterexample để từ chối giao dịch.
4. **Compile & Prove Bounds**: Biên dịch các ngưỡng $c_a = \lfloor (1 - \tau) \Delta_{\text{sim}} \rfloor$ cho tiền vào (inflows) và giữ chính xác cho tiền ra (outflows). Dùng Z3 chứng minh lại mệnh đề $\forall p \in \text{band}, \forall \Delta \ge c \Rightarrow \text{Policy}(\Delta, p)$.
5. **Execute Checked**: Ký và gửi `W.executeChecked(b, \Phi)`. Ví hợp đồng sẽ kiểm tra số dư thực tế on-chain nguyên tử với lệnh thực thi.

### 3.2. Sửa lỗi Kiểm toán Thanh toán (Payment-Crediting Fix)
Trong phiên bản dự thảo đầu tiên, khoản thanh toán $\pi$ được tính dựa trên số lượng trong calldata. Qua kiểm toán độc lập, tác giả phát hiện kẻ tấn công có thể dùng token có phí chuyển (fee-on-transfer) để trích một phần tiền thanh toán về cho chủ token mà không bị phát hiện.

Trong phiên bản chính thức, $\pi$ được định nghĩa lại là **giá trị nhỏ hơn giữa số lượng dự định và số lượng thực sự nhận được trong tài khoản người thụ hưởng ở bước mô phỏng**. Phí phát sinh từ token sẽ bị tính là tổn hại ($L$), chặn đứng kịch bản lừa đảo này (Họ tấn công H14).

### 3.3. Lý do Sử dụng SMT Solver (Z3)
Dù công thức chính sách giá trị đơn giản có thể kiểm tra ở các góc biên (corners), SMT Solver được chọn vì 3 lý do:
1. **Một thủ tục quyết định duy nhất được xác minh**: Dùng chung cho cả bước Check và bước Compile mà không cần viết lại logic phân tích tay khi thay đổi policy.
2. **Bằng chứng Counterexample minh bạch**: Khi từ chối, Z3 trả về ví dụ cụ thể (vd: *"Tại WETH = 2,487.5 và USDC = 1.005, mức lỗ là $3,458"*).
3. **Khả năng mở rộng**: Dễ dàng hỗ trợ các chính sách phức tạp sau này (chính sách đa tài sản, mô hình giá tương quan, khung phí từng phần).

---

## 4. Đánh giá Thực nghiệm & Bộ Testbed 260 Kịch bản

### 4.1. Thiết lập Bộ Thử nghiệm (Testbed)
Thử nghiệm gồm 260 kịch bản chia thành 26 họ (mỗi họ 10 biến thể ngẫu nhiên):
- **14 Họ Tấn công (140 scenarios)**: Bao gồm 5 họ tấn công biến động trạng thái (State Drift H6–H8, H13, H14) và 2 họ tấn công thích ứng.
- **12 Họ Hợp lệ (120 scenarios)**: Các tác vụ swap, thanh toán, gửi/rút tiền khỏi Vault, giao dịch đa chặng (multihop).

### 4.2. Bảng Kết quả So sánh Tổng thể

Dưới đây là bảng tổng hợp kết quả của các cơ chế bảo vệ trên 260 kịch bản:

| Cơ chế Bảo vệ | Attack Prevention Rate (APR) [95% CI] | Benign Pass Rate (BPR) [95% CI] | Số lệnh bị Revert On-chain | Thiệt hại Kẻ tấn công (Attacker Gain) |
| :--- | :---: | :---: | :---: | :---: |
| **None** (Không bảo vệ) | 0.000 [0.000, 0.027] | 1.000 [0.969, 1.000] | – | $12.18M |
| **Static Allowlist** | 0.714 [0.635, 0.783] | 0.833 [0.757, 0.889] | – | $558k |
| **PGS-sim** (Chỉ mô phỏng) | 0.579 [0.496, 0.657] | 0.975 [0.929, 0.991] | – | $855k |
| **PGS w/o receipts** | 0.864 [0.798, 0.911] | 0.975 [0.929, 0.991] | 30 | $80k |
| **PGS (Đầy đủ)** | **0.936** [0.882, 0.966] | **0.975** [0.929, 0.991] | **40** | **$42k** |

### 4.3. Phân tích Tấn công State Drift (50 Kịch bản)

5 họ tấn công (H6, H7, H8, H13, H14 - tổng cộng 50 kịch bản) thực hiện can thiệp vào chuỗi giữa lúc Guard kiểm tra và lúc đóng block:
- **PGS-sim (chỉ mô phỏng)**: **Bỏ sót toàn bộ 50/50 kịch bản**. Kết quả mô phỏng pre-signing hoàn toàn sạch sẽ, nhưng giao dịch thực thi lại bị can thiệp gây thiệt hại.
- **Static Allowlist**: Bỏ sót 40/50 kịch bản do các hợp đồng bị tấn công nằm trong danh sách cho phép (như Uniswap pool, token TAX).
- **Proof-Gated Signing (PGS)**: **Ngăn chặn 50/50 kịch bản drift (Attacker gain = $0)**:
  - 30 kịch bản (H6, H7, H8) bị **Revert trực tiếp on-chain** do điều kiện số dư ví không đạt ngưỡng $c$.
  - 10 kịch bản (H14 - Fee rug khi thanh toán) bị **Revert trực tiếp on-chain** nhờ kiểm tra biên nhận người thụ hưởng (payee receipt check).
  - 10 kịch bản (H13 - Mempool-aware sandwich): Kẻ săn MEV đọc hậu điều kiện $\Phi$ trong mempool và front-run đến mức tối đa cho phép. Tuy nhiên do phí bể 0.3% và ngưỡng trượt giá $\tau = 1\%$, kẻ tấn công không tìm thấy khoảng lợi nhuận nào, giao dịch thực thi an toàn.

### 4.4. Tấn công Rút tiền Trong Chính sách (In-Policy Drain H12)
Trong họ tấn công H12, kẻ tấn công thực hiện 20–30 giao dịch swap trên bể skim pool, mỗi giao dịch chỉ gây thiệt hại 1.8% (nằm trong ngưỡng $s = 3\%$ của per-transaction policy).

Không có kiểm tra đơn giao dịch nào có thể chặn được H12. Tuy nhiên, nhờ **Ngân sách Phiên ($W_{\text{max}} = \$5,000$)**, PGS đã chặn đứng chuỗi giao dịch ngay khi tổng thiệt hại tích lũy chạm ngưỡng, giới hạn mức mất mát ở mức $\$4.53k - \$4.76k$ (so với $\$12.18M$ khi không bảo vệ).

### 4.5. Chi phí Gas & Độ trễ

| Chỉ số | Không bảo vệ (Unguarded) | Proof-Gated Signing (PGS) | Chi phí Bổ sung (Overhead) |
| :--- | :---: | :---: | :---: |
| **Gas Trung vị (Median Gas)** | 89.9k gas | 131.0k gas | **+41.1k gas (+46%)** |
| **Độ trễ Quyết định (Latency)** | – | 163 ms (p95: 275 ms) | **~0.1–0.2 giây** |

Chi phí gas cố định 41.1k gas chủ yếu đến từ việc đọc lại số dư trước và sau khi thực hiện lệnh gọi trong ví. Đối với các giao dịch DeFi thực tế phức tạp (hàng trăm nghìn gas), tỷ lệ overhead này sẽ giảm đi đáng kể.

### 4.6. Phân tích So sánh với LLM Judge Baseline

Thử nghiệm trên tập 120 kịch bản so sánh PGS với phương pháp dùng mô hình LLM tiên tiến (Claude Opus) làm bộ duyệt giao dịch (LLM Judge):

| Họ Tấn công / Tác vụ | Static Allowlist | LLM Judge (Call-only) | LLM Judge (+ Simulation) | PGS-sim | PGS (Full) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **H1 Direct Transfer** | 5/5 | 3/5 | 3/5 | 5/5 | **5/5** |
| **H5 Fake Pool** | 5/5 | 1/5 | 5/5 | 5/5 | **5/5** |
| **H6 Sandwich (Drift)** | 0/5 | 5/5 | 4/5 | 0/5 | **5/5** |
| **H7 Proxy Upgrade (Drift)**| 5/5 | 3/5 | **0/5** | 0/5 | **5/5** |
| **H8 Fee Rug (Drift)** | 0/5 | 0/5 | 0/5 | 0/5 | **5/5** |
| **B8 Honest Non-allowlisted**| 0/5 | 5/5 | 5/5 | 5/5 | **5/5** |
| **B12 High-impact Swap** | 0/5 | 1/5 | 5/5 | 3/5 | **3/5** |

**Phát hiện Định tính Quan trọng nhất**:
Khi cung cấp thêm báo cáo mô phỏng (Simulation) cho LLM Judge, tỷ lệ duyệt các tác vụ hợp lệ tăng từ 0.85 lên 0.98. Tuy nhiên, **báo cáo mô phỏng sạch lại khiến LLM Judge duyệt sai 100% cuộc tấn công nâng cấp hợp đồng độc hại (Proxy Upgrade H7 - từ 2/5 lừa lên 5/5 lừa thành công)**. Báo cáo mô phỏng (thực hiện trước khi nâng cấp) trông hoàn toàn an toàn đã đánh lừa LLM Judge. Đây là minh chứng rõ nhất cho thấy: **Mô phỏng tiền thực thi là bằng chứng về sai trạng thái, và việc cung cấp nó cho một bộ duyệt dạng suy luận có thể làm tình hình tồi tệ hơn nếu không có ràng buộc on-chain.**

---

## 5. Giới hạn & Hướng phát triển

### 5.1. Giới hạn của Hệ thống
1. **Thiệt hại trong chính sách**: PGS chỉ giới hạn thiệt hại tích lũy qua ngân sách phiên $W_{\text{max}}$, không thể chặn các giao dịch đơn lẻ cố tình gây thiệt hại nhẹ nằm trong ngưỡng trượt giá cho phép.
2. **Tài sản không được theo dõi**: Các tài sản chưa được định dạng giá (NFT, vị thế LP phức tạp) bị từ chối theo nguyên tắc bảo thủ.
3. **Chữ ký Off-chain**: Các chữ ký dạng EIP-712 permit nằm ngoài quy trình kiểm tra giao dịch của ví.

### 5.2. Hướng phát triển Trong Tương lai
1. Đo lường tỷ lệ trượt giá và State Drift thực tế trên mạng lưới Ethereum Mainnet.
2. Phát triển mô hình giá tương quan (correlated price models) cho SMT Solver đối với các vị thế đa tài sản.
3. Tích hợp PGS với chuẩn ví ERC-4337 dưới dạng Validator Module để thực thi quyền kiểm soát khóa riêng tư trực tiếp on-chain.
