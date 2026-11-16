# Triển khai và bàn giao phần B — Execution Plane v1.1

Mã mới bám `03_SHARED_INTEGRATION_CONTRACT.md` và guide B ngày 16/11/2026. `PolicyVault` chỉ swap mock USDC → mock WAVAX; không phải smart account ERC-4337. Phần A vẫn sở hữu Planner, Shield, exposure/risk, SDE, attestor và dashboard.

## 1. Cấu trúc để merge với A

| Thư mục | Nội dung |
|---|---|
| `contracts/src/` | Vault, adapter, mock tokens; OpenZeppelin 5.6.1 |
| `contracts/test/PolicyVault.t.sol`, `PDRGoldenVector.t.sol` | Acceptance/security tests, Python → Solidity golden signature |
| `contracts/script/Deploy.s.sol` | Script Foundry thay thế; CLI Python là đường deploy lưu manifest |
| `apps/execution-plane/` | FastAPI, builder, pinned-fork simulator, extractor, relayer, SQLite |
| `packages/contracts-api/` | Package Python dùng chung, HTTP client, JSON Schema |
| `fixtures/` | Input mẫu, mock outputs và golden vector |
| `evidence/execution-plane-*` | Kết quả kiểm chứng của phần B |

Code PoC cũ (React/Vite, Hardhat, ERC-4337, script Avalanche và tests cũ) đã được loại khỏi working tree theo yêu cầu refactor. Tài liệu PoC được giữ trong `docs/`, gồm `LEGACY_POC_README.md`; xem `05_PROJECT_STRUCTURE.md` để tham khảo hoặc tìm source trong clone/backup cũ nếu có. Foundry chỉ build `contracts/src`, test trong `contracts/test`. Module chain nằm tại `app/chain/`; cross-language test nằm trong `tests/integration/`.

Merge các thư mục mới ở trên cùng `foundry.toml`, package files và `.gitignore`. Các lệnh npm chuẩn (`compile`, `test`, `dev`, `deploy:local`) chạy phần B; alias `b:*` vẫn tương thích. Không commit `.env*`, `.execution-data/`, `.venv/` hoặc `deployments/execution-local.json`. Schema/fixture/Approval cần A review theo shared contract; bản này chưa có review của A.

## 2. Chạy local trên Windows

Cần Node >=22.13, npm và `uv`. Lock Python được commit trong `apps/execution-plane/uv.lock`. Foundry forge/anvil 1.7.1 và OpenZeppelin được pin bằng `package-lock.json`.

```powershell
npm ci --ignore-scripts
npm run setup
npm run check
npm run local
```

`npm run local` tự compile, khởi động Anvil nếu cần, tái dùng deployment hợp lệ hoặc bootstrap mới, rồi chạy API. Khi dừng bằng Ctrl+C, nó chỉ dừng Anvil do chính lệnh đó tạo; node đang có được giữ lại. Port API mặc định 8001; có thể dùng `npm run local -- --port 8002` nếu cần. Các bước terminal bên dưới là lựa chọn chạy tách riêng.

`--ignore-scripts` tránh script postinstall POSIX của package Foundry lỗi dưới cmd.exe. Wrapper `scripts/foundry.mjs` gọi binary theo OS/CPU từ optional packages. Nếu tự cài Foundry 1.7.1, có thể dùng `forge`, `anvil` trong PATH; `B_ANVIL_BINARY` cho phép chỉ rõ đường dẫn.

Terminal 1:

```powershell
npm run b:anvil
```

Terminal 2:

```powershell
npm run b:deploy:local
npm run b:demo
npm run b:api
```

Bootstrap tạo ba tài khoản **ngẫu nhiên, khác nhau** owner/attestor/relayer, fund native token bằng RPC chỉ trên Anvil loopback, deploy mock tokens/router/vault, cấu hình mandate và mint 7,700 USDC + 115 WAVAX vào vault. Giá adapter test mặc định $20/WAVAX. Cấu hình dùng **một file `.env`**: bootstrap cập nhật `B_LOCAL_*`, giữ nguyên các biến khác và giữ `B_API_KEY` đã có. Local owner/attestor keys vẫn chỉ ở `.execution-data/local-keys.json`, bị gitignore; `.env` giữ local relayer key. Không tạo lại `.env.b.local`.

