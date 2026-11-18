# Fuji Observatory: ví, PolicyVault và oracle

PaceVant đọc trực tiếp Avalanche Fuji C-Chain `43113`. Đây là phần quan sát bổ sung cho kiến trúc A/B: số dư, oracle, PolicyVault, receipt và sự kiện thực thi có thể đối chiếu trên explorer. Trang chạy độc lập với B và không cần private key.

## Chạy demo nhanh

Cài Python 3.12, uv và chạy `uv sync --locked` ở root.

CLI đọc địa chỉ công khai:

```powershell
uv run --locked python scripts/fuji_wallet_read.py 0xYOUR_PUBLIC_ADDRESS --output data/fuji-snapshot.json
```

Web UI chỉ cần operator token dài ít nhất 24 ký tự, tự đặt trong terminal local:

```powershell
$env:PACEVANT_OPERATOR_TOKEN = "YOUR_LOCAL_OPERATOR_TOKEN_AT_LEAST_24_CHARACTERS"
uv run --locked python scripts/serve.py --fuji-readonly --port 8012
```

Mở [Fuji Observatory](http://127.0.0.1:8012/fuji-wallet). Nhập địa chỉ công khai và operator token. Có thể lấy địa chỉ qua Core/MetaMask trên Fuji. Mục mở rộng nhận thêm địa chỉ PolicyVault và tx hash.

Nếu lưu token trong `.env`, dùng `uv run --env-file .env --locked python scripts/serve.py --fuji-readonly --port 8012`. Observer không khởi tạo ControlPlane, B adapter, attestor hay mock workflow. Full ControlPlane ở mode FUJI cũng phục vụ cùng trang/API, dùng xác thực operator hiện có.

`GET /v1/fuji/wallet/{address}?vault=0x…&tx_hash=0x…` yêu cầu `Authorization: Bearer …`. Token chỉ ở input của trang hiện tại; không ghi localStorage, URL hay file JSON tải xuống. Server bind loopback.

CoinGecko là nguồn ngoài chain tùy chọn qua `PACEVANT_COINGECKO_DEMO_KEY`; key chỉ gửi đến API cố định của CoinGecko. Chưa cấu hình thì trả `NOT_CONFIGURED`.

## Dữ liệu thực sự đọc được

- Kiểm tra chain ID, pin block number/hash/timestamp; mọi balance, code và eth_call đọc tại block đã pin. Cuối lượt đọc kiểm tra lại hash tại cùng chiều cao.
- Native AVAX, Circle test USDC và WAVAX: base units nguyên, decimals, loại tài sản, địa chỉ token, bytecode hash. Token lỗi là `UNAVAILABLE`, không thay thành số dư 0. `snapshot_status` COMPLETE/PARTIAL chỉ mô tả ba số dư ví.
- Chainlink: description, decimals, round ID, raw answer, answeredInRound, thời điểm bắt đầu/cập nhật và heartbeat. Giá âm, round thiếu, timestamp tương lai bị đánh dấu `UNVERIFIED`.
- Witnet: pair ID, raw price, timestamp và ERC-2362 status. Status khác 200 không có giá hợp lệ.
- Pyth: feed ID, raw price, exponent, confidence interval, publish time và tuổi dữ liệu. Ngưỡng hiển thị 60 giây là cấu hình của observer.
- PolicyVault tùy chọn: owner, attestor, policy hash/version/expiry, active/paused, trần mỗi swap, dailySpent và ngân sách còn lại theo ngày UTC của block. Số dư Vault dùng đúng token trả về từ `usdc()/wavax()`, không dùng nhầm token mặc định của reader.
- Receipt tùy chọn: block thuộc chain quan sát, trạng thái thành công/revert/pending, recipient có khớp Vault, gas và phí thực trả. Khi tx gọi đúng Vault, giải mã `SwapExecuted` gồm nonce, policyHash, evidenceRoot, token/amount in/out và đọc `usedNonce(nonce)` ở block snapshot.
- Download JSON kèm source URLs, explorer links và `observation_hash` (Keccak-256 của RFC 8785 canonical JSON). Khi kiểm tra hash bỏ trường `observation_hash` và trường API bổ sung `cached` nếu có. Hash hỗ trợ phát hiện thay đổi artifact; không phải chữ ký hay bằng chứng đồng thuận.

## Registry và địa chỉ Fuji

| Nguồn | Hợp đồng / feed | Chu kỳ dùng để hiển thị |
|---|---|---|
| Chainlink AVAX/USD | `0x5498BB86BC934c8D34FDA08E81D444153d0D06aD` | heartbeat 600 giây |
| Chainlink USDC/USD | `0x97FE42a7E96640D932bbc0e1580c73E705A8EB73` | heartbeat 86400 giây |
| Witnet router, Price-AVAX/USD-6 | `0x1111AbA2164AcdC6D291b08DfB374280035E1111` | heartbeat tài liệu 24 giờ |
| Pyth AVAX/USD | `0x23f0e8FAeE7bbb405E7A7C3d60138FCfd43d7509` | observer yêu cầu tuổi ≤60 giây |
| Circle test USDC | `0x5425890298aed601595a70AB815c96711a31Bc65` | decimals 6 |
| WAVAX | `0xd00ae08403B9bbb9124bB305C09058E32C39A48c` | decimals 18 |

Pyth AVAX feed ID: `0x93da3352f9f1d105fdfe4971cfa80e9dd777bfc5d0f683ebb6e1294b92137bb7`.

Nguồn chính thức đã dùng:

- [Chainlink Fuji feed registry](https://reference-data-directory.vercel.app/feeds-avalanche-fuji-testnet.json), được dẫn từ [cấu hình Chainlink documentation](https://github.com/smartcontractkit/documentation/blob/main/src/features/data/chains.ts).
- [Chainlink: đọc data feeds](https://docs.chain.link/data-feeds/using-data-feeds).
- [Witnet: Avalanche feed addresses](https://docs.witnet.io/smart-contracts/witnet-data-feeds/addresses/avalanche-price-feeds).
- [Pyth EVM contract registry](https://github.com/pyth-network/pyth-crosschain/blob/main/contract_manager/src/store/contracts/EvmPriceFeedContracts.json) và [Hermes AVAX/USD feed lookup](https://hermes.pyth.network/v2/price_feeds?query=AVAX%2FUSD&asset_type=crypto).
- [Pyth Core pull interface](https://github.com/pyth-network/pyth-crosschain/blob/main/target_chains/ethereum/sdk/solidity/IPyth.sol): đọc giá lưu trong contract không tự kéo bản cập nhật mới.
- [Avalanche: Chronicle integration](https://build.avax.network/integrations/chronicle-data-feeds) liệt kê AVAX/USD Fuji `0x8b3328b27436263e0BfE7597a0D97B1BEE9cC576`. Đây là lựa chọn nghiên cứu tiếp, chưa có adapter trong bản này; cần xác minh quyền đọc theo caller, heartbeat và cơ chế cấp quyền trước khi chọn.
- [CoinGecko Demo API](https://docs.coingecko.com/demo/reference/simple-price).

## Hiện trạng và giới hạn

Xem [báo cáo kiểm chứng](FUJI_AVALANCHE_INTEGRATION_REPORT.md) và [snapshot live](../evidence/fuji-oracle-readonly-live.json). Đây là kết quả tại thời điểm ghi nhận; freshness sẽ thay đổi.

`WITHIN_HEARTBEAT` chỉ nói feed chưa vượt heartbeat công bố. Heartbeat USDC 24 giờ có thể quá chậm cho một giao dịch cụ thể. Không tự động ghép giá các nhà cung cấp, dùng giá cũ, hoặc thay giá thiếu bằng $1.

Mọi nguồn trả `usable_for_decisions=false`; snapshot trả `used_for_sde_or_attestation=false`. AVAX/USD và USDC/USD không chứng minh MockUSDC của Vault có giá đó. Muốn nối vào APPROVE/PDR phải đồng nhất token, nguồn giá, ngưỡng tuổi, block evidence và fork/execution state xuyên suốt A/B.

Kiểm tra ABI của Vault thành công chỉ xác nhận đọc được interface; bytecode hash cần đối chiếu deployment manifest tin cậy. Oracle proxy bytecode hash cũng không chứng minh implementation hay registry chưa đổi. Snapshot dựa vào một RPC, dùng pin-height/hash-recheck; chưa có xác minh state proof hoặc đồng thuận đa RPC.

HTTP reader có deadline 20 giây, giới hạn mỗi request/response, không redirect/proxy môi trường. Service dùng connection pool, tối đa hai lượt đọc đồng thời, 30 request/phút cho mỗi process và cache 5 giây giữ nguyên observed_at. Rate limit này phục vụ local demo; nhiều worker cần limiter dùng chung nếu triển khai lớn hơn.

## Kiểm tra

```powershell
uv run --locked python -m pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
npm run test:ab
```

Các unit test dùng HTTP transport giả lập cho trạng thái lỗi và dữ liệu cố định. Live artifact và dashboard dùng RPC Fuji thật. Chưa có địa chỉ deployment/receipt Fuji của PolicyVault hiện tại trong workspace nên chưa xác nhận swap thật hoặc nonce thực trên Fuji trong lần nâng cấp này.
