# Playbook merge A + B bằng AI

> Historical / compatibility document. For the current runtime use [V2.1 system design](AI_Treasury_Security_System_Design_v2.1.md) and [readiness audit](audit/V2_1_READINESS_REVIEW.md). Old A/B layouts, PoC evidence and removed pre-refactor paths describe their original checkpoint; they are not current deployment instructions or new validation evidence. References to removed artifacts are retained as plain code text.

Dùng khi có source phần A. Đây là hướng dẫn bàn giao/copy-paste cho AI, không có nghĩa code A đã hiện diện hay được kiểm thử trong repository B.

## 1. Thông tin người A cần cung cấp

- Repository/branch hoặc folder chứa code A, và revision nguồn B cần ghép. Hiện source B còn có thay đổi chưa commit trong working tree; người bàn giao phải commit/review chúng trước khi người khác dùng branch/PR. Đừng chỉ copy `git diff`, vì file mới chưa tracked có thể không nằm trong diff.
- Port/base URL muốn chạy A/B; mặc định A 8000, B 8001, dashboard theo A.
- Mạng test: local Anvil 31337 trước; Fuji 43113 sau.
- Nếu chạy Fuji: public address attestor do A quản lý, RPC phù hợp fork, test wallets/funds. Không gửi private key trong chat/PR.
- Tình trạng tests và gate A-01…A-10; nếu chưa implement đủ, AI cần hoàn thiện theo guide A, không giả APPROVE.

## 2. Prompt có thể đưa nguyên khối cho AI

```text
Bạn đang ghép AI Treasury Security Control Plane A với Execution Plane B.
Hãy thực hiện merge/integration trong workspace, không chỉ viết kế hoạch.

ĐỌC THEO THỨ TỰ:
1. docs/03_SHARED_INTEGRATION_CONTRACT.md — single source of truth v1.1.
2. docs/01_GUIDE_PERSON_A_CONTROL_PLANE.md và 02_GUIDE_PERSON_B_EXECUTION_PLANE.md.
3. docs/06_AB_INTEGRATION_HANDOFF.md — hành vi thực tế và giới hạn B/SDK.
4. docs/handoff/integration-manifest.json — index máy đọc, file/route/model/commands.
5. packages/contracts-api/treasury_contracts/{models,client,crypto,onchain}.py,
   JSON Schemas, openapi.json, ABI và fixtures/eip712_golden/.
6. docs/08_AB_COMPATIBILITY_AUDIT.md — cái đã kiểm chứng và gate chưa có A/Fuji.

OWNERSHIP:
- Implement/preserve A trong apps/control-plane; dashboard A trong apps/dashboard.
- Preserve B trong apps/execution-plane và contracts; giao tiếp qua HTTP.
- A import treasury_contracts từ shared package. Không import app.* của B hoặc thêm
  apps/execution-plane vào PYTHONPATH của A: hai backend có namespace app riêng.
- Shared schema, Approval, golden vector, fixtures và root configs là shared ownership.
  Không tự đổi route/field/enum/units/Approval order để làm test pass.

PRESERVE:
- Giữ .env trên máy, merge biến bằng tên, không ghi đè toàn file từ branch khác.
- Không đưa secret vào chat/log/docs/fixtures/git. Chỉ merge .env.example.
- Không xóa thay đổi chưa commit của người dùng, không reset/clean workspace.
- Root npm/Foundry scripts thuộc B; merge thêm dashboard scripts nếu cần, không thay
  root package.json bằng package của React/Next.js.
- Không khôi phục Hardhat/ERC-4337/PoC cũ; docs lịch sử không là API hiện hành.

IMPLEMENT A ĐÚNG GUIDE:
- Planner typed + Shield → ALIGNED; UNCERTAIN phải ESCALATE, MISALIGNED phải REJECT.
- Trusted orchestrator lấy chain/vault/token/router từ B context, deadline vừa tạo,
  proposal đúng chain local 31337 hoặc Fuji 43113 theo mode đã chọn.
- SDK build → simulate → verify_evidence. Persist exact records/hashes/build/nonce.
- Thêm trusted prices/history vào B OnchainSnapshot rồi chạy risk deterministic:
  max trade/day, exposure ≤25%, freshness, no float, tối đa 2 replan.
- SDE immutable decision; attestor chỉ nhận decision_id, tự load/check records từ DB.
- Chỉ ký APPROVE còn hạn, đủ predicate và exact evidence/build/policy/domain binding.
  Re-fetch read-only policy/nonce/attestor/bytecode/freshness trước khi ký.
- Fuji deny MOCK_FIXTURE và REAL_LOCAL_SIM thuần túy; chỉ FORK_SIM đối chiếu được.
- Serialize signed Approval bằng camelCase chính xác, uint256 decimal strings,
  EIP-712 domain TreasuryPolicyVault/1. Không personal_sign hay arbitrary signing API.
- POST execution giữ payload và Idempotency-Key khi retry; poll receipt. Không hiển thị
  CONFIRMED chỉ vì SDE APPROVE hoặc POST SUBMITTED.
- Serialize workflow theo chain/vault đến khi receipt terminal để tránh exposure risk
  cùng snapshot; reconcile PENDING trước khi mở attempt kinh tế mới.
- PROTECTED_REVERT là rollback, không tự gọi là UNSAFE_EXECUTION hay mất token.
- Mỗi REPLAN/stale attempt tạo build/sim/risk/decision/signature mới; không sửa PDR cũ.

VALIDATE:
- npm ci --ignore-scripts; npm run setup; npm run check; npm run test:consumer.
- Chạy tests A trong project uv riêng; không nối thủ công uv.lock.
- Chạy N/P/E/M/R/C/S/O và A-01…A-10 với A thật, B thật trên local.
- Không dùng LOCAL_PROTOCOL_PROBE_NOT_A_SDE hay local demo của B làm production SDE.
- Chưa đủ attestor/Fuji RPC/funds thì ghi rõ pending G6; không bịa txHash/explorer.

DELIVER:
- Code merge cụ thể, docs lệnh chạy A/B, các biến .env.example mới, tests/evidence.
- Report file conflicts đã giải quyết và API/signature contracts có đổi hay không.
- Đánh dấu riêng: test B, protocol consumer, SDE A thật, full A+B, Fuji.
  Chỉ gọi end-to-end A+B hoàn thành khi code A thật đã chạy qua các gates.
```

