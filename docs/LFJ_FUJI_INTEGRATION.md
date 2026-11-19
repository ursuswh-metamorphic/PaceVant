# LFJ trên Fuji: triển khai, preflight và bằng chứng

**Trạng thái: adapter/builder/fork/monitor đã triển khai; chưa đạt Definition of Done live.** Không có deployment hay giao dịch LFJ nào của PaceVant được broadcast lên Fuji trong lần tích hợp này. Mọi địa chỉ Vault/adapter và receipt trong báo cáo fork chỉ tồn tại trên Anvil.

## Chạy phần đã được phép

```powershell
npm ci --ignore-scripts
npm run setup
uv sync --locked
npm run compile
npm run lfj:preflight
uv run --locked python scripts/lfj_preflight.py --output data/lfj-preflight-with-oracles.json
```

`lfj:preflight` chỉ đọc Fuji. Lệnh Python tiếp theo dùng lại reader Chainlink của A và pin oracle về đúng block của quote LFJ, tạo observation hash cho report. Tất cả giá trị vẫn có `used_for_sde_or_attestation=false`.

Nếu không có route/quote hợp lệ, preflight trả `NO_LIQUIDITY` hoặc lỗi xác minh cụ thể. Nếu quoter chọn tuyến khác V1 trực tiếp, trả `LFJ_UNSUPPORTED_ROUTE`; không đổi route âm thầm và không fallback mock.

## Hợp đồng và tuyến được xác minh

