# Fuji web demo — kiểm chứng và giới hạn

> **DOC STATUS: CURRENT_REVIEW_REPORT** — 20/11/2026. Phân biệt bằng chứng swap đã gửi với regression tests sau chỉnh sửa; không phải independent security audit.

## Kết quả giao dịch thật

Đã chọn Demo User qua Chromium, không nhập credential; gửi goal `Buy WAVAX with 0.000001 USDC` qua cùng pipeline Shield/ITAG/oracle/risk/SMT/signing/final preflight. Giao dịch được đối soát **CONFIRMED** trên Avalanche Fuji:

- Workflow `workflow_00370cd7f0c3479aacf9c9faced7940f`.
- Transaction `0x315a9bff8ba111487d295903ebd0f6389b1baefd40ea9526fc33bc014a9656ba`, block `61375517`.
- Actual input `-1` base unit Circle USDC; output `+13266640314006` base units WAVAX.
- Gas `356389 × 160 wei/gas = 57022240 wei AVAX` = `0.00000000005702224 AVAX`. Đây là gas price quan sát ở lượt đó, không cam kết phí tương lai.
- Credit charge một event, reservation còn `0`; chọn lại account/reconcile không cấp lại allocation.
- 14 chain checks và ba negative eth_call checks pass. SMT artifacts được rehash/re-solve SAT/UNSAT/SAT/UNSAT/UNSAT với source hash khớp engine hiện tại.

Raw evidence: [chain report](web-demo-fuji-chain-evidence.json), [web/billing report](web-demo-live-validation.json), [query directory](web-demo-live-proof/README.md). Browser receipt workflow có giai đoạn RPC chưa hội tụ trước khi được xác nhận; báo cáo giữ finding này, không sửa history để giấu nó.

## Chi phí setup tách riêng

Vault trước đó thiếu USDC headroom so với exposure 25%. Đã mua và nạp **253 USDC base units** bằng owner, không đổi policy; hai receipts setup nằm trong web/billing report. Native purchase là provisioning test assets, không phải gas của request Demo User. Relayer gas và credit debit chỉ tính actual swap receipt.

Lệnh `treasury fund-demo` là owner action riêng, capped/resumable một lần; không tự chạy khi chọn account/serve/retry. Chưa hứa nhiều lượt swap nếu vault lại hết exposure room. Test AVAX không tạo unlimited liquidity; có thể cần Circle faucet/top-up để trình diễn thêm.

## Các lỗi đã sửa

1. RPC read failure trước attestation làm lượt đầu ESCALATED, chưa broadcast/debit. Thêm đúng một retry cho GET RPC/transport errors, không retry mutations hoặc tự tạo transaction mới.
2. RPC có thể trả receipt trước latest-head/transaction inclusion view cập nhật; verifier giữ PENDING khi thiếu convergence, không gán reorg ngay và không charge unverified gas.
3. UI có thể dừng ở RECEIPT_MISMATCH hoặc observer chậm ghi đè kết quả mới; tiếp tục poll trạng thái review và bỏ observer response đến muộn sau POST completion.
4. LOCAL còn thừa defaults Fuji sau khi đổi chế độ mặc định; profile test riêng dùng controlled oracle/rules, không nhận model/wallet secrets Fuji. Service API credential LOCAL vẫn giữ để single-app auth hoạt động.

## Kịch bản hiện có và ý nghĩa evidence

Web tách **sử dụng bình thường** với **kiểm thử bảo mật**. Swap là public write khi mọi gate pass. Limits/auth/session checks dùng actual APIs/chain reads; contract replay/calldata/signature dùng historical eth_call trên swap Demo User. Ba fixed prompt-injection challenges chạy real configured model trong lab TOOL-role, không đưa vào swap thật. Model fail/unavailable phải hiển thị trung thực, không hardcode pass.

Real-model trace ban đầu đã ghi nhận recipient-redirect bị MISALIGNED; thêm choices policy-override/forged-user có offline dispatch tests. Chỉ các traces trong report mới được coi là kết quả real-provider, không suy mọi prompt injection đều bị chặn.

Full Python suite có checkpoint **473 passed, 4 skipped** trước các refinement UI/attack choices cuối. Những refinement có focused regression checks riêng; không cộng focused counts vào full count. Solidity **60 passed**, gồm hai fuzz tests × 256 runs. JavaScript syntax và Ruff pass. Lệnh kiểm browser có `--broadcast` opt-in riêng; mặc định không gửi swap.

## Cách kiểm lại không gửi transaction

```powershell
uv run --locked python tools/quality/check_live_demo.py --include-ai
uv run --locked python tools/evaluation/verify_fuji_queries.py --report docs/audit/web-demo-fuji-chain-evidence.json --queries docs/audit/web-demo-live-proof
```

Browser checker cần backend đang chạy và ít nhất một confirmed Demo User workflow cho historical contract checks. `--include-ai` dùng model quota/API thật; bỏ flag thì chỉ kiểm API/chain. Không thêm `--broadcast` chỉ để kiểm health. Xem [runbook web](../demo/LIVE_WEB_DEMO.md).

Chưa có hosting/mainnet/HA/customer payment/multi-user ownership/independent audit. Smart-contract treasury hiện tại là PolicyVault, không có ERC-4337 bundler/paymaster trong flow. Giá USD vẫn là Chainlink reference cho test assets; stress vẫn là hypothetical scenarios trên EVM fork.