API: `http://127.0.0.1:8001/docs`; health: `/health`. Truyền `X-API-Key` lấy từ `B_API_KEY` trong `.env` cho mọi route `/v1/*`. POST cần `Idempotency-Key`. A có thể dùng `ExecutionClient` trong package chung. Không đưa API key hoặc attestor key vào frontend.

`b:demo` chạy B thật và **ký local test PDR**, ghi `evidence/execution-plane-local.json`. Nó không giả lập rằng A đã chạy SDE: `a_sde_exercised=false`. Chạy lại demo tiêu thêm 200 mock USDC trong hạn mức; nếu hết 1,000/ngày thì khởi động node/deploy mới hoặc dùng tài khoản owner điều chỉnh mandate trong test. API chỉ dùng relayer key, không đọc file local attestor keys.

`b:test` tự khởi động node riêng và dùng snapshots, không cần node/demo đang chạy. Restart node local cần deploy lại; không tái dùng manifest và DB của node cũ. Các account/địa chỉ được tạo sau deploy, không hardcode.

## 3. API cho A

| Method | Route | Dữ liệu |
|---|---|---|
| GET | `/v1/chain/context` | Chain/vault/policy/attestor, block/hash/time, giới hạn và route hỗ trợ |
| GET | `/v1/portfolio/onchain-snapshot` | Balance theo block, UTC day, daily spent; không tự thêm giá USD |
| POST | `/v1/build` | `TransactionProposal` → immutable `BuiltTransaction` |
| POST | `/v1/simulations` | `{build_id, expected_policy_hash}` → `SimulationEvidence` |
| POST | `/v1/executions` | `{build_id, signed_pdr}` → `{tx_hash,status}` |
| GET | `/v1/executions/{tx_hash}` | Receipt, deltas từ Transfer logs, SwapExecuted, artifact refs |
| GET | `/v1/artifacts/{keccak}` | Canonical bytes để A tự kiểm tra hash/provenance |

Lấy addresses và chain từ context, không dùng address minh họa trong docs. Orchestrator nên chọn `deadline = min(now_unix, context.timestamp) + 25` để có dư thời gian trong TTL on-chain 30 giây. Local node lâu không mine có block timestamp cũ: mine một block trước khi bắt đầu workflow. Không tăng TTL âm thầm; build/simulation/PDR hết hạn phải tạo workflow attempt mới.

Nonce được cấp trong SQLite `BEGIN IMMEDIATE`, namespace chain/vault. Các mutation được serialize bằng process-shared file lock. Hai PDR khác nonce vẫn phải chịu daily counter atomic trên Vault. Một build có đúng một evidence immutable tại snapshot đã chốt; cùng build trả lại evidence cũ. Muốn mô phỏng state mới thì build mới.

Build/simulation retry cùng `Idempotency-Key` và cùng payload trả cùng artifact immutable. Execute retry giữ cùng tx hash, có thể cập nhật status và gửi lại đúng bytes đã journal nếu RPC chưa nhận. Đổi payload mà giữ key → 409. Relayer lưu raw signed transaction và tx hash **trước broadcast**; retry cùng build/PDR không ký thêm transaction. Nếu RPC timeout không rõ đã nhận hay chưa, trả PENDING và giữ hash để theo dõi. A phải poll GET; POST success/SUBMITTED không có nghĩa CONFIRMED.

## 4. Simulation/evidence

Mỗi simulation spawn Anvil fork riêng từ RPC nguồn tại block build. Nó kiểm tra block hash, deployed code, balances, allowance, policy và giá mock. Compiler storage layout được dùng để thay **duy nhất attestor** trong fork bằng ephemeral signer; owner thật và RPC nguồn không bị ghi. Gas balances và giá mock ở stress cũng chỉ đổi trong fork.

