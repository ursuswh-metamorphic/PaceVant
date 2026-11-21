# PaceVant — Hiện trạng MVP public Avalanche Fuji

Cập nhật ngày 21/11/2026. Đây là tài liệu hiện hành; [bản review trước nghiệm thu](audit/system-review-before-public-acceptance-20261121.md) chỉ giữ làm lịch sử. Các kết quả fork cũ không được dùng thay bằng chứng giao dịch public.

## Phạm vi thực tế

Website `https://pacevant.live` đã chuyển sang **REAL_FUJI_EXECUTION**, chain ID **43113**. Backend gọi model thật, đọc policy/số dư/oracle/DEX thật, chạy simulation trước khi ký; bước cuối gửi giao dịch đã ký lên RPC Fuji công khai. Simulation vẫn cần thiết để đo tác động và kiểm tra chữ ký, nhưng không phải nơi settle giao dịch cuối.

MVP chỉ có hai nghiệp vụ: **USDC_PAYMENT** và **SWAP_EXACT_IN**. Lending, staking, LP, bridge, multihop, arbitrary approval/call và customer gas billing không được bật. Các tên nội bộ TOKEN_PAYMENT/TOKEN_SWAP ánh xạ hai nghiệp vụ này.

## Contract và ba ví hiện có

| Thành phần | Địa chỉ public Fuji |
|---|---|
| PolicyVaultMVP mới | `0x70e1395F959dba530cF4A53B060c809b715bB6d5` |
| LFJSwapAdapterV3 mới | `0x05522FFAfe20CAb88Ce223E0E84031d98381DeaF` |
| Circle test USDC | `0x5425890298aed601595a70ab815c96711a31bc65` |
| WAVAX Fuji | `0xd00ae08403b9bbb9124bb305c09058e32c39a48c` |
| Owner | `0x607bd883bd3621378812CF5B4B8dDcCFAeBbab1b` |
| Attestor | `0x5704fA0FF7CBEd213F622c99aC6F9d6E5cbF2989` |
| Relayer trả gas | `0x761B1FFB7AA70C7A946D3970A25F5a3859dA328C` |

Đã deploy từ source Solidity hiện hành, xác minh runtime code hash, cấu hình policy/session/payees và chuyển **1 USDC test từ Owner vào Vault**. Tổng 13 giao dịch setup có receipt status 1; phí thực trả `1225174720 wei AVAX`. Đây là token và gas testnet, không phải tài sản mainnet. Contracts bất biến cũ V2 vẫn giữ nguyên, không bị ghi đè hay rút tiền tự động.

Payment cố định **0,01 USDC/lần**, chuyển từ Vault tới một trong ba EOA trên; server lần lượt cấp recipient trong ba ví đã được Owner duyệt. Đây là luồng Owner cấp vốn → Vault → EOA nhận tiền; không có daemon tự rút USDC từ bất kỳ EOA nào để quay vòng vốn. Swap cố định **0,000001 USDC/lần**, lấy WAVAX về Vault qua LFJ V1. Trình duyệt không chọn địa chỉ, amount hay calldata tùy ý.

`deployments/mvp-fuji.json` được Owner ký, chứa ba vai trò, hai token, contract hashes và session. Các giá `local_*` trong schema chỉ phục vụ LOCAL_TEST; chế độ public đọc Chainlink thật. Tên ABI helper `MockUSDC`/`MockWAVAX` được dùng để gọi interface ERC-20 tại địa chỉ Circle USDC/WAVAX public; không deploy token mock cho luồng này.

## Kết quả chạy thật

