# Chạy demo V2.1 trên local và Avalanche Fuji

> **DOC STATUS: HISTORICAL_RUNBOOK - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](../AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](../README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

Live update 2026-11-20: [Circle / Chainlink / full Fuji demo](FUJI_LIVE_END_TO_END.md). Earlier faucet-USDC blockers and controlled/mock descriptions below belong to their historical profiles.


**Cập nhật toolchain:** backend đã chuyển sang Python gọi native Forge/Anvil trực tiếp. Xem [setup và deploy không Node.js](../deployment/PYTHON_BACKEND_RENDER_VPS.md) cho lệnh `uv run ...`, Docker và Render/VPS. Các alias `npm run` trong tài liệu này vẫn dùng được khi có Node để phát triển; Node không còn là dependency của backend container.

Tài liệu vận hành chính cho phiên bản V2.1. Các lệnh `treasury:*` khởi động **một FastAPI với workflow và execution modules**, qua SDE, proof engine, attestor và PolicyVault; không có đường ký riêng cho demo. Trạng thái kiểm tra môi trường hiện tại: [ENVIRONMENT_STATUS.md](ENVIRONMENT_STATUS.md). Chưa có deployment V2.1 hoặc giao dịch Fuji được thực hiện trong lần triển khai mã này.

**Cập nhật máy hiện tại:** theo ủy quyền tự điền của người dùng, khóa attestor và sáu hạn mức demo đã được điền cục bộ; doctor báo `configuration_ready=true`. Không còn biến bắt buộc cần lấy tài khoản ngoài để điền. Các hướng dẫn nhập biến bên dưới áp dụng khi thiết lập trên máy mới hoặc đổi policy. Xem [luồng xử lý và lý do có Node.js](../CURRENT_SYSTEM_FLOW.md) để phân biệt ví, private key, Python API và tooling npm.

## 1. Bạn cần chuẩn bị gì?

| Thành phần | Yêu cầu |
|---|---|
| Máy chạy | Python 3.12, `uv`, Git, native Foundry v1.7.1; hai terminal khi demo Fuji |
| Dependencies | `uv sync --locked`, `uv run --locked python tools/contracts/bootstrap.py` tại root |
| RPC | Fuji C-Chain, chain ID **43113**, có thể đọc trạng thái block gần đây và phục vụ Anvil fork; outbound HTTPS được phép |
| Owner | Ví test riêng, private key trong `B_FUJI_OWNER_PRIVATE_KEY`; trả phí deploy/cấu hình/gia hạn |
| Relayer | Ví test khác owner, private key trong `B_FUJI_RELAYER_PRIVATE_KEY`; trả phí swap |
| Attestor | Ví test thứ ba, `PACEVANT_ATTESTOR_KEY`; ký EIP-712 offline, không cần AVAX để ký |
| Phí | **Test AVAX trên Fuji C-Chain** cho owner và relayer; số dư dương không đảm bảo đủ cho toàn bộ deployment |
| Rủi ro | Owner chọn sáu thông số ở mục 3 và xác nhận cấu hình; không dùng fixture `TEST_ONLY` cho Fuji |

Network chính thức: RPC `https://api.avax-test.network/ext/bc/C/rpc`, currency AVAX, explorer `https://explorer-test.avax.network/c-chain`. Xem [Avalanche Primary Network endpoints](https://build.avax.network/docs/primary-network). Lấy test AVAX tại [Avalanche faucet](https://build.avax.network/console/primary-network/faucet); điều kiện cấp tại faucet có thể thay đổi. Có thể dùng ví trình duyệt để nhận/chuyển test AVAX, nhưng API/demo không cần kết nối MetaMask.

Runbook này dùng profile mock với **MockUSDC, MockWAVAX, MockSwapAdapter và PolicyVault mới**. Ví dụ này mint token thử khi deploy. Planner chọn real Groq hoặc offline rules. Đường LFJ dùng pool Fuji thật trên fork và có điều kiện định giá riêng. [Groq configuration](../integrations/GROQ_PLANNER_AND_ENV.md), [Fuji/LFJ integration](../integrations/FUJI_LFJ_V2_1.md).

## 2. Kiểm tra local trước

Chạy tại root repository, PowerShell hoặc shell tương đương:

```powershell
uv sync --locked
uv run --locked python tools/contracts/bootstrap.py
uv run --locked treasury init-env
uv run --locked treasury local --once
```

Native Foundry chạy trực tiếp, không cần npm. Các npm aliases bên dưới là lựa chọn tương thích cho máy development; lệnh chuẩn là `uv run treasury ...`. `treasury:init` giữ nguyên biến có sẵn, thêm biến thiếu, sinh ba service token còn trống. Lệnh này không sinh attestor trừ khi truyền cờ rõ ràng.

Smoke tự compile, khởi động hoặc tái dùng Anvil loopback chain 31337, deploy V2 nếu cần, tạo mandate/oracle, chạy một backend và một workflow `Buy WAVAX with 200 USDC`. Kết quả mong đợi: `CONFIRMED`, tx hash thật của Anvil và đường dẫn report. Sau đó dừng các tiến trình mà lệnh đã tạo. Không dùng khóa Fuji hoặc gửi giao dịch Fuji.

Để giữ dashboard local chạy:

```powershell
uv run --locked treasury local
```

Mở `http://127.0.0.1:8000`, nhập **giá trị `PACEVANT_OPERATOR_TOKEN` từ `.env` trên máy** vào ô credential. Token chỉ giữ trong bộ nhớ tab. B chạy tại `http://127.0.0.1:8001`; không nhập `B_API_KEY` vào dashboard. Đổi `TREASURY_A_PORT`/`TREASURY_B_PORT` nếu cổng bận. Ctrl+C dừng stack; một Anvil đã chạy từ trước được giữ lại. Anvil do lệnh tạo là ephemeral; khi nó dừng, lịch sử chain mất và lần chạy sau sẽ deploy local mới. Các file audit cũ vẫn được giữ.

Các lệnh `npm run local`, `deploy:local`, `demo`, `dev:*` và `b:*` là công cụ B/legacy, **không phải lệnh chạy toàn bộ V2.1**.

## 3. Điền `.env` cho Fuji

Đã có placeholder trong `.env` thực tế, không cần copy đè file. Dùng `uv run --locked treasury init-env` để thêm biến thiếu trên máy khác.

| Biến bắt buộc | Đơn vị / ý nghĩa |
|---|---|
| `PACEVANT_ATTESTOR_KEY` | Private key ví test riêng cho A, khác owner và relayer |
| `TREASURY_MAX_RELATIVE_LOSS_BPS` | Mức lỗ tương đối tối đa; số nguyên bps, 100 bps = 1% |
| `TREASURY_MAX_FIXED_LOSS_USD` | Phần lỗ USD cố định bổ sung; nhập số thập phân, có thể `0` |
| `TREASURY_ORACLE_BAND_BPS` | Biên giá quanh oracle trong mô hình proof, số nguyên bps |
| `TREASURY_POSTCONDITION_TOLERANCE_BPS` | Dung sai compile Phi, số nguyên bps; có thể bị giảm về 0 nếu proof yêu cầu |
| `TREASURY_SESSION_RISK_LIMIT_USD` | Trần **certified reservation** cho một phiên, USD dương |
| `TREASURY_GLOBAL_DAILY_RISK_LIMIT_USD` | Trần reservation tổng các phiên trong ngày UTC, USD dương |
| `TREASURY_OWNER_POLICY_APPROVED` | Chuyển từ `false` sang `true` **sau khi bạn xem và chọn các thông số trên** |

Các giá trị USD nhận tối đa 8 chữ số thập phân, không dùng dấu phẩy hoặc ký pháp khoa học. Reservation là upper bound lỗ trong modeled price domain, thường lớn hơn lỗ thực tế; không phải số tiền được phép chuyển cho agent. Band rộng hoặc giới hạn lỗ quá chặt có thể khiến một swap nominal fair vẫn bị proof từ chối.

Nếu muốn tự sinh khóa attestor mới ngay trên máy:

```powershell
uv run --locked treasury init-env --generate-attestor
```

Lệnh chỉ sinh khi ô khóa còn trống; ghi khóa vào `.env`, không in khóa. `B_FUJI_ATTESTOR_ADDRESS` được suy ra tự động nếu còn trống. Nếu tự điền private key, chạy lại `uv run --locked treasury init-env` để suy ra địa chỉ. Nếu đổi khóa mà public address đã có, bạn phải cập nhật public address cho khớp; doctor sẽ chặn trường hợp lệch. Không gửi private key/token qua chat.

Các biến đã có hoặc có giá trị mặc định cần xem lại:

| Biến | Mặc định / cách dùng |
|---|---|
| `B_FUJI_RPC_URL` | `${FUJI_RPC_URL}`; thay bằng RPC riêng nếu public RPC giới hạn truy cập/fork |
| `B_FUJI_OWNER_PRIVATE_KEY` | `${DEPLOYER_PRIVATE_KEY}`; khóa owner chỉ cấp cho tiến trình deploy/cấu hình |
| `B_FUJI_RELAYER_PRIVATE_KEY` | `${AGENT_PRIVATE_KEY}`; khóa relayer chỉ cấp cho B |
| `FUJI_TEST_WALLETS_ONLY` | Phải `true` để công cụ dùng các ví Fuji |
| `TREASURY_MAX_WAVAX_PER_SWAP` | `0` = khóa WAVAX→USDC. Owner nhập số WAVAX, tối đa 18 số lẻ, nếu muốn demo chiều bán |
| `TREASURY_SESSION_DURATION_SECONDS` | `3600`; hết hạn phải owner gia hạn, không tự làm mới |
| `TREASURY_MAX_ORACLE_AGE_SECONDS` | `60`; proof kiểm tra tuổi oracle, A vẫn giữ kiểm tra freshness 60 giây |
| `TREASURY_ORACLE_USDC_USD` / `TREASURY_ORACLE_WAVAX_USD` | `1` / `20`, **giá nominal của mock demo**, không phải giá thị trường |
| `TREASURY_FUJI_MAX_BLOCK_DRIFT` | `30` block; local `3`. Phù hợp thời gian fork/proof trên chain nhanh; tăng giá trị chấp nhận evidence cũ hơn theo block, không bỏ kiểm tra freshness hoặc deadline |
| `PACEVANT_FUJI_VERIFICATION_RPC` | Endpoint Avalanche chính thức, A dùng để đối chiếu độc lập block/hash/code từ B; có thể đổi HTTPS RPC đáng tin cậy |
| `TREASURY_FUJI_CONFIRMATIONS` | `2`; chưa đủ confirmation thì giữ pending |
| `TREASURY_FUJI_DEPLOYMENT_FILE` | `deployments/treasury-fuji-v2.json`, riêng với manifest V1 |
| `TREASURY_FUJI_DATA_DIR` | `.execution-data-fuji-v2`, raw-tx journal/artifacts của B |
| `TREASURY_CONTROL_DATA_DIR` | `.control-data-v2`; dữ liệu Fuji ở thư mục con `fuji` |

`B_API_KEY`, `PACEVANT_OPERATOR_TOKEN`, `PACEVANT_INTERNAL_TOKEN` phải khác nhau, mỗi token ít nhất 24 ký tự; init tự sinh giá trị thiếu. `PACEVANT_MODE=MOCK` được giữ để lệnh legacy không vô tình ký Fuji. **Các lệnh `treasury:* --network fuji` tự truyền profile FUJI cho A/B**, không cần sửa hàng loạt biến `PACEVANT_*` hoặc `B_MODE`. V2 lấy đường dẫn `TREASURY_*_DEPLOYMENT_FILE`, không dùng `B_FUJI_DEPLOYMENT_FILE` cũ.

## 4. Deploy V2 mới trên Fuji

```powershell
uv run --locked treasury doctor --network fuji --live
```

Doctor chỉ đọc: kiểm tra tên biến, tách vai trò, chain 43113, số dư AVAX công khai và một historical state read. Exit code 2 nghĩa là chưa sẵn sàng; `NOT_DEPLOYED` trước deployment là bình thường. Nó không in private key/token hoặc full RPC URL có API credential. Kiểm tra này chưa đảm bảo mọi RPC method mà Anvil fork cần sẽ chạy; lỗi rate limit/archive vẫn phải xử lý bằng RPC phù hợp.

Khi doctor cho biết cấu hình sẵn sàng và hai ví đủ test AVAX:

```powershell
uv run --locked treasury deploy --network fuji
```

**Lệnh này gửi giao dịch testnet có phí**: triển khai bốn hợp đồng, cấu hình owner/adapter/registry/proof/session và cấp mock token. Công cụ từ chối `TEST_ONLY` trên chain 43113 và từ chối ghi đè manifest đã tồn tại. Nếu deployment trước bị gián đoạn, giữ manifest/audit để kiểm tra receipt; không xóa file rồi retry mù quáng. Muốn deployment mới độc lập, đặt đường dẫn `TREASURY_FUJI_DEPLOYMENT_FILE` mới và data dir mới; không tái sử dụng địa chỉ immutable V1.

Output/manifest chứa địa chỉ thật, chain ID, code hashes, session ID và transaction/block. Công cụ đọc lại code của cả bốn hợp đồng, trạng thái policy/registry/session, kiểm tra signer và tạo `mandate.json`/`oracle.json` đúng vault. Có thể tái tạo hai file này bằng `uv run --locked treasury prepare --network fuji`; không sửa tay field proof hoặc session để vượt gate.

## 5. Chạy demo Fuji

Terminal 1, giữ chạy trong suốt demo:

```powershell
uv run --locked treasury serve --network fuji
```

Lệnh chạy A, B và heartbeat oracle mỗi 5 giây. Heartbeat xác minh chain/head còn mới trước khi ghi timestamp; lỗi RPC giữ timestamp cũ để signer từ chối khi stale. Oracle là nguồn **controlled demo**, độc lập với `router.quote`, không mô phỏng oracle giá thị trường có đảm bảo production.

Terminal 2:

```powershell
uv run --locked treasury demo --network fuji
```

Hoặc dùng dashboard tại `http://127.0.0.1:8000` với `PACEVANT_OPERATOR_TOKEN`. Mục tiêu mẫu: `Buy WAVAX with 200 USDC`. Nếu đã cho phép reverse cap: `Sell 1 WAVAX for USDC`. Với mục tiêu không xác định được ý nghĩa, hệ thống từ chối thay vì đoán.

Theo dõi timeline: intent → alignment → build → simulation/stress → economic risk → proof Check/Compile/risk → SDE → attestation → submission → receipt. Dashboard hiển thị signed Phi, reservation, session/global usage, gas và actual deltas. Một giao dịch chỉ được gọi `CONFIRMED` khi receipt/canonical block/confirmation và accounting khớp. `PROTECTED_REVERT` là bảo vệ atomic có gas phí; `REJECT/ESCALATE` trước ký không có giao dịch swap.

Report đầy đủ nằm ở `.control-data-v2/fuji/demo-<workflow_id>.json`; audit SQL/query ở cùng profile, evidence/raw-tx journal trong `.execution-data-fuji-v2`. Dùng tx hash thật trong report để tra [Fuji explorer](https://explorer-test.avax.network/c-chain). Ctrl+C dừng dịch vụ, không xóa on-chain state hay audit. Pending được phục hồi bằng journal; không tạo swap mới để thay một giao dịch chưa biết kết quả.

Khi thuyết trình, bắt đầu bằng treasury/mandate và các giới hạn, chạy một buy, mở proof/Phi rồi đối chiếu receipt và counters. Một vault mới bắt đầu với 7.700 mock USDC và 115 mock WAVAX; tại giá demo 1/20, một buy 200 USDC đưa projected WAVAX exposure lên 25%. Lần mua tiếp theo có thể bị giảm size hoặc chặn. Với cap reverse đã được owner bật, bán một phần WAVAX tạo lại headroom rồi thử buy mới. Để trình bày hai trường hợp drift và cumulative budget theo cách tái lập được, dùng benchmark local và report; không hứa kiểm soát thứ tự mining trên public Fuji như Anvil.

## 6. Chạy lại, hết phiên và hạn mức

- Session mặc định 1 giờ. Dừng stack, xem lại owner settings, chạy `uv run --locked treasury renew-session --network fuji`, rồi khởi động lại `uv run --locked treasury serve --network fuji`. Lệnh owner tạo **session ID mới**, cập nhật manifest/mandate; session cũ và global/day spend vẫn giữ lịch sử. Restart cần thiết vì execution module cache deployment lúc khởi động.
- Policy hết hạn/đã thay cấu hình: dừng stack, owner xem lại `.env`, chạy `uv run --locked treasury renew-policy --network fuji`, rồi restart. Đây là giao dịch owner đổi proof policy/commitment và tạo phiên mới; không xóa day/global usage.
- Hai protected reverts liên tiếp cùng policy làm attestor quarantine policy đó. Cần owner điều tra và đổi policy sau review; không xóa database để làm mất audit.
- Budget tính theo reservation bảo thủ. Một chuỗi giao dịch lỗ thực tế nhỏ vẫn có thể hết session/global cap. Tạo session mới không làm mới global cap ngày UTC.
- Exposure WAVAX mặc định tối đa 25%, vẫn là **pre-sign gate**. Sau nhiều lần mua, workflow có thể giảm size hoặc từ chối. Không phải lỗi demo. Bán khi owner đã cho phép chiều reverse hoặc chọn một deployment mock mới có cấu hình vốn phù hợp; không tắt gate để luôn có kết quả xanh.
- Legacy spend cap là 500 USDC/swap và 1.000 USDC/ngày. Direction WAVAX→USDC có cap riêng. Không chỉnh trực tiếp file mandate để vượt các giới hạn on-chain.

## 7. Xử lý lỗi

| Biểu hiện | Kiểm tra / hành động |
|---|---|
| Doctor `MISSING`, `BLOCKED` | Điền đúng biến được nêu; owner approval/test-wallet acknowledgement, ba khóa phải khác nhau |
| `CHAIN_MISMATCH`, code/manifest mismatch | RPC C-Chain đúng 43113 và manifest V2 đúng deployment; không trỏ Anvil/local sang Fuji |
| Service thoát/cổng bận | Đọc `.control-data-v2/fuji/backend.log`, `backend.log`; đổi cổng hoặc dừng tiến trình cũ do bạn quản lý |
| Stale oracle/snapshot, hash mismatch | Đồng bộ đồng hồ máy, giữ heartbeat, kiểm tra RPC/head/rate limit và verification RPC; khởi tạo workflow mới từ evidence mới |
| Fork/RPC lỗi | RPC phải phục vụ historical code/storage/trace cần cho Anvil. Có thể cần provider hỗ trợ trạng thái gần đây tốt hơn public endpoint |
| Approval hết TTL | Deadline mặc định tối đa 30 giây; máy/RPC chậm phải xử lý nguyên nhân, không tái ký từ evidence cũ |
| Session inactive/expired/policy mismatch | Dừng dịch vụ, owner renew session/policy theo mục 6 và restart |
| Proof `SAT/UNKNOWN/INCONCLUSIVE` | Không có chữ ký. Xem proof artifact/counterexample và owner policy; không tự chuyển thành APPROVE |
| Pending/reorg/receipt mismatch | Giữ journal và workflow ID, poll receipt; không tạo thay thế với nonce mới khi kết quả chưa rõ |
| Không đủ gas | Nạp test AVAX đúng địa chỉ owner/relayer trên Fuji C-Chain; không phải token mock |

Giữ `.env`, `.execution-data*/`, `.control-data*/`, SQL và raw journal cục bộ. Chỉ chia sẻ report đã rà soát, địa chỉ công khai, tx hash, cấu hình không chứa bí mật. `.env.example` chỉ chứa placeholder.

## 8. Kiểm thử và bằng chứng

```powershell
uv run --locked python -m pytest -q
uv run --locked python tools/contracts/foundry.py forge test -vv
uv run --locked ruff check backend/src backend/tests tools
uv run --locked python tools/quality/scan_secrets.py
# Opt-in benchmark:
uv run --locked python tools/evaluation/evaluate_protocol.py
```

Benchmark cuối là opt-in local, archive đúng source V1 từ Git và chạy V1 legacy hai API và V2.1 một backend thật trên các Anvil riêng, không dùng `.env`/Fuji. Xem [full protocol comparison](../evaluation/full_protocol_results.md), [four-mode ablation](../evaluation/v1_vs_v2_1_ablation.md), [migration progress](../migration/v2_1_progress.md), [proof assumptions](../security/proof_assumptions_v2_1.md), [policy coverage](../security/policy_coverage_v2_1.md). Proof là bảo đảm có điều kiện trong mô hình hai mock asset/oracle domain; không chứng minh toàn bộ token/adapter, chặn mọi MEV hoặc bảo đảm exposure runtime.
