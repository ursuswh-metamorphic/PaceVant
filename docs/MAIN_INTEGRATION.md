# Trạng thái main sau tích hợp

Ngày 19/11/2026 (giờ Việt Nam), theo yêu cầu người dùng:

- Tạo `main` từ nền A+B đã tích hợp (`1b09bd8`).
- Merge [PR #1](https://github.com/ursuswh-metamorphic/PaceVant/pull/1), gồm Fuji wallet/oracle reader, tại `e45f057`.
- Merge [PR #2](https://github.com/ursuswh-metamorphic/PaceVant/pull/2), gồm LFJ thật và fork evidence, tại `cd9be15`.
- Đặt `main` làm default branch. Lịch sử hai nhánh nguồn được giữ nguyên trong main.
- Đã xóa đúng hai nhánh remote `codex/lfj-fuji-execution` và `feat/fuji-wallet-oracle-readonly` sau khi xác nhận các commit được giữ lại và mọi kiểm tra hoàn tất. Nhánh local LFJ cũng đã xóa; local không có nhánh tên `feat/fuji-wallet-oracle-readonly`. Các nhánh khác được giữ nguyên.

Source tree sau hai merge khớp nhánh LFJ đã kiểm thử; các cập nhật tiếp theo ở main chỉ bổ sung tài liệu và bằng chứng kiểm tra. Không nới policy, oracle identity, TTL, block drift hay quyền broadcast trong lúc ghép.

## Cách chạy theo từng phần

Cài Node >=22.13, Python 3.12 và uv, chạy ở root:

```powershell
npm ci --ignore-scripts
npm run setup
uv sync --locked
```

Dashboard A với fixture để xem luồng SDE:

```powershell
uv run --locked python scripts/serve.py --port 8010
```

Mở `http://127.0.0.1:8010/`. Chế độ mặc định MOCK có nhãn trong API/workflow. Để chạy A+B Local trên Anvil, dùng [B handoff](B_HANDOFF.md); đây là luồng có thực thi EVM local.

Observer đọc Fuji thật, chạy độc lập với ví ký/B:

```powershell
$env:PACEVANT_OPERATOR_TOKEN = "YOUR_LOCAL_OPERATOR_TOKEN_AT_LEAST_24_CHARACTERS"
uv run --locked python scripts/serve.py --fuji-readonly --port 8012
```

Mở `http://127.0.0.1:8012/fuji-wallet`, nhập một địa chỉ công khai và operator token. Địa chỉ đọc có thể được nhập trực tiếp; kết nối ví chỉ giúp lấy địa chỉ. Operator token bảo vệ backend local, không phải private key của ví.

Preflight LFJ/Chainlink chỉ đọc dữ liệu:

```powershell
npm run lfj:preflight
uv run --locked python scripts/lfj_preflight.py --output data/lfj-preflight.json
```

## Kiểm chứng và giới hạn

[CI của merge main](https://github.com/ursuswh-metamorphic/PaceVant/actions/runs/44561694229) đã qua cho code đã ghép. Bộ kiểm tra gồm 59 tests A, 51 tests B (có 4 tests A+B), 37 Solidity tests, golden EIP-712, lint/format và secret scan. Hai ca LFJ Fuji-fork được chạy opt-in riêng; test chỉ gửi giao dịch vào Anvil loopback, không broadcast Fuji công khai.

Các lệnh kiểm tra:

```powershell
npm run check
uv run --locked python -m pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
npm run test:lfj:fork
```

Xem bằng chứng lịch sử trong [báo cáo LFJ](LFJ_FUJI_REPORT.md) và [oracle report](FUJI_AVALANCHE_INTEGRATION_REPORT.md). Artifact lịch sử giữ nguyên block/hash; freshness phải đọc lại khi dùng.

Đợt kiểm tra lại từ checkout `main` sạch cũng đạt đủ 59/51/37/2 tests, lint, golden signature và secret scan. Hai API khởi động mới từ main đã kiểm tra: workflow MOCK CONFIRMED; observer Fuji đọc live, xác thực và cache hoạt động. [Kết quả tích hợp main](../evidence/main-integration-validation.json) ghi commit được test, CI, block/provenance và evidence root của lượt fork mới. Database demo đang dùng không bị thay đổi bởi smoke test.

Những điều còn cần trước một vòng A→SDE→PDR→LFJ trên Fuji công khai:

1. **Định giá đúng asset:** LFJ faucet USDC không phải Circle USDC. Chưa có định giá độc lập được xác minh; SDE vẫn ESCALATE, không ký PDR. Đây là giới hạn đã biết, không thể khắc phục chỉ bằng cung cấp địa chỉ ví.
2. **Operator và funding:** cần cấu hình owner/attestor/relayer riêng biệt tại máy vận hành, kiểm tra test AVAX/LFJ test USDC, triển khai rồi đối chiếu manifest. Người dùng chưa cung cấp ví và chưa có deployment hiện tại được xác nhận trên Fuji.
3. **Độ trễ:** giữ nguyên TTL 30 giây và drift 3 block. Cần đo toàn luồng trên chain liên tục tạo block trước khi chấp nhận live execution.
4. **Cho phép broadcast riêng:** merge code/xóa nhánh không cấp phép gửi giao dịch testnet. Deploy/relayer vẫn mặc định dry-run/tắt broadcast.

Do đó, main tích hợp được các thành phần đã triển khai và có kiểm thử; không coi tests local/fork là bằng chứng hoàn thành live treasury. Không có giao dịch mainnet hay tiền thật trong quy trình này.