Payment qua UI local đã CONFIRMED: [`0x8f3c1b8f045bc80eeb49df2a85f45feb2fea07957402220ab60cd011a5b02642`](https://testnet.snowtrace.io/tx/0x8f3c1b8f045bc80eeb49df2a85f45feb2fea07957402220ab60cd011a5b02642), block `61405956`; Owner nhận đúng `10000` USDC base units. Relayer giảm đúng `54720000` wei AVAX phí gas.

Payment từ `pacevant.live` cũng đã CONFIRMED: [`0x10f6a04e22179f4186459e3738c61597048e9b2aac724c01347ba306f4470b8c`](https://testnet.snowtrace.io/tx/0x10f6a04e22179f4186459e3738c61597048e9b2aac724c01347ba306f4470b8c), block `61407202`; Attestor nhận đúng `10000` USDC base units. Phí gas thật `43783680` wei AVAX. Worker chạy `519.941612` giây, gồm thời gian đợi round Chainlink mới; cùng job tự tiếp tục, không POST/gửi lại.

Swap từ `pacevant.live` đã CONFIRMED: [`0xa708f44e355b6926c02693282f8ca6514fd043199ae8d23d3a031d64f82e4b2d`](https://testnet.snowtrace.io/tx/0xa708f44e355b6926c02693282f8ca6514fd043199ae8d23d3a031d64f82e4b2d), block `61406870`; Vault giảm `1` USDC base unit và tăng `13266545691051` wei WAVAX. Phí gas thật `77911360` wei AVAX. Worker chạy `123.322466` giây, chưa tính thời gian chờ oracle trước khi bấm.

Phí ở trên là `gasUsed × effectiveGasPrice` từ public receipt, đối chiếu mức giảm AVAX của Relayer giữa hai block. Số dư USDC/WAVAX đọc trực tiếp ở block trước và sau giao dịch, không lấy số UI làm bằng chứng settlement. Sau ba giao dịch runtime: Vault còn **0,979999 USDC + 0,000013266545691051 WAVAX**; Owner **39,010004 USDC**, Attestor **20,01 USDC**, Relayer **20 USDC**. Đây là snapshot tại block kiểm tra trong evidence, sẽ thay đổi sau các lần demo tiếp theo. [Bằng chứng deploy](audit/mvp-public-deployment-20261121.json), [đối chiếu public settlement](audit/public-fuji-live-acceptance-20261121.json).

Guard đã chạy với policy public thật và bị từ chối `PAYEE_NOT_ALLOWED` trước Attestation, không có transaction và không tốn execution gas. **Sáu lựa chọn mô phỏng tấn công trên UI hiện vẫn là preview**, có ghi rõ khi mở; chúng không tạo backend job và không phải sáu cuộc tấn công đã được thực thi. Không tuyên bố chúng đã chạy live.

## Pipeline và kết nối dữ liệu

Owner authority → AI proposal → trusted builder → EVM simulation → Economic Risk → ITAG → Z3/Phi proof → SDE → Attestor → exact signed preflight → Relayer/PolicyVault → canonical receipt/reconciliation.

Mỗi stage được persist từ backend thực. Graph và panel đọc timeline/intent/effects/proof/outcome này; không có timer tự chuyển sang approved/confirmed. F5 khôi phục job theo session/idempotency key và tiếp tục GET polling; không tự gửi giao dịch lần nữa. Receipt public mới mở link Snowtrace; replay được gắn nhãn riêng.

Prompt, amount và lựa chọn scenario cố định là đầu vào demo có chủ đích; số dư, quote, effects, verdict, proof, chữ ký và receipt không được thay bằng dữ liệu mẫu để cho pass.

## Module/source hiện hành

| Module | Trách nhiệm và trạng thái |
|---|---|
| `api/judge.py`, `config/judge.py`, `operations/judge_serve.py` | Public UI API, anonymous session/quota, explicit public activation, signed manifest; cấm Owner/deployer key trong server. Default chưa cấu hình vẫn là fork; VPS đã được bật public riêng. |
| `modules/workflows/judge.py` | Hàng đợi một job, SQLite history/idempotency, cấp recipient phía server, worker timeout, khôi phục giao diện. Public worker chỉ nhận Attestor/Relayer và model credentials. |
| `operations/public_treasury.py`, `judge_worker.py` | Compose public engine với shared execution/control DB; chờ oracle thật, publish đúng workflow, thu thời gian/token usage. Không deploy/fund tự động trong request. |
| `operations/judge_source.py` | Xác minh code identity và đọc số dư/policy/Chainlink public; source lỗi trả unavailable, không lấy cached fork làm số dư public. |
| `modules/planning/treasury.py` | Model thật đề xuất có cấu trúc, ràng buộc exact operation/token/recipient/amount. Proposal không cấp authority. |
| `modules/alignment/`, `modules/temporal/` | Task Shield, authenticated intent/provenance, interception, ITAG history/graph/citation/semantic checks. Sai schema, thiếu evidence hoặc provider lỗi đều không được ký. ITAG DeepSeek dùng JSON object output theo API chính thức; validation vẫn giữ nguyên. |
| `modules/oracle/chainlink.py` | Giá, round, decimals, code, freshness và đúng asset từ feeds Fuji; không sửa `updatedAt`. |
| `modules/risk/operations.py` | Đo effects, payee receipt, price impact, loss/exposure/allowance/gas. Payment principal tách khỏi trading loss. |
| `modules/proof/`, `packages/contracts-api/treasury_contracts/proof_v3.py` | Shared Z3 solver, rational units, operation-specific constraints/Phi; không certificate hardcode. |
| `modules/decision/service.py`, `modules/signing/service.py` | SDE yêu cầu tất cả gate; bind hashes, tái kiểm tra state/proof trước ký EIP-712, durable sign-once. |
| `modules/workflows/treasury.py` | Coordinator đầy đủ, persist rejection/recovery, revalidation, final preflight, public relay và reconcile. |
| `modules/execution/mvp.py`, `v3/context.py`, `v3/builder.py` | Signed registry, ba EOA, exact assets/roles/code/session/policy; canonical calldata/nonce/min-output và reference checks. |
| `modules/execution/v3/simulation.py` | Native Anvil chỉ để simulation/preflight; final signed preflight không sửa storage. Public keys không được truyền cho Anvil subprocess. |
| `modules/execution/dex/lfj.py`, `v3/relay.py` | Official LFJ quoter/pair/reserves kiểm tra route; relay có atomic journal trước broadcast, gas guard, canonical receipts/effects. |
| `modules/gas_credit/system.py`, `modules/persistence/` | Sổ phí hệ thống, reservation/journal, idempotency/history và đối soát phí; không reset nonce/budget khi refresh hay restart. |
| `PolicyVaultMVP.sol`, `PolicyVaultV3.sol`, `LFJSwapAdapterV3.sol` | Contract mới đã deploy public; kiểm chữ ký/session/policy/Phi/receipt/allowance; chỉ hai operation được mở trong MVP. |
| `modules/workflows/readiness.py`, `monitoring/` | Readiness và reconciliation; unknown/reorg không biến thành success. |
| `frontend/src/app/` | React/TypeScript/Vite, Tailwind/Radix/shadcn, Motion, Lucide, React Flow, TanStack Query; tiếng Việt mặc định, English, graph/panels và history từ API thật. Nginx phục vụ static build. |
| `modules/workflows/autonomy.py`, `planning/rebalance.py` | Code optional; không tự chạy tài sản trong public judge mode. |
| `api/app.py`, `api/mvp.py`, legacy portfolio/experience/relaying | Operator/compatibility code còn trong repo; Nginx public không mở admin/debug/legacy mutation. Không phải luồng Judge hiện hành. |
| `attack_lab.py`, local/fork fixture tools, research V3 | Giữ để kiểm thử/nghiên cứu; không được dùng làm bằng chứng public execution. Scripted model fixtures chỉ trong chế độ test được gọi rõ ràng. |

## Economic risk và quyền hạn

Không nới gate để cho demo pass: max relative loss **3%**, oracle bounds **1%**, max exposure **25%**, oracle signing age **300 giây**; exact receipt/allowance/policy/session/spend/gas checks vẫn bắt buộc. Các timestamp/giá/balance thật được đọc lại trước ký và relay.

Policy payment: tối đa **0,01 USDC/giao dịch**, tổng **1 USDC** theo budget session/day đã cấu hình; whitelist đúng ba EOA, tối đa **500 actions**. Session và policy hiện hết hạn tại epoch **1795832966**. Owner phải gia hạn/cấp vốn khi cần; serving process không có Owner key để tự nâng quyền.

USDC bị trừ ở Vault; AVAX gas bị trừ ở Relayer. Model token usage được đo từ provider responses, nhưng chưa có hóa đơn API nên không gọi đó là chi phí USD thực trả. Phí Fuji rất nhỏ trong mẫu hiện tại; không lấy mức này làm cam kết giá gas tương lai hay phí mainnet.

## VPS và cập nhật

Native Ubuntu: source `/opt/pacevant-source`, release `/opt/pacevant/releases/<git-sha>`, symlink `/opt/pacevant/current`, systemd `pacevant-judge`, Nginx/TLS trên `pacevant.live`. Không Docker/Node production server. Persistent data public `/var/lib/pacevant/judge-public`, khác fork database cũ. Environment riêng `/etc/pacevant/judge.env`, quyền `0640 root:pacevant`; chỉ hai serving keys và model credentials.

Nhánh deploy **develop**, cập nhật bằng `pacevant-update` theo [hướng dẫn VPS](../VPS_DEPLOYMENT.md). Chờ job hiện tại kết thúc trước khi update/restart; không tự resubmit job bị gián đoạn. Không tự push sang main.

## Khả dụng và điểm cần biết khi demo

- Public Chainlink Fuji có khoảng trống giữa các round dài hơn signing age 300 giây. Runtime có thể **chờ tối đa 720 giây** cho round mới; timeout job **900 giây**. UI báo chờ giá; tuyệt đối không sửa timestamp hay dùng giá giả để ép chạy. Vì vậy không cam kết bất kỳ thời điểm nào cũng hoàn tất trong ba phút.
- Giới hạn một job đồng thời, 6 runs/visitor/ngày, 6 starts/IP/giờ, 30 runs toàn hệ thống/ngày. Những giới hạn này giảm phí và bảo vệ tài nguyên, có thể khiến người tiếp theo phải đợi.
- Model/RPC/DEX/oracle lỗi hoặc market vi phạm policy sẽ dừng thật. Phiên đã ký nhưng chưa rõ receipt được giữ recovery/UNKNOWN, không tự gửi giao dịch khác.
- Reverse WAVAX→USDC có code route nhưng market/reference/quoter có thể chặn. UI live swap hiện chỉ dùng forward USDC→WAVAX; không mở protocol khác.
- Chỉ nạp 1 USDC test để giữ phạm vi tiêu tiền nhỏ; cần theo dõi số dư Vault, AVAX Relayer, action/spend budget và expiry khi chạy lâu dài. systemd restart không thay thế những điều kiện này.

## Sửa lỗi và kiểm chứng trong đợt chuyển public

Đã sửa checksum address khi đọc public source; lọc progress khỏi các reconciliation của job khác; retry ngắn atomic file replacement trên Windows; unique request key cho shared public ledger; harness chấp nhận workflow chưa được tạo ở giai đoạn đầu; hiển thị phí AVAX thật; giảm các full-context RPC reads trùng lặp trước workflow nhưng vẫn giữ full verification trong engine.

Một lần swap trước sửa đã dừng tại ITAG vì đầu ra semantic không hợp lệ, trước ký và không tốn execution gas. Không đổi verdict thành PASS. Đã thêm chế độ JSON output của DeepSeek chỉ cho ITAG object request, giữ các API trả array của Task Shield và toàn bộ schema/citation checks. Các lần thất bại được giữ trong evidence, không ghi thành giao dịch thành công.

Đã chạy 40 kiểm tra tập trung ở public signer filtering/activation, Judge API/session/idempotency, DeepSeek wire format và ITAG catalog/negative cases: tất cả đạt. Public source/code hashes/receipt và historical balances được kiểm tra độc lập bằng RPC. Browser payment và swap trên domain thật đều PASS: mỗi lượt đúng một POST, F5 khi đang chạy và sau hoàn tất, prompt/intent thật trong panel, đủ 12 module, link public receipt, không có browser error và không tràn ngang ở 1440×900/390×844. Payment còn kiểm tra được trạng thái chờ oracle rồi tự tiếp tục khi giá cập nhật. Không dùng screenshot trong lượt này.

Một lần payment acceptance trên VPS bị gián đoạn trong lúc chuyển release, trước khi có workflow/transaction, trả UNAVAILABLE; không ghi thành success và không tự chạy lại. Runbook yêu cầu chờ job kết thúc trước update. Hai lần payment/swap public CONFIRMED mới là bằng chứng chuyển token/gas, không phải kết quả test fixture. Chưa thực hiện multi-day soak hay cam kết uptime tuyệt đối.

Xem công cụ read-only `tools/quality/verify_public_judge_settlement.py` để kiểm tra lại receipt/code hash/biến động số dư, và `tools/operations/deploy_mvp_public_fuji.py` cho deployment đã journal. Không chạy lại deployment để demo; phục vụ bằng manifest đã ký hiện có.
