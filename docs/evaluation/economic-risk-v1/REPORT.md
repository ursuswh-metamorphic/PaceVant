# Economic risk benchmark v1 — 21/11/2026

Đánh giá **economic admissibility** của hai nghiệp vụ MVP bằng `assess_operation` và `prove_operation` thật (Z3 thật), với observations tổng hợp. Không gọi LLM/RPC, không fork EVM, ký hay chuyển tiền. Không dùng số đo AI security của bạn cùng nhóm để tính metric economic risk.

## Dataset và nhãn chuẩn

[Dataset JSONL](../../../fixtures/evaluation/economic-risk-v1/dataset.jsonl), [manifest](../../../fixtures/evaluation/economic-risk-v1/manifest.json): **800 ca**, seed `20261121`, 16 nhóm, mỗi nhóm 50 ca. Các nhóm gồm swap/payment bình thường; loss bound sát ngưỡng; compiled min-output; session/global risk; spend caps; payment caps và short receipt; exposure; oracle lifetime; allowance; effects chưa xác minh; disabled asset debit; invalid price band; nhiều mức giá/price bands. Amount có phần lẻ base unit, giá WAVAX $2/$7/$20/$80/$150 và nhiều mức vốn. Không lấy prediction để sinh gold, loại ca hoặc chọn seed.

Gold do [economic_oracle.py](../../../tools/evaluation/economic_oracle.py) tính bằng `Fraction` và liệt kê bốn đỉnh miền giá hai tài sản. Không import backend/proof/Z3. Nhãn tuân theo đặc tả: loss đo được và miền compiled phải trong relative/fixed/cumulative budget; spending payment tách risk debit; output/receipt/exposure/freshness/integrity phải đủ. Mỗi ca giữ input, family, group ID, gold, split, provenance. `REJECT` là positive class; false approval là rủi ro cần ưu tiên.

Chia cố định **160 development / 640 test**, không trùng group ID. Hai split vẫn dùng cùng generator/template families nên chỉ là test split tái lập của bộ tổng hợp, **không phải blind external holdout**. Không tối ưu production code trên test split. Giá và effects là dữ liệu dựng theo specification, không được gọi là giao dịch Fuji thật.

## Kết quả cuối

| Metric trên 640 test cases | Kết quả |
|---|---:|
| Accuracy | 100% |
| Precision, REJECT | 100% |
| Recall, REJECT | 100% |
| F1, REJECT | 1.0000 |
| Macro F1 | 1.0000 |
| True reject / true approve | 288 / 352 |
| False approval / false rejection / harness error | 0 / 0 / 0 |

[metrics.json](metrics.json) có kết quả toàn bộ, theo split/family, confusion matrices, latency, Wilson interval và baseline luôn approve/reject. [predictions.jsonl](predictions.jsonl) lưu từng prediction/reason, [errors.json](errors.json) giữ tất cả mismatch. Wilson 95% accuracy khoảng **99,40%–100%**, chỉ mang tính mô tả dưới giả định các ca độc lập; các template có tương quan nên không suy ra field accuracy. Không có false approval trong 288 unsafe cases không chứng minh xác suất false approval thực tế bằng 0.

[stability.json](stability.json) ghi ba lần chạy trên cùng corpus ở ba Python process, decisions/reasons giống nhau. Đây là reproducibility/determinism, không phải ổn định trên thị trường nhiều ngày. Latency chỉ thuộc máy local, không phải VPS SLO.

## Sai sót và thay đổi trong vòng đánh giá

Lượt đầu đạt accuracy test **99,0625%**, F1 **0,98997**, với sáu false rejection theo gold lúc đó. Đã lưu [initial metrics](initial-metrics.json) và [initial mismatches](initial-errors.json), không xóa lịch sử. Rà soát cho thấy oracle tham chiếu ban đầu chỉ kiểm age < 300 giây, bỏ sót yêu cầu **approval deadline không vượt oracle valid-until**. Với TTL 60 giây, age 299 giây phải reject. Đã bổ sung TTL vào schema/gold, mở rộng freshness boundary 239/240/241 giây và thêm ca tính tay. Generator mới dùng cùng seed nhưng thêm age candidates làm thay đổi chuỗi random ở các ca sau; final dataset có hash mới. Vì đã xem lỗi trong vòng phát triển này, không gọi test cuối là untouched holdout. Không sửa production economic logic, threshold hoặc policy để nâng điểm.

## Phạm vi độc lập và giới hạn

Nhãn độc lập về **implementation**: arithmetic oracle không gọi hệ thống cần đánh giá. Dataset và oracle vẫn do cùng tác giả/nhóm dự án tạo theo cùng specification; chưa có nguồn dữ liệu bên thứ ba hoặc adjudication độc lập. 100% cho thấy conformance trên các ca đã dựng, không chứng minh 100% độ an toàn ngoài thực tế. Cần freeze bản này trước khi thu thêm external/real market cases hoặc nhờ người khác gán nhãn blind.

Bản v1 chỉ có USDC-input forward swap và USDC payment, không đánh giá reverse swap, session/recipient on-chain allowlist, gas pricing market, mất RPC, receipt canonicality, oracle manipulation hay prompt injection. Các price bands/measurements là giả định đầu vào; một proof đúng trong band không chứng minh band đúng ngoài thị trường. Missing price-band/malformed data có thể cần benchmark ba lớp riêng; v1 gộp không đủ điều kiện vào REJECT. Không dùng approved/rejected để kết luận transaction đã thực thi.

## Chạy lại

```bash
# Chỉ generate khi chủ động tạo lại corpus; file đã freeze và có SHA-256.
uv run --locked python tools/evaluation/build_economic_dataset.py
uv run --locked python -m pytest backend/tests/control/test_economic_dataset.py -q
uv run --locked python tools/evaluation/evaluate_economic_dataset.py
```

Evaluator kiểm dataset hash trước khi chạy, lưu source commit và SHA-256 của risk/proof/oracle/generator/evaluator. Exceptions ngoài expected rejection được tính ERROR và không nhận điểm đúng. Mọi ca đều được ghi, không bỏ exception hoặc chỉ tính successful requests.