Registry chính thức: [LFJ Fuji](https://developers.lfj.gg/deployment-addresses/fuji) / [Markdown](https://developers.lfj.gg/deployment-addresses/fuji.md).

| Thành phần | Địa chỉ Fuji |
|---|---|
| LBRouter V2.2 | `0x18556DA13313f3532c54711497A8FedAC273220E` |
| LBQuoter V2.2 | `0x9A550a522BBaDFB69019b0432800Ed17855A51C3` |
| LFJ test USDC, decimals 6 | `0xB6076C93701D6a07266c31066B298AeC6dd65c2d` |
| WAVAX, decimals 18 | `0xd00ae08403B9bbb9124bB305C09058E32C39A48c` |
| Factory V1 | `0xF5c7d9733e5f53abCC1695820c4818C59B457C2C` |
| Pool V1 USDC/WAVAX | `0x9371619C8E2A487D57FB9F8E36Bcb0317Bff0529` |

Đã đọc chain ID, code hashes, decimals, token0/token1, factory registry, router/quoter bindings và reserve thực. Discovery cũng liệt kê các pool V2/V2.1/V2.2 và token balances. Balance tổng của LB pair không đủ để chứng minh thanh khoản thực thi tại bin hiện tại; quoter và fork execution mới kiểm chứng được tuyến chọn.

Quoter V2.2 thực sự chọn **Version.V1 = 0, binStep = 0** cho các lượng thử 0.1/1/10 LFJ test USDC. Adapter chỉ hỗ trợ tuyến này. Đã kiểm chứng LBRouter V2.2 gọi được pool V1 trên fork, không suy luận khả năng tương thích chỉ từ tên phiên bản.

ABI đối chiếu [ILBRouter](https://github.com/traderjoe-xyz/joe-v2/blob/main/src/interfaces/ILBRouter.sol) và [LBQuoter](https://github.com/traderjoe-xyz/joe-v2/blob/main/src/LBQuoter.sol). `contracts/src/interfaces/ILFJ.sol` là tập con ABI; enum/path giữ đúng thứ tự. Quoter được gọi off-chain; `adapter.quote()` tính lại cùng quote V1 từ reserve thực với công thức phí V1, không dùng quoter tốn gas trên chain.

## Trust boundary và dữ liệu

`PolicyVault` vẫn allowlist **adapter**, không cấp allowance trực tiếp cho LFJ router. Adapter có Vault/router/pool/token/path bất biến; chỉ caller và recipient là Vault được cấu hình. LFJ thực thi `minOut`; adapter và Vault kiểm tra delta thực. Cả allowance Vault→adapter và adapter→LFJ chỉ bằng amount cần dùng rồi trả về 0.

Giữ nguyên `ISwapAdapter`, selector/164-byte calldata, EIP-712 domain/Approval và calldataHash. Route bất biến được gắn qua adapter address, runtime hashes, quote artifact và evidence root. Không thêm AI Verification Agent.

Builder dùng quote LFJ theo block, đối chiếu quote adapter/quoter/reserves, tính minOut bằng số nguyên, lưu provenance và recheck block hash. Chain/relayer kiểm tra runtime hashes, cấu hình Vault/adapter, pool registry, policy, nonce, deadline, quote mới và evidence. Monitor đối chiếu đường đi token đúng Vault→adapter→pool và pool→Vault, hai tầng approval, SwapExecuted, nonce, allowance, gas/receipt và output so với minOut/simulation.

SDK nâng **1.1.0 → 1.2.0** để thêm `adapter_version=lfj-v1-fuji-v1`. DTO cũ và wire evidence schema 1.1 vẫn đọc được; không thay chữ ký PDR. A và B phải cùng nâng SDK: client 1.1 cũ sẽ từ chối enum LFJ mới. Schemas/OpenAPI và hai lockfiles đã cập nhật.

## Fork thực và stress

```powershell
npm run test:lfj:fork
```

Test opt-in đọc public Fuji, tạo Anvil loopback pinned source block; mọi write đi vào fork. Chỉ môi trường test mới tạo treasury contracts, dùng ba role ngẫu nhiên, cấp gas fork và impersonate **LFJ faucet owner trên fork** để mint token vào treasury thử nghiệm. Pool/token storage không bị sửa, không thêm thanh khoản giả vào pool. Đây không phải funding, deployment hay SDE approval trên Fuji công khai.

Test thực thi swap qua Vault→adapter→LFJ rồi dùng production simulator fork lại đúng pre-state để đối chiếu output. Chữ ký ở test contract dùng root sentinel có nhãn fork-only; evidence root cuối được tính sau mô phỏng, không được coi là PDR từ SDE cho receipt đó. Luồng binding root cuối/PDR thật vẫn do A+B regression và production relayer kiểm tra. Baseline phải chạy thật; receipt và quote phải khớp, nonce phải tiêu thụ và allowance phải sạch. Hai kịch bản giữ ID v1.1 `reserve_shift_mild/adverse` để tương thích mandate, nhưng dùng **một swap Vault hợp lệ được sắp trước giao dịch mục tiêu trên fork**, không gọi `setOutputPerUsdc` hay sửa reserve/storage.

Mục tiêu shift khoảng 20/200 bps, có kiểm tra shift đạt được. Đây là kịch bản thứ tự giao dịch từ cùng treasury, không phải tái hiện MEV thật. Không đủ balance/cap/budget hoặc setup không đạt mục tiêu thì trả `INCONCLUSIVE` và evidence không COMPLETE.

Hai mức funding fork-only 100/1000 test USDC kiểm chứng cả đường fail-closed và stress đủ vốn. Artifact gồm setup, traces, logs, delta, manifest và bundle JSON có content hashes để kiểm tra evidence root.

## Oracle và rào cản định giá

**LFJ faucet USDC không phải Circle test USDC, cũng không có bằng chứng redeem/peg theo USDC/USD trong lần kiểm tra này.** LFJ docs còn phân biệt token faucet Avalanche với token của LFJ. Tên `USDC`/decimals 6 không chứng minh định giá.

Hai Chainlink feeds được đọc thật và gắn block với quote trong `lfj-fuji-oracle-preflight.json`. Chưa thể dùng chúng để định giá LFJ test USDC. `WITHIN_HEARTBEAT` cũng không đồng nghĩa đáp ứng ngưỡng risk 60 giây.

A ở mode FUJI không nhận file `TRUSTED_TEST_ORACLE` để cấp quyền. EconomicRiskEvaluator cũng trả `INCONCLUSIVE` với `ORACLE_TOKEN_IDENTITY_MISMATCH` cho adapter LFJ ngay cả khi được đưa một snapshot test-price. SDE ESCALATE và không ký PDR. Không có công tắc cho phép coi LFJ token là $1.

Muốn bỏ rào cản này phải có chính sách định giá phù hợp với đúng asset và nguồn độc lập đã xác minh, hoặc một thay đổi mandate/model được đánh giá riêng về ý nghĩa testnet reference pricing. Đổi label mock thành oracle, dùng DEX quote của cùng pool làm nguồn USD độc lập, hoặc tăng độ cũ cho phép không giải quyết được định danh.

## Deployment và execution sau này

```powershell
npm run deploy:fuji -- --dry-run
```

Lệnh này chưa deploy. Preflight hiện báo role/funding chưa cấu hình khi chưa có owner/attestor/relayer. B không tạo hay tải private key attestor Fuji của A.

Chỉ sau khi người dùng cho phép một bước broadcast cụ thể, mới cấu hình `B_FUJI_BROADCAST_AUTHORIZED=true` và dùng `--broadcast`. Việc bật biến này không giải quyết oracle/SDE; deployment hạ tầng có thể được cấp phép riêng với việc execute.

```powershell
# Chỉ chạy sau khi được phép deploy hạ tầng Fuji và kiểm tra ví test/route.
npm run deploy:fuji -- --broadcast
# Có thể thêm --fund-amount N để chuyển đúng N base units LFJ test USDC từ owner.
```

Python deploy tạo Vault với đúng hai token LFJ, tạo adapter tuyến verified, allowlist adapter và cấu hình policy. Giữ cap PoC 500 USDC/swap và 1000 USDC/ngày, slippage 100 bps, TTL approval 30 giây; lưu deployment manifest/tx hashes và mandate trong data dir. Không mint token live; owner phải có LFJ test USDC thật để fund. Manifest đã tồn tại sẽ không bị ghi đè. `Deploy.s.sol` mock cũ chỉ cho phép chain local 31337.

Sau khi có build/evidence và **Signed PDR do A SDE cấp**, CLI kiểm tra request mà chưa gửi:

```powershell
npm run lfj:execute -- --request-file data/execution-request.json --dry-run
```

Dry-run kiểm tra build/evidence/PDR, policy/quote/nonce/freshness và eth_estimateGas; không ký tx, không ghi submissions journal và không gửi. `--broadcast` cùng authorization setting mới gửi qua relayer có journal/idempotency hiện có. Không có script ký PDR Fuji thay SDE.

**Hiện chưa thể đến bước PDR hợp lệ vì định giá LFJ test USDC chưa xác minh.** Role/funding cũng chưa cấu hình trong preflight. Độ trễ fork và giới hạn 3-block drift/30-second TTL vẫn giữ nguyên; cần đo tiếp trên hạ tầng Fuji thực trước khi tuyên bố chạy tự động được trong cửa sổ đó.

## Bằng chứng và kiểm tra

- [Preflight LFJ thật](../evidence/lfj-fuji-preflight.json).
- [LFJ + Chainlink cùng block](../evidence/lfj-fuji-oracle-preflight.json).
- [Fork đủ vốn stress](../evidence/lfj-fuji-fork-validation.json).
- [Fork thiếu ngân sách stress, INCONCLUSIVE](../evidence/lfj-fuji-fork-validation-insufficient-stress-budget.json).
- [Báo cáo bàn giao](LFJ_FUJI_REPORT.md).

```powershell
npm run check
uv run --locked python -m pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
npm run test:lfj:fork
```

CI mặc định chạy cả A, B và A+B qua `test:python`; live-fork test opt-in để lỗi hạ tầng/biến động thanh khoản không bị nhầm với unit-test determinism. Workflow có thêm manual input `fuji_fork` để chạy job fork và lưu artifact mới của lần CI đó. Test doubles ở unit tests được ghi nhãn rõ; Local MockSwapAdapter vẫn giữ cho regression. Không có mainnet, production funds, private key hay fake Fuji receipt trong evidence.