## 3. Trình tự kỹ thuật khi ghép branch

### Bước 1 — bảo toàn source và xác định baseline

```powershell
git status --short
git diff --stat
git ls-files --others --exclude-standard
```

Người bàn giao review/commit cả source mới lẫn các deletion PoC có chủ đích. Không commit `.env`, `.execution-data*/`, `.control-data*/`, runtime key, local deployment manifest hoặc build output. Nếu hai người ở hai repository khác nhau, import source/commit vào nhánh tích hợp riêng và giữ lịch sử origin để review. Không merge dữ liệu private giữa hai máy.

### Bước 2 — giải quyết conflict theo ownership

| Conflict | Cách xử lý |
|---|---|
| `apps/control-plane`, `apps/dashboard` | Giữ implementation A, sửa adapter gọi B nếu lệch interface |
| `contracts`, `apps/execution-plane` | Giữ bảo vệ B; nếu bug thực sự thì sửa có test regression |
| `packages/contracts-api` | Đối chiếu shared v1.1/golden. A dùng SDK, không tạo DTO thứ hai |
| JSON Schema/OpenAPI/ABI | Sinh lại từ source bằng `npm run compile` + `npm run schemas`; review diff |
| Root `package.json` | Giữ Foundry/OpenZeppelin/viem + B scripts; dashboard dependency theo project A |
| `package-lock.json` | Sau khi merge package.json, regenerate bằng npm phù hợp; không chọn lock tùy ý |
| Các `uv.lock` | Giữ mỗi app một file; chạy uv sync/lock ở đúng project |
| `.env.example` | Hợp nhất tên/comment/default không bí mật; B_* và A_* không đè nhau |
| `.env` | Không lấy bản trong branch/PR; giữ cấu hình máy, bổ sung biến cần thiết bằng tên |
| `.github/workflows` | Giữ B checks, bổ sung jobs A và full integration; không bỏ B tests để CI xanh |
| `frontend/`, Hardhat/AA PoC | Deletion có chủ đích; chuyển UI A cần dùng sang apps/dashboard |