Ba kịch bản cùng snapshot: baseline, mild (giá ×9980/10000), adverse (×9800/10000). Thực thi qua đúng `PolicyVault.executeApprovedSwap`, cùng calldata/nonce/deadline. `evidenceRoot` của PDR mô phỏng là sentinel ghi rõ `simulation_only`; root cuối được tính sau chạy. Việc đổi signer/sentinel được ghi provenance, vì simulation không chứng minh A đã duyệt hoặc chữ ký production hợp lệ. Golden vector và integration execution kiểm chứng chữ ký riêng.

Extractor đối chiếu receipt, call trace, before/after balances/allowance và toàn bộ Transfer/Approval logs. Chỉ trace chứa `MinOutputNotMet()` cùng rollback mới gọi là PROTECTED_REVERT. Unknown revert/trace lỗi/bytecode hoặc state lệch không được COMPLETE. Mô phỏng không ghi DB counter hay thay nonce ở source chain.

Manifest canonical theo RFC 8785/JCS, không chứa `evidence_root`; `evidence_root=keccak256(bytes_manifest)`. Manifest commit report facts + bindings + content hashes của raw artifacts. A tải manifest và từng artifact bằng SDK `verify_evidence` rồi mới chạy SDE. Số uint256 lớn trong raw artifacts cũng dùng string, tránh JSON làm tròn số.

Local: `source=REAL_LOCAL_SIM`. Fuji: chỉ `FORK_SIM` với deployed state/code được đối chiếu mới qua gate relayer. `MOCK_FIXTURE`/local thuần túy không được relay Fuji. Kết quả deterministic là effects/constraints tại snapshot/seed; raw hashes còn gắn client version, account/signature simulation và dữ liệu provenance. Lưu nguyên artifact để tái kiểm chứng; không coi stress là mô hình sandwich ngoài đời.

## 5. Fuji — phần chờ người A

**Chưa deploy/execute bản PolicyVault mới trên Fuji vì A chưa có địa chỉ attestor.** Các địa chỉ Fuji trong PoC cũ không phải deployment của bản v1.1. Không cần gửi private key của A cho B.

Cách lấy `B_FUJI_ATTESTOR_ADDRESS`:

