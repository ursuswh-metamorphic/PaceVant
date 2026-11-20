# Gói tài liệu phản biện PaceVant

> **DOC STATUS: CURRENT_REVIEW_GUIDE** — source baseline `3f9f9af`, 20/11/2026. Không chia sẻ `.env` hoặc private logs/DB/keys với AI bên ngoài.

## Gửi tài liệu nào?

Nếu chỉ muốn gửi **một file Markdown**, dùng [Hồ sơ hiện trạng và phản biện PaceVant](PACEVANT_CURRENT_SYSTEM_REVIEW.md). File tự chứa mô tả kiến trúc, từng module/input-output, data thật/mock/giả định, bằng chứng và các phần chưa kiểm chứng. Người chỉ nhận file này có thể phản biện thiết kế; để xác minh implementation/evidence độc lập vẫn cần source/artifacts tương ứng.

Gửi [System Design V2.1](AI_Treasury_Security_System_Design_v2.1.md) làm bản chính. Đính kèm [sanitized inventory](current-system-inventory.json), [API catalog](current-api-catalog.json), [documentation manifest](DOCUMENTATION_MANIFEST.json) và [Demo User runbook](demo/DEMO_USER_GAS_CREDIT.md). Bộ này đủ để hiểu trách nhiệm, IO, trust boundaries, flows và trạng thái implementation hiện tại mà không cần đọc các design lịch sử.

Để kiểm bằng chứng, thêm ba nhóm: [core Fuji validation](audit/system-security-live-validation.json) cùng [review](audit/SYSTEM_SECURITY_REAL_DATA_REVIEW.md)/[proof files](audit/system-security-live-proof/README.md); [demo billing validation](audit/demo-user-gas-credit-validation.json); [one-click auth validation](audit/demo-account-selection-validation.json). Mỗi nhóm có checkpoint/mode/scope riêng. Raw evidence không tự trở thành “test HEAD trên Fuji”.

## Nếu reviewer cần source

| Nội dung phản biện | Source nên đọc |
| --- | --- |
| Một backend, injected execution | [api/app.py](../backend/src/treasury_backend/api/app.py), [local adapter](../backend/src/treasury_backend/api/local_execution.py) |
| Demo quyền hẹp / không cần wallet | [demo routes](../backend/src/treasury_backend/api/demo.py), [auth](../backend/src/treasury_backend/api/demo_auth.py), [config](../backend/src/treasury_backend/config/demo.py) |
| Luồng và revalidation | [workflows](../backend/src/treasury_backend/modules/workflows/README.md), service/evaluation/authorization trong folder đó |
| Prompt injection/temporal authorization | [alignment](../backend/src/treasury_backend/modules/alignment/README.md), [temporal](../backend/src/treasury_backend/modules/temporal/README.md) |
| Loss theorem/Phi | [shared proof engine](../packages/contracts-api/treasury_contracts/proof.py), [V2 model](../packages/contracts-api/treasury_contracts/v2.py), [risk](../backend/src/treasury_backend/modules/risk/README.md) |
| Oracle provenance | [oracle](../backend/src/treasury_backend/modules/oracle/README.md), [shared oracle contracts](../packages/contracts-api/treasury_contracts/oracle.py) |
| Fork và final guarded call | [simulation module](../backend/src/treasury_backend/modules/execution/simulation/README.md) |
| EVM enforcement/revert | [PolicyVault.sol](../contracts/src/PolicyVault.sol), [LFJSwapAdapter.sol](../contracts/src/adapters/LFJSwapAdapter.sol) |
| Journal/actual gas/reorg | [relaying](../backend/src/treasury_backend/modules/execution/relaying/README.md), [monitoring](../backend/src/treasury_backend/modules/monitoring/README.md), [gas_credit](../backend/src/treasury_backend/modules/gas_credit/README.md) |
| Browser/account/fee display | [demo UI](../frontend/src/features/demo/README.md), [frontend](../frontend/README.md) |

## Thứ tự giải quyết khi tài liệu mâu thuẫn

1. Source thực tế + effective configuration đã lọc ở baseline được review.
2. Bằng chứng đúng mode/commit/workflow/transaction, chỉ cho kết luận trong scope đó.
3. Canonical current design và current runbook; cập nhật nếu source khác.
4. Module/component README cho interface cục bộ.
5. Historical docs để hiểu lịch sử, không dùng phủ định hoặc nâng mức sẵn sàng hiện tại.

Ngày tạo docs mới không phải ngày chạy lại transaction. Receipt core có trước gas credit không chứng minh billing hoạt động Fuji. Testnet token có giá reference không chứng minh có giá thị trường/redeem USD.

## Câu hỏi kỹ thuật nên phản biện

- Trusted attestor có thể chứng thực sai điều gì? Vault tự kiểm phần nào, không tự kiểm phần nào?
- Proof đang lượng hóa over price/effect bounds nào? Assumptions token/adapter/oracle là gì? Có nhầm SAT với “safe” không?
- Dữ liệu pin block/hash/round ra sao? Sau model/fork kéo dài, freshness có được kiểm lại không?
- Pending/unknown broadcast, concurrent requests và crash giữa hai SQLite DB được xử lý thế nào?
- Receipt canonicality/confirmations/reorg có tác động gì đến outcome và gas ledger?
- Demo credit có thực sự là deposit không? Ai có quyền tiêu shared allowance? Scope demo credential có thể nâng quyền không?
- Case reject trước gửi có tốn gas không? Revert rollback những gì, phí nào không được hoàn lại?
- Code/current runtime/evidence có đang bị đánh đồng? Phần nào chưa browser/Fuji/hosting validated?

## Prompt có thể dùng cho AI bên ngoài

> Hãy review PaceVant theo current system design và sanitized inventory đính kèm. Tách phát hiện từ source, kết luận theo evidence và giả định chưa kiểm chứng. Không coi HISTORICAL docs là mô tả hiện tại. Đặc biệt phản biện trusted attestor/oracle mapping, bounded SMT theorem, revalidation/time-of-check-to-use, on-chain Phi, ITAG concurrency, gas reserve/journal/settlement/reorg và shared demo auth. Chỉ ra lỗ hổng với đường code hoặc invariant cụ thể; không suy profitability/production-readiness từ testnet. Không yêu cầu private keys; không gửi giao dịch hay sửa policy để thử nghiệm.

Việc review nên bắt đầu bằng tài liệu/source và tests offline. Mọi thao tác chạy thật, renew policy/session hoặc setup Fuji là bước vận hành riêng, có thể tốn test AVAX; không cần chúng để đọc và phản biện kiến trúc.