Không thêm npm workspace trỏ tới folder dashboard chưa tồn tại. Nếu A dùng npm workspaces, tạo cấu hình chỉ khi có package thật; cũng có thể giữ dashboard tự quản lý bằng `npm --prefix apps/dashboard ...`.

### Bước 3 — ghép read-only/build trước signing

Chạy B với `npm run local`, lấy API key từ `.env` vào settings backend A. A gọi context/snapshot bằng SDK, persist mapping workflow→intent→build. Xác nhận A parse được model và không giả định snapshot B có prices. `deadline` do orchestrator trusted tạo ngay trước build, sau các bước LLM/Shield chậm.

Thử request sai recipient, chain, token và schema: A phải đọc error envelope đúng, không retry thành transaction tùy ý. Kiểm tra request correlation bằng `X-Request-ID` và retry với cùng Idempotency-Key.

### Bước 4 — simulation → risk → immutable SDE

Tải manifest/artifacts bằng SDK, verify hash/bindings và provenance. Lấy fresh chain snapshot + trusted prices. Fixture `fixtures/mock/simulation_evidence.json` hiện là INCOMPLETE; không dùng nó làm proof production. Nếu A cần unit fixture để test SDE độc lập, phải gắn mode/source test rõ ràng, không bật Fuji signer.

Normal 200 USDC có adverse stress PROTECTED_REVERT; A phải định nghĩa rõ policy đối với stress rollback. Exposure 500 →28% phải REPLAN trước signing. Proposal mới sau replan đi lại toàn bộ pipeline, giới hạn 2 lần.

### Bước 5 — golden và attestor

Chạy vectors trước khi relay. Local test signer của A phải là signer Vault hiện tại; không suy ra nó từ owner/agent address. `read_approval_state` và packaged ABI giúp kiểm tra nonce/policy trực tiếp, không cần import code B.

Attestor A chỉ xử lý `decision_id` trong DB của chính A. Kiểm tra immutable APPROVE, expiry, full hash binding, freshness, authorized signer và double-sign gate trước ký. Code signing fragment trong handoff chưa bao gồm toàn bộ các predicate đó; không copy nó thành attestation endpoint mở.

### Bước 6 — receipt, failure và UI

Chạy exact SignedPDR qua B; A dùng GET result để cập nhật CONFIRMED/REVERTED/PENDING. Revert có token delta 0 nhưng có thể tốn gas. Khi RPC drop, retry cùng request/key lấy lại cùng txHash; không build một swap mới để thay cho retry chưa rõ kết quả.

Giữ state machine và terminal outcomes đúng guide. Dashboard gọi A, không cầm API key B hay key owner/attestor. Feedback/experience chỉ tư vấn, không sửa mandate.

## 4. Checklist để tuyên bố merge thành công

- [ ] A và B chạy process/env riêng, cùng shared SDK version và network/deployment.
- [ ] Schema/OpenAPI/ABI/golden checks pass; không đổi Approval v1.1 ngoài quy trình shared review.
- [ ] Context/portfolio được A đọc đúng; prices/history có nguồn riêng và không dùng float.
- [ ] N: A thật ALIGNED → risk PASS → immutable APPROVE → attestor A → B → receipt CONFIRMED.
- [ ] P: injection/recipient ngoài vault không dẫn tới signature/unauthorized execution.
- [ ] E: $500 exposure 28% → REPLAN, không ký; $200 candidate được build/sim/evaluate mới.
- [ ] S: stale/missing evidence/price hoặc UNCERTAIN → no signature.
- [ ] M: adverse below minOut rollback, không ghi nhận token mất thật.
- [ ] R/O: replay, modified call, policy/attestor revoke bị từ chối.
- [ ] C: daily spent 700 +200 +200, chỉ tối đa một swap nữa thành công dưới 1,000.
- [ ] Transport retry không nhân đôi giao dịch, receipt pending không hiện CONFIRMED.
- [ ] Tests A-01…A-10 và B checks đều pass.
- [ ] G6 Fuji có proof đúng network/attestor/fork/receipt thật hoặc được ghi pending rõ ràng.

Nếu thiếu code A, không đánh dấu các ô liên quan A đã pass chỉ vì consumer probe của B pass. Danh sách này là tiêu chí nghiệm thu, không phải kết quả hiện có.