1. A tạo một ví EVM test riêng trong MetaMask: [thêm account mới](https://support.metamask.io/configure/accounts/how-to-add-accounts-in-your-wallet), chọn account attestor rồi [copy địa chỉ public](https://support.metamask.io/start/how-to-copy-your-metamask-account-public-address-). Nếu giao diện hiển thị nhiều network addresses, chọn địa chỉ Ethereum/EVM `0x...`, dùng được trên Fuji.
2. Account attestor phải khác owner và relayer. Chữ ký PDR off-chain không cần AVAX để ký; owner deploy và relayer gửi tx cần test AVAX.
3. Nếu A đã có private key riêng trong service attestor, A tự chạy `Account.from_key(attestor_private_key).address` bằng `eth_account`, rồi chỉ gửi **địa chỉ public** sang B. Không dán private key vào chat/git/B/frontend. A tự cấu hình key này trong control-plane theo guide A.

Cấu hình nhóm Fuji trong **cùng `.env`** tại root. `npm run deploy:fuji` và `dev:fuji` tự chọn nhóm này, không cần đổi `B_MODE` hoặc copy file:

```dotenv
B_MODE=local
B_API_KEY=<chuoi-ngau-nhien-dung-chung-giua-backend-A-va-B>
B_FUJI_RPC_URL=${FUJI_RPC_URL}
B_FUJI_DEPLOYMENT_FILE=deployments/execution-fuji.json
B_FUJI_DATA_DIR=.execution-data-fuji
B_FUJI_RELAYER_PRIVATE_KEY=${AGENT_PRIVATE_KEY}
B_FUJI_OWNER_PRIVATE_KEY=${DEPLOYER_PRIVATE_KEY}
B_FUJI_ATTESTOR_ADDRESS=<dia-chi-public-do-A-cung-cap>
```

Các tham chiếu `${...}` tái dùng biến ví test hiện có, không nhân bản giá trị private key. Có thể thay bằng ví test riêng nếu muốn. Owner key chỉ được model của lệnh deploy/config đọc; API không có field owner key và không dùng key này. Attestor private key vẫn do A giữ trong control-plane. Chỉ commit `.env.example` khi merge; `.env` giữ ở máy chạy, không gửi cho A.

Nạp test AVAX cho owner/relayer qua faucet Fuji, kiểm tra chain là 43113. Owner cần đủ gas deploy 4 contract + cấu hình/mint; relayer chỉ cần gas execution. Chạy:

```powershell
npm run config:fuji
npm run compile
npm run check
npm run deploy:fuji
npm run dev:fuji
```

CLI lưu địa chỉ/code hashes/policy thật vào `deployments/execution-fuji.json`; chuyển manifest public cho A. A gọi build/simulate và chỉ ký sau immutable APPROVE + verified `FORK_SIM`. B gửi đúng signed PDR và theo dõi receipt. Explorer Fuji chỉ được ghi sau receipt thật; không sử dụng hash local làm hash Fuji. Nếu public RPC không hỗ trợ fork archive/trace hoặc simulation vượt TTL/drift, hệ thống fail closed; chọn RPC phù hợp hoặc demo local có nhãn rõ ràng.

## 6. Acceptance và giới hạn bàn giao

Lần kiểm chứng local: **27 Forge tests + 34 pytest tests pass**, thêm 256 fuzz runs; golden vector Python/viem/Solidity và ruff đều pass. Bao gồm consumer SDK độc lập qua HTTP thật, OpenAPI/ABI/handoff drift checks, retry sau RPC drop, cấu hình env/profile và local node idle. API chạy thật tại port 8001 đã phục vụ manifest/artifacts được SDK kiểm tra lại và receipt CONFIRMED. Xem `evidence/execution-plane-validation.json`, `ab-consumer-acceptance.json`, `shared-sdk-package.json`. Hai cảnh báo deprecation đến từ thư viện Python, không phải test failure. Workflow GitHub CI đã thêm, chưa được chạy trên GitHub trong phiên này.

`b:check` chạy Forge, pytest (gồm full HTTP E2E trên Anvil riêng), cross-language Python/viem golden hash và secret scan. Forge bao gồm B01–B10, sai selector, policy revoke/reactivate, ngày UTC, bad signer/domain, allowance exact/reset, adapter thiếu input/output, reentrancy và fuzz. Python kiểm chứng B11–B12, strict money/schema, auth/errors, concurrent nonce, idempotency, source-fork isolation, evidence provenance, ký Python → Vault và receipt.

Hoàn thành B không thay cho G2/G4 của A: normal/exposure/injection/stale phải đi qua SDE/attestor thật của A khi ghép. Fixture injection được Builder chặn recipient, nhưng Shield semantic vẫn do A. Exposure 25% cần giá và portfolio do A kiểm chứng; Vault không tính USD exposure. G6 Fuji còn chờ địa chỉ attestor, test AVAX và end-to-end với A.

## 7. Quy tắc cấu hình một file và merge

`B_MODE` chọn mạng mặc định của `npm run dev` và `config`. Các lệnh có mạng rõ ràng và `demo`/`local` luôn chọn đúng profile. `B_LOCAL_*` và `B_FUJI_*` giữ RPC, relayer, deployment và DB riêng; TTL/limits/API key chung vẫn dùng `B_*`. Generic `B_RPC_URL`, `B_RELAYER_PRIVATE_KEY`, `B_DEPLOYMENT_FILE`, `B_DATA_DIR` còn được hỗ trợ như override cho môi trường CI/operator, nhưng không cần dùng chúng trong `.env` chuẩn.

Để bàn giao/merge với A: đọc [handoff chi tiết](06_AB_INTEGRATION_HANDOFF.md), [playbook cho AI](07_AI_MERGE_PLAYBOOK.md) và [audit](08_AB_COMPATIBILITY_AUDIT.md). SDK có model response, error envelope, OpenAPI và ABI/nonce helper riêng; A không import backend B.

`python -m app.cli migrate-env` gộp file split cũ nếu checkout của thành viên khác vẫn có chúng, kiểm tra xung đột trước khi cập nhật và giữ nguyên API key/biến A. Việc ghi `.env` dùng file lock và atomic replace. Đường dẫn trong profile dùng dạng tương đối để không chứa đường dẫn máy cá nhân. Mỗi thành viên copy `.env.example` thành `.env`, điền thông tin riêng, không merge secret.
