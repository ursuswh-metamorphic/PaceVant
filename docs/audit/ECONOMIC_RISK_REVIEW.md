# Kiểm thử economic risk — 20/11/2026

> **DOC STATUS: CURRENT_REVIEW_REPORT** — runtime source baseline `39342cb`. Chỉ kiểm economic risk và các gate proof/budget liên quan; không sửa phần kiểm thử tấn công.

## Kết quả

**127 tests Python pass**, **8 tests Solidity về ngân sách/risk pass**, gồm 256 lượt fuzz cho budget invariant. Bổ sung 47 trường hợp economic risk trong `backend/tests/control/test_economic_risk.py`, trong đó một test so sánh 150 bộ dữ liệu với phép tính `Fraction` độc lập, seed cố định.

Không phát hiện lỗi tính toán/enforcement mới trong phạm vi đã kiểm. Không thay logic runtime, policy, session, biến môi trường hoặc smart contracts để làm test pass. Không gọi model, gửi transaction Fuji hoặc phát sinh gas trong đợt kiểm tra này. [Evidence JSON](economic-risk-validation.json) lưu kết quả và snapshot cụ thể; đây không phải audit độc lập hoặc bảo đảm mọi tình huống đều an toàn.

## Những gì được kiểm

| Nhóm | Tình huống và kỳ vọng |
| --- | --- |
| Happy path | Risk PASS với đủ facts, đúng input/output IDs, exposure tính đúng |
| Hạn mức từng swap | Đúng cap được chấp nhận; vượt 1 USDC base unit bị từ chối |
| Hạn mức ngày | Dùng remaining = limit − spent; không dùng lại phần đã tiêu; remaining 0 bị chặn |
| Số dư | Không đủ input bị chặn; gợi ý amount không vượt available balance |
| Exposure WAVAX | Đúng 25% được chấp nhận; thêm 1 WAVAX base unit vượt ngưỡng bị chặn; ceil bps bảo thủ |
| Slippage/minOut | Tại floor minOut tham chiếu được chấp nhận; thấp hơn 1 base unit bị chặn |
| Value loss | Lỗ bằng `relative × outgoing + fixed` được chấp nhận; vượt một đơn vị biểu diễn bị chặn; fixed USD không bị nhân thêm notional |
| Gas budget | Có actual simulation gas × fee estimate, prior native cost và legacy USD cost; tính bằng integer và ceil USD-e8; vượt budget bị chặn |
| Đủ dữ liệu | Zero/unsupported prices, missing gas price, stale/future facts, khác scope/balance/block, sai ngày/deadline không PASS |
| Thời gian | Đúng giới hạn 60s/300s hợp lệ trong fixture tương ứng; quá 1s hoặc future timestamp bị chặn |
| Chiều reverse | LOCAL dùng cap WAVAX riêng và không ăn USDC daily-spend cap; không suy live Fuji hỗ trợ reverse |
| Independent arithmetic | 150 portfolios/price pairs so với công thức Fraction độc lập; 6/18 decimals, amounts lớn hơn khả năng biểu diễn chính xác của JavaScript Number |
| SDE | Economic FAIL không tạo APPROVE; reason codes đi tiếp tới decision |
| Interval proof | Nominal risk PASS không ghi đè counterexample khi xét toàn bộ price band |
| Certified risk headroom | Đúng remaining session/global risk đủ thì VERIFIED; thiếu 1 USD-e8 unit thì proof không VERIFIED |
| Solidity | Session cumulative/global caps, ngày UTC không reset session, owner session mới không reset global usage, atomic daily race và fuzz budget invariant |

Giá trị slippage/policy rộng hơn trong một số fixtures là **owner config LOCAL có nhãn test**, không sửa hoặc mô tả rằng Fuji mandate hiện cho phép mức đó. Các test không claim input giả lập là dữ liệu thị trường thật.

## Công thức và điểm cần hiểu

Exposure được kiểm trên **danh mục sau swap**, dùng measured output và giá USD reference:

```text
USDC_value  = USDC_base_units * USDC_price_e8 / 10^6
WAVAX_value = WAVAX_base_units * AVAX_price_e8 / 10^18
exposure    = ceil(10000 * projected_WAVAX_value / projected_total_value)
```

Output tốt hơn có thể giảm value loss nhưng lại tăng exposure; vì vậy một swap “đổi được nhiều WAVAX” vẫn có thể bị chặn đúng. Amount gợi ý khi replan chỉ là hint, không phải approval; phải build/simulate/evaluate/prove lại.

