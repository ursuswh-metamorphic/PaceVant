# PaceVant

> **DOC STATUS: CURRENT_INDEX** — hiện trạng source baseline `3f9f9af`, rà soát 20/11/2026. Không có giao dịch hoặc live readiness check mới trong lần chuẩn hóa docs.

PaceVant là treasury security system: AI đề xuất swap, hệ thống kiểm quyền và intent, mô phỏng fork, đánh giá rủi ro, chứng minh bounded postcondition bằng Z3, ký approval và thực thi qua Solidity PolicyVault trên Avalanche Fuji. Backend là **một Python/FastAPI modular monolith**, frontend là HTML/CSS/browser JavaScript. Native Anvil phục vụ mô phỏng; Node.js chỉ là tooling phát triển tùy chọn.

Đọc [System Design V2.1 hiện tại](docs/AI_Treasury_Security_System_Design_v2.1.md) để xem đầy đủ kiến trúc, từng module, input/output, sources, luồng bảo mật, Solidity enforcement, session/budget, gas accounting, storage/recovery và giới hạn. [Gói phản biện](docs/REVIEWER_GUIDE.md) chỉ rõ tài liệu nên gửi cho người review hoặc AI; [chỉ mục tài liệu](docs/README.md) phân biệt hiện hành với lịch sử.

Muốn gửi AI **một file duy nhất**: [Hồ sơ hiện trạng, thiết kế và phản biện](docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md), có trạng thái từng thành phần, data thật/mock, assumptions, bằng chứng và các việc còn mở.

## Hiện trạng thực tế

- Core pipeline đã có transaction/receipt Fuji ở checkpoint trước; dùng Chainlink Fuji và LFJ với Circle test USDC → WAVAX. Không còn mô tả đây là đường controlled oracle/mock DEX trong live profile.
- Demo User chọn sẵn trên website, không Connect Wallet hoặc nhập token. Vẫn đi qua toàn bộ pipeline; swap dùng treasury vault, relayer trả gas. Gas credit là sponsor allowance off-chain, khác với AVAX trong ví.
- Gas ledger và one-click demo có offline/Anvil validation; **chưa có public Fuji end-to-end riêng cho phần bổ sung này**. Session/funding/providers và process đã load code mới cần kiểm khi demo; source trên đĩa không chứng minh runtime sẵn sàng.
- MOCK/LOCAL và fixtures vẫn phục vụ tests. USD cho test token là policy reference, không phải khả năng redeem hoặc chứng minh sinh lời. Reverse Fuji swap, payment/multi-user/HA và independent audit chưa thuộc phần đã hoàn thiện.

## Chạy trên máy operator

Python 3.12, uv và native Foundry theo project lock/bootstrap. Từ repository root:

```powershell
uv sync --locked
uv run --locked python tools/contracts/bootstrap.py
uv run --locked treasury doctor --network fuji
uv run --locked treasury doctor --network fuji --live
uv run --locked treasury serve --network fuji
```

Hai lệnh doctor chỉ kiểm local/read-only RPC; serve dùng deployment/profile đã có, khởi động API và monitor. Mở `http://127.0.0.1:8000`, chọn **PaceVant - Demo User** rồi xem trạng thái. Bấm chạy goal sẽ khởi chạy pipeline và có thể gửi giao dịch Fuji thật; không dùng thao tác đó như health check. Nếu session/vốn/policy không đủ, xử lý nguyên nhân trước.

Hướng dẫn thao tác: [Demo User và gas credit](docs/demo/DEMO_USER_GAS_CREDIT.md), [system design mục vận hành](docs/AI_Treasury_Security_System_Design_v2.1.md#20-vận-hành-demo-và-chuẩn-bị-phản-biện). `deploy`, `renew-session`, `renew-policy`, `demo`, `fuji-demo` có thể ký/gửi transaction; `fuji-demo --setup` còn setup/funding. Không tự chạy các lệnh này để kiểm process.

## Source và phát triển

| Thành phần | Điểm bắt đầu |
| --- | --- |
| Backend, 15 modules | [backend README](backend/README.md), [module map](backend/MODULES.md) |
| Frontend và Demo User | [frontend README](frontend/README.md), [demo feature](frontend/src/features/demo/README.md) |
| Shared types/hash/proof/SDK | [contracts-api](packages/contracts-api/README.md) |
| Solidity vault/adapter | [contracts](contracts/README.md) |
| Deployment | [deploy](deploy/README.md) — hosting chưa được chứng minh bằng smoke test |
| Quy tắc đóng góp/tests | [CONTRIBUTING](CONTRIBUTING.md), [test guide](backend/tests/README.md) |

Kiểm tra phù hợp khi sửa code: `uv run --locked python -m pytest -q`, `uv run --locked python tools/contracts/foundry.py forge test -vv`, `uv run --locked ruff check backend/src backend/tests tools`, `uv run --locked python tools/quality/scan_secrets.py`. Các lệnh này không được coi là đã chạy lại chỉ vì xuất hiện trong README; evidence theo từng checkpoint nằm trong design/manifest.

`.env` và `.env.example` có cùng 104 tên biến ở lần kiểm kê; template mặc định không phải effective Fuji profile. Không commit private env, keys, raw signed transaction, DB/journal/log runtime. Tài liệu mang `HISTORICAL_*` chỉ để truy nguyên, không dùng làm hướng dẫn triển khai hiện tại.