Nominal value loss và bounded proof là hai lớp:

```text
loss(p)     = -sum(delta_i * p_i / 10^decimals_i)
outgoing(p) = -sum(min(delta_i * p_i / 10^decimals_i, 0))
loss(p) <= relative_loss_bps / 10000 * outgoing(p) + fixed_loss_usd_e8
```

Risk gate dùng giá nominal đã xác minh; PGS còn xét mọi giá trong bands, compiled Phi và session/global room. Feasibility cần SAT, counterexample obligations cần UNSAT. UNKNOWN không tạo approval.

Ba ngân sách không được nhầm:

- **Certified risk debit:** worst-case reference loss trong model/Phi; có thể khác nominal loss và khác tổng vốn swap.
- **Economic execution-cost budget:** gas được định giá USD reference cùng lịch sử chi phí.
- **Demo gas credit:** reserve/debit integer wei AVAX theo transaction/receipt, nằm ở ledger riêng.

## Replay dữ liệu thật của giao dịch đã chạy

Đã mở control database ở chế độ SQLite `mode=ro` và tính lại từ original immutable inputs của workflow `workflow_00370cd7f0c3479aacf9c9faced7940f`, tại **timestamp decision gốc**:

| Giá trị | Kết quả |
| --- | --- |
| Public tx đã có từ trước | `0x315a9bff8ba111487d295903ebd0f6389b1baefd40ea9526fc33bc014a9656ba` |
| Risk tính lại | PASS; khớp toàn bộ saved risk record |
| Exposure dự kiến tại lần đó | 2492 bps = 24,92%, trần 2500 bps |
| Proof tính lại | VERIFIED; proof context hash khớp decision |
| Certified debit tại lần đó | 0 USD-e8 theo price bands/Phi của trade nhỏ đó |
| Input/output | 1 USDC base unit → 13266640314006 WAVAX base units |

Replay dùng dữ liệu thật đã lưu, không chạy lại swap và không biến snapshot cũ thành fresh authorization. Debit 0 ở một trade không có nghĩa toàn bộ chiến lược không có rủi ro hoặc mọi trade có debit 0.

## Tình trạng economic risk trên Fuji khi kiểm tra

Đã đọc balances, original Chainlink rounds và LFJ quote tại pinned block **61376641**. Không tạo fake simulation evidence để đưa quote qua signing.

| Chỉ số | Snapshot |
| --- | --- |
| Vault Circle USDC | 1378 base units = 0,001378 USDC |
| Vault WAVAX | 66137381683518 base units |
| Current exposure, ceil bps | 2490 bps ≈ 24,90% |
| Nếu mua thêm bằng 1 USDC base unit theo LFJ quote | Exposure dự kiến 2849 bps ≈ 28,49% |
| Trần hiện có | 2500 bps = 25% |
| Kết luận phạm vi quote | Không đạt exposure gate; cần thêm Circle USDC headroom nếu muốn swap tiếp |

Đây là **điều kiện từ chối đúng**, không phải lỗi cần tắt trần. Lượng USDC thiếu để đáp ứng đúng quote này được ghi trong evidence JSON; quote/prices có thể đổi nên phải đọc lại trước vận hành. Không tự nạp vốn, bán tài sản hoặc nới policy trong đợt kiểm thử.

Quote-only diagnostic chưa kiểm đủ full simulation/stress/proof/session/freshness/submit. Passing một diagnostic không cấp quyền gửi giao dịch. USD vẫn là Chainlink reference mapping cho test tokens, không chứng minh giá trị redeem hoặc lợi nhuận kinh tế trên mainnet.

## Chạy lại các kiểm thử đã dùng

```powershell
uv run --locked python -m pytest backend/tests/control/test_economic_risk.py backend/tests/control/test_workflows.py backend/tests/control/test_v2_gates.py backend/tests/control/test_chainlink_live.py backend/tests/integration/test_proof_v2.py -q
uv run --locked python tools/contracts/foundry.py forge test --match-contract PolicyVaultV2Test --match-test 'test(Session|Global|DailyRisk|V2DailyRace|FuzzBudgetInvariant|NormalExactDeltasAndCounters|ReverseHasSeparateCap)' -vv
```

Hai lệnh dùng fixtures/local EVM, không cần model hoặc transaction Fuji. Snapshot Fuji/read-only replay là bằng chứng bổ sung đã ghi, không tự phát sinh lại khi chạy unit tests. Không cộng 150 so sánh hoặc 256 fuzz runs vào số test cases để quảng cáo thành một tổng test độc lập.
