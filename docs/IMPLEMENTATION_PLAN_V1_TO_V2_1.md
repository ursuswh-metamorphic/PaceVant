# IMPLEMENTATION PLAN — AI Treasury Security V1 → V2.1 (Lean Proof-Gated Treasury)

> **Audience:** AI coding agent đang chạy tại **root repository của dự án thực tế**.  
> **Loại tài liệu:** Execution plan + migration specification + acceptance tests; không phải mô tả code hiện có.  
> **Ngày soạn:** 19/11/2026.  
> **Target:** Avalanche Fuji C-Chain, chain ID `43113`; mock USDC ↔ mock WAVAX, **một** allowlisted swap adapter, owner-controlled `PolicyVault`, EIP-712 PDR.  
> **Giới hạn:** testnet/research/hackathon, **không production-ready hoặc audited**. Không dùng quỹ thật.  
> **Tài liệu nguồn:** `AI_Treasury_Security_System_Design_v1.0(1).md` (V1), `AI_Treasury_Security_System_Design_v2.1.md` (V2.1), local folder `Proof-Gated-Signing/` (PGS reference), paper [arXiv:2610.00354](https://arxiv.org/abs/2610.00354).

---

## 0. LỆNH THỰC THI CHO CODING AGENT — ĐỌC TRƯỚC KHI SỬA CODE

Bạn đang **migrate một dự án V1 ĐÃ ĐƯỢC CODE**. Không được mặc định dự án trống, không được viết lại từ đầu, không dựa vào layout giả định trong hai design documents để kết luận file đã tồn tại. **Repository thực tế là source of truth về code**, V2.1 là target behavioral specification, V1 là baseline để bảo toàn.

### Nguyên tắc không được vi phạm

1. **Inspect first, edit second.** Tìm hiểu cấu trúc và logic V1, chạy test/baseline trước khi refactor. Ghi lại khoảng trống giữa code thật, V1 và V2.1. Không khẳng định feature có sẵn khi chưa thấy code/test.
2. **Incremental migration.** Giữ nguyên module có trách nhiệm hợp lý. Ưu tiên adapter/refactor nhỏ, không dựng backend/contract/frontend mới song song. Không đổi stack hoặc cấu trúc thư mục hàng loạt chỉ vì tài liệu v2.1 có ví dụ khác.
3. **One authoritative path:** một `PolicyVault`/guarded execution path, một SDE, một attestor, một bộ policy model, một proof subsystem, một Outcome Monitor. Không có LLM-controlled bypass, arbitrary `target.call`, `delegatecall`, second signer/executor.
4. **Never weaken V1.** Preserve owner access control, chain/domain, attestor revocation, nonce/replay prevention, pauses, adapter/selector/recipient allowlists, `amountIn`, `minOut`, daily spend atomicity, reentrancy guard, temporary allowance cleanup, stale evidence rejection, semantic Task Alignment, exposure pre-sign gate, observability.
5. **Fail closed.** `SAT`, `UNKNOWN`, solver timeout, malformed proofs/evidence/ABI, stale policy/oracle/snapshot, hash mismatch, insufficient coverage, pending/reorg uncertainty → NO SIGNATURE; không tự chuyển thành APPROVE.
6. **Không fake kết quả:** không khai báo test pass/deploy Fuji/benchmark/coverage nếu chưa chạy và chưa có bằng chứng. Không hardcode địa chỉ giả hoặc keys. Nếu thiếu credential/test AVAX/RPC, hoàn thành local integration và ghi `BLOCKED_EXTERNAL_DEPENDENCY`, không tạo tx hash giả.
7. **Không đưa code PGS vào GitHub của dự án:** `Proof-Gated-Signing/` là reference local, cần thêm root `.gitignore` và kiểm tra trạng thái Git trước khi commit. Chỉ port logic tối thiểu sau khi hiểu/kiểm tra license; không copy nguyên testbed/wallet.
8. **Small focused changes + tests.** Từng phase có code, migration, test và báo cáo. Không thay đổi public API/ABI cũ tùy tiện; dùng versioned schema/signature khi breaking.
9. **Không tự suy ra owner-approved security parameters.** Nếu project chưa có các giá trị `max_relative_loss_bps`, `fixed_loss`, `oracle_band`, `tau`, session/global cap, giới hạn chiều WAVAX→USDC, dùng **test-only config đánh dấu rõ**; không kích hoạt signer trên Fuji với thông số chưa được chủ sở hữu phê duyệt.
10. **Giải pháp phải chạy trên môi trường hiện tại.** Ưu tiên framework/test runner/package manager đang dùng. Nếu một bước trong plan không tương ứng với repo thì **map vào component tương đương**, ghi lý do. Nếu một hạng mục đã implement đúng thì **giữ và thêm test**, không viết lại.

### Cách báo cáo mỗi phase (bắt buộc)

Ghi tóm tắt vào `docs/migration/v2_1_progress.md` (tạo trong repo nếu chưa có):

```text
Phase / status: DONE | PARTIAL | BLOCKED
Files changed: ...
V1 behavior preserved: ...
V2.1 behavior added: ...
Commands executed: ...
Tests: X passed, Y failed, Z skipped (lý do)
Security assumptions / new risks: ...
Deployment info (nếu có): verified chain ID, address, tx hash, block
Next step: ...
```

Không xóa log/test cũ để che failing tests. Khi phát hiện blocker nguy hiểm, dừng phần **ký/gửi giao dịch**, vẫn có thể tiếp tục unit tests và tài liệu hóa blocker.

---

## 1. MỤC TIÊU VÀ DEFINITION OF DONE

### 1.1 Kết quả cần đạt

Nâng cấp flow V1:

```text
Owner mandate → AI typed intent → Task Alignment → deterministic Transaction Builder
  → exact-path Simulation + fixed stress → typed Effect Evidence
  → Economic Risk / Oracle / Exposure precheck
  → [PGSProofEngine: SMT Check → Postcondition Compiler → SMT Compile → Certified Risk Bound]
  → single SDE decision → isolated Attestor signs EIP-712 ApprovalV2
  → Relayer → PolicyVaultV2 (atomic PDR + Phi + session/global/daily checks)
  → CONFIRMED or PROTECTED_REVERT → reconciled Monitor / Audit / Replan
```

**Core value of V2.1:** chứng minh `Phi ⇒ ValuePolicy` trong modeled price domain trước khi ký, bảo đảm `Phi` được ký đúng exact transaction và được enforce atomically on-chain; thêm certified worst-case loss debit trong session/global budget. **Không nói rằng PGS giải quyết toàn bộ exposure drift, oracle compromise, token lies hoặc bất kỳ loại MEV nào.**

### 1.2 Must-have sản phẩm (MVP V2.1)

- [ ] V1 user journey còn chạy: configure owner mandate, đề xuất swap, kiểm tra, ký, submit, monitor, replan có giới hạn.
- [ ] Hai hướng swap MockUSDC ↔ MockWAVAX được kiểm tra đúng theo limit **từng chiều**; nếu chưa có owner-approved limit chiều WAVAX→USDC, tạm khóa chiều đó trong môi trường ký thật/testnet và đánh dấu trong UI, không âm thầm bỏ max-trade rule.
- [ ] One off-chain `PGSProofEngine` với Check Mode, Compiler, Compile Mode và certified risk bound; tất cả trả về typed artifact, provenance và `SAT/UNSAT/UNKNOWN`.
- [ ] `ApprovalV2` ký exact calldata/swap, policy version/hash, evidence context, `postConditionsHash`, session ID, riskDebit, nonce, deadline trong domain EIP-712 chuẩn.
- [ ] PolicyVault V2 verify mọi binding; snapshot tracked balances, thực thi swap hạn chế, cleanup allowance, enforce Phi, cập nhật on-chain budgets atomically; revert không để lại token state/counters/nonce.
- [ ] `dailySpentUsdc`, `sessionRiskUsed`, `globalDailyRiskUsed` không bị race hoặc reset bởi agent/new session; Owner quản lý session.
- [ ] SDE không ký khi proof không hợp lệ/không trùng artifact hoặc exposure/price gate không đạt.
- [ ] Audit nối được intent → exact call → simulation block/hash → effects → proof/query → Phi → SDE → PDR → tx receipt/counters.
- [ ] Local/fork tests, Foundry tests và Fuji smoke tests **nếu có testnet credentials**; không claim Fuji nếu chỉ có Hardhat local.
- [ ] Có ablation **Full V1 vs upgraded guard vs PGS vs session budget**, có kết quả định lượng khi chạy benchmark.
- [ ] `Proof-Gated-Signing/` không được track/push trong project repo.

### 1.3 Explicitly non-goals, KHÔNG LÀM MỞ RỘNG LÉN

- Không chuyển ERC-4337/7579, không thêm bundler/paymaster, không multi-chain, không bridge/lending/real DEX, không arbitrary calls, không payment/owner checks không có operation tương ứng, không second AI verifier, không on-chain SMT verifier, không migrate sang microservices.
- `enforce_exposure_onchain` là **optional feature có gate riêng**, **không** được tuyên bố bảo đảm allocation 25% khi gate này tắt. Giữ mandatory off-chain exposure check của V1.
- Không tích hợp private keys từ PGS testbed; không dùng `AgentWallet.execute` unguarded của paper làm production path.

### 1.4 Vai trò các nguồn

| Nguồn | Cách dùng | Không được làm |
|---|---|---|
| **Current repo** | Quyết định file paths, stack, actual API, existing tested behavior | Coi thiếu chứng cứ là feature đã tồn tại |
| **V1 spec** | Xác nhận invariant / API / demo behavior cần giữ | Recreate toàn bộ module nếu code đã có |
| **V2.1 spec** | Target semantics cho SMT, PDRv2, budget, Phi, UI | Triển khai tất cả optional extensions như bắt buộc |
| **`Proof-Gated-Signing/`** | Kiểm chứng thuật toán PGS, test fixtures, differences và benchmark design | Copy repo nguyên khối, dùng wallet unguarded, đưa vendor vào Git |
| **Paper arXiv** | Scope theorem / assumptions / SAT-vs-UNSAT / effect policy | Áp paper APR/BPR 93.6%/97.5% cho sản phẩm |

---

## 2. PHASE 0 — REPOSITORY DISCOVERY, BASELINE, GIT HYGIENE (P0, FIRST)

> **Không được bỏ qua phase này.** Đây là điều kiện để mọi lệnh phía sau áp dụng đúng vào code thực tế.

### 2.1 Xác định root và bảo vệ working tree

```bash
pwd
git rev-parse --show-toplevel
git status --short
git branch --show-current
# Windows PowerShell: git status --short; git rev-parse --show-toplevel
```

- Phát hiện user modifications/staged files và **không overwrite**. Nếu repo có thay đổi chưa commit, làm việc giữ nguyên chúng, report nguy cơ conflict; không `git reset --hard`, `git clean -fd`, force push hoặc tự rewrite history.
- Tạo branch migration **khi an toàn và phù hợp workflow hiện tại**, ví dụ `feat/v2-1-proof-gated` (không bắt buộc nếu người dùng đã chọn branch khác).
- Kiểm tra `.env`, `.env.local`, deployment files, secrets; không print giá trị nhạy cảm, không đưa vào test snapshots hoặc progress docs.

### 2.2 BẮT BUỘC: thêm `Proof-Gated-Signing/` vào `.gitignore`

Giả định thư mục PGS nằm **trực tiếp dưới root repo**, thêm dòng dưới vào `.gitignore` root (giữ các rules cũ):

```gitignore
# Upstream PGS research/reference repository; local-only, never push
/Proof-Gated-Signing/
```

Nếu thư mục ở vị trí khác trong repo, điều chỉnh gitignore path theo vị trí thật và ghi lại. Thao tác idempotent: không tạo nhiều dòng trùng. **Đừng xóa thư mục**, đừng thay `/.gitignore` thành file mới rỗng.

Kiểm tra:

```bash
git check-ignore -v Proof-Gated-Signing/README.md
# kiểm tra những file đã bị git track trước khi thêm ignore:
git ls-files -- Proof-Gated-Signing
# kiểm tra có bị stage nhầm không:
git status --short --ignored
```

Nếu PGS đã được track bởi **root repository**, `.gitignore` KHÔNG tự làm nó ngừng track. Sau khi kiểm tra đúng path và xác nhận đó chỉ là local vendor code, dùng:

```bash
git rm -r --cached -- Proof-Gated-Signing
```

Lệnh trên **chỉ untrack trong Git index**, giữ file trên máy. Nếu là git submodule hoặc đã có commit chứa thư mục, phải khảo sát `.gitmodules`/history trước; không dùng lệnh xóa bừa. Nếu vendor đã push trước đây, `.gitignore` **không xóa khỏi lịch sử** — cần báo cáo và xử lý lịch sử riêng nếu có secret/license concern. Dùng `git check-ignore` + `git ls-files` để xác nhận.

**Acceptance (Git):** root `.gitignore` có đúng rule; `git ls-files -- Proof-Gated-Signing` rỗng (trừ khi đã phát hiện submodule cần review); `git check-ignore -v` báo ignore rule; PGS folder vẫn còn local.

### 2.3 Đọc dependency graph và tìm code V1 thật

Sử dụng tool hiện có (`rg`, `find`, IDE search) để xác định tất cả entrypoints, network configs, migrations và tests. Gợi ý lệnh **chỉ để khảo sát**:

```bash
ls -la
find . -maxdepth 3 -type f \( -name 'pyproject.toml' -o -name 'requirements*.txt' -o -name 'foundry.toml' -o -name 'package.json' -o -name 'docker-compose*.yml' \) -not -path './Proof-Gated-Signing/*'
rg -n 'PolicyVault|executeApprovedSwap|EIP712|Attestor|calldataHash|SDE|Simulation|EconomicRisk|OutcomeMonitor|dailySpent|nonce|replan|exposure|ProofEngine|z3' --glob '!Proof-Gated-Signing/**' .
```

Nếu Windows không có `find`, dùng PowerShell `Get-ChildItem -Recurse`, hoặc IDE project search. Lưu **actual** paths và symbols; không mặc định `backend/app/...` hoặc `contracts/src/...` tồn tại.

**Bắt buộc đọc và map tối thiểu:**

| Khối | Phải tìm trong code | Bằng chứng cần lưu |
|---|---|---|
| Owner Mandate | owner auth, policy version, hard caps, pause/revoke | files + tests + storage/events |
| Planner / Task Alignment | typed intent, fail-closed, prompt injection fixtures | routes/handlers/models |
| Transaction Builder | exact ABI, selector/path/recipient, canonical hash | builder method + vectors |
| Simulation | fork/local, exact execution path, traces, state snapshot | harness/trace/sample |
| Evidence / Risk | balance deltas, fee/oracle/exposure | logic + units + policy |
| SDE / Attestor | approve decision, signer access, EIP-712 bytes | decision and signing gate |
| Vault / adapter | allowances, balances, nonce, daily caps, test router | Solidity + Foundry tests |
| Monitor / Store / UI | receipt, reorg, statuses, DB schemas, dashboard | component/API mapping |
| CI / deployment | test commands, env names, chain IDs, addresses | scripts/workflows and output |

Tạo `docs/migration/v2_1_repository_inventory.md` với trạng thái từng hạng mục: `IMPLEMENTED_TESTED`, `IMPLEMENTED_UNTESTED`, `PARTIAL`, `MISSING`, `UNKNOWN`. Ghi paths đúng repo, references đến test, version/commit hash (không copy secrets). Phân biệt V1 *thiết kế* với V1 *thực thi*.

### 2.4 Chạy baseline trước khi sửa code

- Xác định command thật từ README/scripts/config trước, không tự đoán. Ví dụ khi thực tế sử dụng Foundry/Python/Node: `forge test`, `pytest`, `npm test`, `npm run build`; nếu command khác, dùng command repo thực tế.
- Chạy local/fork smoke cho **V1 normal swap + minOut revert + replay + concurrent daily spend + exposure rejection** khi harness hỗ trợ.
- Ghi baseline: passing/failing tests, coverage nếu có, Foundry gas, pre-sign latency, UX/API response, deployment address đã xác thực, tool versions (không chứa private config).
- Nếu test hiện có fail: **phân loại baseline failure** và giữ record, không biến migration thành cuộc rewrite sửa tất cả thứ không liên quan.

**Exit gate Phase 0:** inventory và baseline thật có thể kiểm tra lại; PGS ignored; xác định các điểm chèn `EffectEvidenceV2`, `PGSProofEngine`, `ApprovalV2` và `PolicyVaultV2` trong code hiện có.

---

## 3. PHASE 0B — AUDIT PGS LOCAL SOURCE TRƯỚC KHI THAM KHẢO (P0)

Repo paper PGS công khai có các điểm tham khảo: `pgs/guard.py` (logic policy/check/postcondition), `pgs/chain.py` (chain simulator adapter), `contracts/Testbed.sol` (local test wallet), `tests/` và `eval/`. **Phải dùng local folder để xác minh paths/file version trước khi trích thuật toán**; nếu local clone khác, report khác biệt và đọc theo file thực tế.

### 3.1 Mapping cần lập

Tạo `docs/migration/v2_1_pgs_reference_map.md`:

| Tính năng | PGS upstream candidate | Migrate vào project | Quy tắc |
|---|---|---|---|
| Value Policy `L`, `V`, band | `pgs/guard.py`, paper §2 | existing risk policy + typed math helpers | Không copy hàm dùng float nếu security arithmetic cần integer/rational |
| SMT check | `pgs/guard.py` | `proof/check_mode` (hoặc path hiện có) | Match SAT/UNSAT meaning; exact solver query |
| Phi compilation | `pgs/guard.py` | `proof/compiler` | Bound assumptions, canonical ordering, minOut consistency |
| SMT assert/compile | `pgs/guard.py` | `proof/compile_mode` | Chứng minh actual signed Phi ⇒ policy |
| Simulated effect extraction | `pgs/chain.py` | extend V1 Simulation/Evidence | Không thay Foundry/Anvil harness chỉ vì upstream dùng Hardhat |
| On-chain postchecks | `contracts/Testbed.sol` | extend V1 PolicyVault | **Không** sao chép unguarded `execute` |
| Drift/replay/property tests | `tests/`, `eval/` | reuse/adapt test scenarios | Preserve same threat assumptions; don't copy statistics |

### 3.2 Những cảnh báo phải ghi trong báo cáo

- PGS reference testbed là local Hardhat, không phải deployment/security audit trên Avalanche Fuji.
- Upstream README nêu **key custody không được triển khai đầy đủ**: test wallet có cả guarded và unguarded execution entrypoint; **tuyệt đối không port đường bypass**.
- Paper proof dựa trên trusted code, tracked tokens đúng, price bands hợp lệ, policy đúng, wallet enforcement đúng; không phải on-chain SMT verifier.
- PGS upstream dùng **per-session realized loss logic**; bản V2.1 của dự án thay bằng **certified worst-case risk debit** với hạn mức on-chain; đây là **adaptation**, không phải triển khai chính xác nguyên session model của paper.
- Đọc `LICENSE` và `NOTICE` local; upstream repo hiển thị Apache-2.0. Nếu copy đáng kể code, giữ các notices/attributions bắt buộc theo license. Ưu tiên tự implement interface mỏng dựa trên phương pháp và test fixtures.

**Exit gate:** source map với local paths/commit, thuật toán/assumption cần tham khảo, những phần KHÔNG port, license notes.

---

## 4. KIẾN TRÚC ĐÍCH TỐI GIẢN — KHÔNG ĐẺ MODULE THỪA

### 4.1 Thành phần và ownership

| Component | Action | Only responsibility | Không được làm |
|---|---|---|---|
| `MandateManager` | EXTEND | owner policy/version, hard caps, sessions | Agent tự sửa policy |
| `Planner` | KEEP | đề xuất intent | ký / chọn arbitrary calldata |
| `TaskAlignmentShield` | KEEP | intent-level verdict | cấp quyền execution |
| `TransactionBuilder` | EXTEND MINIMAL | exact swap call + canonical fingerprint | decode arbitrary LLM call |
| `SimulationEngine` | EXTEND | simulate exact vault path + stress fixtures | là source-of-truth final chain state |
| `EffectExtractor` | EXTEND | trusted deltas/allowances/state provenance | lấy log Transfer thay balanceOf như bằng chứng duy nhất |
| `RiskEvaluator` | EXTEND | policy eligibility, fee, exposure, freshness, reporting | tạo bản copy SMT policy logic tùy tiện |
| **`PGSProofEngine`** | **NEW ONE SUBSYSTEM** | SMT Check, compile Phi, SMT Compile, certified risk bound | sign hoặc APPROVE cuối cùng |
| `SDE` | EXTEND | tổng hợp mandatory gates, SINGLE APPROVE | trả APPROVE khi UNKNOWN |
| `Attestor` | EXTEND | ký immutable approved payload, revalidate binding | public arbitrary signing |
| `Relayer` | EXTEND | submit immutable signed call, reconcile | thay đổi swap/Phi trong flight |
| `PolicyVault` | EXTEND ON-CHAIN | verify, restricted execute, atomic Phi + budgets | unguarded Agent execute, generic call |
| `OutcomeMonitor` | EXTEND | proof/tx/counter audit, reorg/pending | suy diễn tx success trước receipt |
| `ExperienceStore` | KEEP | reason-coded planner hints | sửa deterministic policy/SDE |
| UI | EXTEND | rõ proof status/counters/coverage | hiển thị APPROVED = CONFIRMED |

**Đừng tạo:** `PolicyEngine` và `EconomicRiskEvaluator` cùng tính loss độc lập; `PolicyBoundGenerator` bên cạnh Compiler; `SessionBudget.sol` executor tách khỏi vault; `PostConditionGuard` là contract dùng để gọi swap; hai monitor, hai signer, hai orchestrator.

### 4.2 Module layout là chỉ dẫn logic, không ép chuyển repo

```text
<EXISTING BACKEND>/
  <existing models>/           + MandateV2, EffectEvidenceV2, Phi, ProofArtifact, ApprovalV2
  <existing risk>/             + shared ValuePolicy / price-band validation
  <existing simulation>/       + exact-path effects
  <existing evidence>/         + tracked-asset completeness
  proof/                       # ONE new package (có thể nested đúng convention)
    models.py                  # exact typed inputs/outputs
    encoder.py                 # policy constraints / SAT witness
    check_mode.py              # simulated effects check
    compiler.py                # canonical Phi
    compile_mode.py            # Phi ⇒ ValuePolicy proof
    risk_bound.py              # worst-case debit certification
    orchestrator.py            # one entrypoint + resource/time limits
  <existing decision>/         + proof mandatory gate
  <existing attestation>/      + ApprovalV2 canonical signing
  <existing execution>/        + Phi relay + receipts
  <existing persistence>/      + proof/session migrations
<EXISTING CONTRACTS>/
  PolicyVault.sol              # extend existing contract architecture
  libraries/PostConditions.sol    # optional internal library IF needed
  libraries/SessionRisk.sol       # optional internal library IF needed
<EXISTING FRONTEND>/           + proof and budget info
```

Tạo thư viện Solidity internal **chỉ** khi có lợi cho audit/tests/size; một file vault có các internal functions rõ ràng vẫn chấp nhận được. `proof/` có thể 4–7 file, **không** cần 4 services/processes hay 4 HTTP endpoints.

### 4.3 Giao diện nội bộ tối thiểu (pseudo-contracts, không ép ngôn ngữ)

```text
build(intent, mandateSnapshot) -> ExactSwapCall {chainId, vault, adapter, tokenIn,
  tokenOut, amountIn, minOut, recipient, deadline, calldataHash}

simulate(exactCall, snapshotContext, guardedSimulationSetup) -> SimulationArtifact
extract(simArtifact, registry, before/afterReads) -> EffectEvidenceV2
risk_assess(effects, portfolio, mandate, priceBands) -> EconomicEligibility
proof_engine.prove(effects, valuePolicy, priceBands, sessionContext, exactCall)
    -> ProofResult {checkVerdict, compileVerdict, riskBoundVerdict, Phi,
                    postConditionsHash, riskDebit, queryHashes, modelVersion, sourceHashes}

sde.decide(alignment, simulation, risk, proof, call, chainContext)
    -> ImmutableDecision
attestor.attest(approvedDecisionId) -> ApprovalV2 + signature
relay(approvedSignedCall, Phi) -> chainTxHandle
monitor(chainTxHandle) -> Confirmed/ProtectedRevert/Pending/Unknown
```

All hashes and IDs must join to same **immutable** intent/call/evidence/policy/version/context; không nhận arbitrary payload thay thế bằng proof ID do client tự nhập.

---

## 5. PHASE 1 — POLICY, ORACLE, UNITS, EFFECT EVIDENCE (P0)

### 5.1 Canonical money and token units

- ERC-20 deltas là signed integer **base units**; MockUSDC thường 6 decimals, MockWAVAX 18; **đọc/validate từ deployed mock contract và registry**, không chỉ tin ví dụ trong docs.
- `usdE8` là integer (1 USD = `100000000`); giá cũng dùng documented fixed-point scale. Trên Python dùng `int`, `Fraction` hoặc `Decimal` với explicit rounding; Z3 dùng `RealVal`/`Q` hoặc exact rational normalization, **không Python float** trong safety assertion.
- EVM ABI uint256/int256 bounds, overflow, signed delta khi before > after, ceil debit, floor inflow, oracle decimals, token decimals phải có centralized conversion tests.
- Hash canonical **ABI/EIP-712 bytes**, không hash JSON stringify/`str(dict)` hoặc dynamic `abi.encodePacked` mơ hồ.

### 5.2 `TreasuryMandateV2` và session config

Giữ các trường V1 thật; bổ sung tương đương các trường design V2.1:

```text
owner, vault, chainId=43113, version, policyHash, status, expiry
allowedTokens, allowedAdapters, allowedSelectors, allowedSwapPairs
maxUSDCPerSwapBaseUnits, maxDailyUSDCSpendBaseUnits
maxWAVAXPerSwapBaseUnits  # mới cho chiều reverse: owner-configured
maxWAVAXExposureBps (=2500 chỉ khi owner thực sự đã chốt như V1)
maxSlippageBps, maxDailyExecutionCostUsdE8, maxReplans
maxRelativeLossBps, maxFixedLossUsdE8, oracleBandBps
postconditionToleranceBps, maxOracleAgeSeconds
sessionRiskLimitUsdE8, globalDailyRiskLimitUsdE8
trackedAssetsRegistryVersion / registryHash
oracleSource/feeds + provenance
featureFlags.enforceExposureOnchain (default false, explicit)
```

**Policy freeze:** Không dùng trực tiếp default paper `s=3%`, `f=$25`, `session=$5k` làm owner defaults. Nếu cần fixtures, đặt trong `tests/fixtures/...` với prefix `TEST_ONLY_`, không tự seed production signer.

**Budget scopes:** `daily USDC spent` = USDC **input** đã spent (đừng lầm với USD notional). Với chiều WAVAX→USDC, enforce owner-configured `maxWAVAXPerSwap` (hoặc runtime notional oracle guard nếu đã triển khai), không dùng daily USDC input cap như thay thế. Đối với global daily risk, thời gian UTC `block.timestamp / 86400`. Multi-day slow drain vượt scope daily cần nêu rõ.

**Owner session rules:** owner-only create/configure/revoke, sessionId immutable & bound to policy/vault/chain, session expiry/startsAt, no agent rotation; không reset usage của sessionId đã dùng; global daily risk cap vẫn áp dụng xuyên session.

### 5.3 Value Policy chính xác

MVP tracking set `A = {MockUSDC, MockWAVAX}`; `payment_credit pi=0` trong swap-only scope. Với normalized token balances:

```text
Delta[a] = afterBalance[a] - beforeBalance[a]  # signed base unit
L(Delta,p) = -Σ Delta[a] * p[a]                   # unexplained modeled loss (USD)
V(Delta,p) =  Σ max(-Delta[a], 0) * p[a]           # outgoing modeled value (USD)
Pass relative policy iff L <= s * V + f
```

`0 <= s < 1`, `f>=0`, all prices >0, non-empty valid bands; `pi=0` only; if extending payments, model properly instead of implicitly assuming credit. Off-chain `EconomicRiskEvaluator` consumes this **same** definition (or shared helpers), solver owns formal encoding; do not implement two formulas silently differing in rounding/decimals.

### 5.4 Oracle evidence

Required: source ID, token list/address/chain, price nominal/low/high, scale, timestamp, readBlockNumber/readBlockHash if available, TTL, oracle policy version, canonical hash. Controlled test oracle on Fuji is acceptable for demo **when labelled controlled**.

Pre-sign validation:

```text
0 < pLow <= pNominal <= pHigh
band not empty; all priced assets covered; decimals validated
source allowlisted; age <= configured TTL; snapshot context consistent
no NaN / float / malformed/unbounded inputs; no hidden default price
```

**Critical:** Check `SAT(PriceAssumptions)` before accepting `UNSAT` safety query; else a contradictory/empty band can yield vacuous success. Include anti-zero-band/stale/unknown asset tests. Snapshot across multiple RPC calls must be block-pinned or detect inconsistent block hash and abort/retry.

### 5.5 Tracked assets completeness + effects

`EffectEvidenceV2` should include:

```text
intentId, chainId, vault, policyHash, exactCalldataHash
stateBlockNumber + stateBlockHash, time, simulatorVersion, adapterVersion
trackedRegistryHash, asset list (unique ordered), before/after balance reads, delta
observed allowance pairs & before/after; structural checks
unexpectedTransfer/unpricedAssetFlow flags, baseline result, stress artifact refs
oracleEvidenceHash, simulation execution context, evidenceRoot
```

- **Before and after `balanceOf`** authoritative for token deltas; logs/traces are supplementary. Track **owner-required registry**, not only `Transfer` events or assets the simulator happens to observe.
- Prevent alias/duplicate addresses, decimal conflicts, missing asset, missing allowance, unknown spender. If token side effects can't be measured correctly, reject rather than omit.
- Strict mapping to actual execution: simulator must execute the **same vault/adapter semantics** that relayer will use. For signed PDR in preflight, use a documented local test-attestor/guarded simulation route on isolated fork, preserving authorization checks; never simulate a fundamentally different unguarded wallet path and claim parity.
- Define `AssetCoverageManifest` as mandatory registry metadata. Runtime vault must check `Phi.assetSet == RequiredTrackedAssets(policyRegistry)` or prove via an explicitly tested restricted adapter invariant that omitted assets **cannot be touched**. For MVP prefer **exact set equality** to avoid ambiguity. Bound array lengths.

### 5.6 Policy coverage map (NEW DOCUMENT, không cần microservice)

Create `docs/security/policy_coverage_v2_1.md`:

| Policy | Pre-sign enforcement | Runtime enforcement | SMT formally proven? | Claim |
|---|---|---|---|---|
| Actor/router/recipient | builder/SDE | vault | no, deterministic | hard on-chain |
| USDC spend/day | backend read | vault atomic | no | hard on-chain |
| Trade amount and reverse amount | builder/risk | vault | no | hard on-chain |
| Value loss in band | Check/Compile | signed Phi | yes, conditional | proof-gated |
| Residual allowance | extractor | vault Phi | deterministic bound | guarded |
| Session certified risk | proof/debit | vault counters | debit upper bound proof | conditional guaranteed under assumptions |
| WAVAX exposure 25% | RiskEvaluator | **off unless explicit guard** | not implied by lower deltas | **pre-sign only by default** |
| Gas/daily relayer expense | budget estimator | relayer/backend controls | no | operational, not session risk |

**Exit gate Phase 1:** all typed schemas exist in repo conventions, owner config validated, numerical/golden fixtures pass, simulation effects complete and pinned, coverage manifest published. No signing path uses partial evidence.

---

## 6. PHASE 2 — ONE PGS PROOF ENGINE (P0)

### 6.1 API contract

```text
prove(
  exactSwapCall,
  effects: EffectEvidenceV2,
  valuePolicy: immutable owner snapshot,
  priceBands: validated oracle evidence,
  sessionContext: owner-authorized chain read,
  timeoutConfig,
) -> ProofArtifactV2
```

Output typed fields:

```text
checkMode: SAT | UNSAT | UNKNOWN
compileMode: SAT | UNSAT | UNKNOWN
riskBound: SAT | UNSAT | UNKNOWN
phi: canonical PostConditionsV2 or null
postConditionsHash: bytes32 or null
riskDebitUsdE8: nonnegative uint256 or null
check/compile/risk SMT-LIB query hashes, model/encoder/solver versions
policyHash, registryHash, oracleEvidenceHash, exactCallHash, evidenceRoot
assumptionSatisfiable: true | false
compiledRegionSatisfiable: true | false
counterexample: sanitized typed values and violated clause (if SAT)
proofStatus: VERIFIED | VIOLATED | INCONCLUSIVE | ERROR
```

Do not return `safe=true` without detailed obligations. Private signed artifacts/SMT files stored in trusted content-addressed storage, DB stores references/hashes.

### 6.2 Solver mode A — Check simulated effects

Given fixed `DeltaSim`, ask solver for a **counterexample**:

```text
exists price p in validated band:
   L(DeltaSim,p) > s * V(DeltaSim,p) + f
   OR sessionRiskUsedOnChain + max(0, L(DeltaSim,p)) > sessionRiskLimit
```

The second disjunct is an **early budget eligibility check**, not the final debit rule. Actual V2.1 authorization charges the later **certified worst-case riskDebit**, and the vault rechecks the signed debit plus global/day cap atomically. Do not compare one stage using realized prior loss while the other uses certified reservations; use the same chain-sourced session accounting model in all stages. If a conservative compile bound exceeds the remaining budget even when simulated loss passes, REPLAN/REJECT before signing.

Also verify other mandatory conditions (notional, structural, exposure, stale) in deterministic prechecks. `UNSAT` is PASS **only after** assumptions confirmed satisfiable; `SAT` means unsafe witness; `UNKNOWN`/timeout/exception = NO SIGN. If budget model is used, do not mistake the future on-chain **certified debit** for realized `Wspent` from the paper.

### 6.3 Compiler mode B — compile Phi

Candidate bound for each asset (in integer **base units**):

```text
if deltaSim[a] <= 0: minDelta[a] = deltaSim[a]
else:                minDelta[a] = floor((1 - tau) * deltaSim[a])
```

For exact-input swap enforce **both** `spent == amountIn` (when adapter contract guarantees that behavior) and `deltaInput >= -amountIn`. For output `minDeltaOut >= max(policyMinOut, compiledPositiveBound)`. Keep only **one effective on-chain output requirement** to avoid inconsistent dual checks. All other tracked assets default `minDelta=0` unless a documented operation requires otherwise. `maxDelta` optional for cases needing upper caps; exposure not proven by lower bounds alone.

Canonical Phi MVP:

```text
PostConditionsV2 {
  balanceBounds: sorted unique [asset, minDelta, optional maxDelta]
  allowanceCaps: sorted unique [(token, spender), maxRemaining]
  receiptBounds: []     # FUTURE, not executed in swap-only MVP
  ownershipChecks: []   # FUTURE, not executed in swap-only MVP
  exposureRule: {enabled: false} OR implemented runtime mode
}
```

Allowances for trusted adapter should end at cap=0 unless token/implementation necessarily requires a justified different policy. `Phi` **must be executable by the deployed vault**; no phantom field counted as protected if vault ignores it.

### 6.4 Solver mode C — prove all accepted executions are policy-safe

Intended obligation:

```text
for all price p in valid band, for all actualDelta obeying Phi:
  ValuePolicy(actualDelta,p) holds
```

Formal check is satisfiability of negation (`SAT` means counterexample). For simple PGS loss model with `0 <= s < 1`, positive prices and **lower bounds on all tracked deltas**, `L - s*V` is non-increasing with `Delta`. Therefore the worst allowed outcome for the relative loss clause is at `Delta = lowerBounds`. Use this **explicit monotonicity lemma with tests and documented assumptions** to reduce nonlinear/unbounded SMT burden:

```text
SMT validate:  exists p in PriceBand such that
  L(lowerBounds,p) > s * V(lowerBounds,p) + f
```

If UNSAT, the clause holds for all actual deltas `>= lowerBounds` **under the lemma**. If there are additional maxDelta/two-sided constraints, receipt credits or nonlinear policy terms, either provide a verified extension proof or fall back to full bound-aware solver; **do not apply monotonicity outside its assumptions**. Do **not** infer portfolio exposure cap from this lemma.

**Vacuous proof prevention:** independently validate `SAT(PriceBand)` and `SAT(PriceBand ∧ D(Phi))`. Compiler must yield a feasible nonempty outcome region under bounded token arithmetic; if not, reject/report `PROOF_INVALID`, not success. If `SAT` with tolerance `tau`, retry once with `tau=0` according to V2.1; still SAT or UNKNOWN → no signature. Note: `tau=0` can harm liveness, record rejection category.

### 6.5 Certified risk upper bound `r`

Prove for every price in band and every Delta accepted by Phi:

```text
L(actualDelta,p) <= r
```

Under the same **proven** lower-delta monotonicity assumptions, maximize `L(c,p)`. With independent positive price intervals, a conservative analytical upper bound is reached by choosing `pHigh` for negative `c` (outflow), and `pLow` for positive `c` (inflow); then **independently verify with Z3 or exact rational evaluator**. For correlated/oracle-constrained bands, use exact optimization or conservative feasible upper bound verified by SMT.

`riskDebitUsdE8 = ceil(max(0, r) * 1e8)` using exact rational rounding **up**. Query `exists p, Delta accepted by Phi : L(Delta,p) > riskDebit`, must be UNSAT after unit normalization. Check uint256 bound/no overflow, no negative debit, no implicit cents-to-e8 truncation. `0` debit only when **provably** worst-case loss ≤ 0; forbid zero from missing proof/unknown price.

**Accounting claim:** on-chain `ΣriskDebit ≤ cap` ensures a conservative **certified risk reservation**, **not** a measurement of realized trading losses. Do not decrease/refund debit from later observed profit unless a separately verified reservation-release protocol is implemented (OUT OF MVP).

### 6.6 Solver implementation and resource safety

- Pin `z3-solver` version in the existing dependency manager/lockfile; keep encoder version in proof artifacts.
- No model-generated SMT scripts or direct user-controlled SMT expression execution.
- Bound tracked assets (MVP exactly two), constraints, arrays, solver time, process memory where supported.
- Distinguish `UNSAT counterexample query` (good), `SAT` (bad), `UNKNOWN` (inconclusive). Solver exception = inconclusive.
- Log deterministic policy/formula/solver query hash and sanitized witness; don't log private keys/secrets/raw injection payload to future planner.
- **Independent validation tests:** exact arithmetic evaluator, corner enumeration fixtures, 6/18 decimal conversions, 0 and boundary values, prices high/low, s=0, s→1 disallowed, malformed/empty bands, huge ints, timeouts.
- Test that a change in `Phi`, `evidenceRoot`, priceBand, registry, policyHash, solverVersion or calldata invalidates downstream proof/approval (except fields deliberately excluded from cryptographic binding and explicitly documented).

### 6.7 Phase 2 test matrix (must pass)

| Test | Fixture | Expected |
|---|---|---|
| Check-safe | fair swap across band | `UNSAT` with valid assumptions |
| Check-loss | harmful swap for some band price | `SAT`, witness independently verified |
| Solver-unknown | injected timeout/unknown | NO SIGN |
| Contradictory-band | `pLow > pHigh` | INVALID, **not** valid UNSAT |
| Empty Phi region | impossible bounds | INVALID, no signature |
| Compiler too loose | tau causes policy violation | SAT then tau=0 retry or fail |
| Compiler binding | mutate bound after proof | hash mismatch |
| Risk upper bound | known exact rational fixture | bound rounded UP, solver UNSAT |
| Rounding adversarial | USDC6/WAVAX18 extreme values | never under-debits |
| Unsupported asset | registry incomplete | refuse proof |
| Exposure counterexample | delta-only proves value but snapshot exposure fails | independent exposure gate rejects |

**Exit gate Phase 2:** deterministic pure proof package tested without chain, plus real simulation integration returning valid proof + counterexample + invalid/timeout. No signing enabled yet.

---

## 7. PHASE 3 — APPROVALV2, SIGNING AND POLICYVAULTV2 (P0)

### 7.1 Freeze ABI and golden vectors **before** Solidity/backend changes

Define one canonical ABI struct specification, supported in both Python/TypeScript backend and Solidity. Proposed fields (adapt to V1 actual fields, preserve security meaning):

```solidity
// Specification only; implement and version in existing contract
struct ApprovalV2 {
    bytes32 intentHash;
    bytes32 calldataHash;
    bytes32 policyHash;
    bytes32 evidenceRoot;
    bytes32 postConditionsHash;
    bytes32 sessionId;
    uint256 riskDebitUsdE8;
    uint256 nonce;
    uint256 deadline;
    address adapter;
    address tokenIn;
    address tokenOut;
    uint256 amountIn;
    uint256 minAmountOut;
}
```

If evidenceRoot does NOT cryptographically bind price assumptions, asset registry hash, encoder/solver context, risk certificate and Phi, include explicit `proofContextHash` **once** in ApprovalV2. **Do not store two unexplained redundant hashes**. Choose and document **one** concrete binding design; a proof artifact ID that can be remapped in DB is insufficient.

- EIP-712 domain `name/version/chainId/verifyingContract`; `version` must distinguish V2. Old V1 signatures must not be valid in V2.
- Dynamic arrays in Phi: deterministic address ordering, unique assets/pairs, explicit length caps; hash via `keccak256(abi.encode(...))` using a formally specified ABI layout; don't use ambiguous `abi.encodePacked` for arrays.
- Golden fixtures: same test vector hashed in backend and Foundry results in **exactly the same bytes32**; wrong order, duplicate, changed signed value or domain must mismatch.
- `deadline`/`nonce`/policy version bind exact execution context. Changing anything post-sign invalidates signed decision; re-run full checks.

### 7.2 Attestor and SDE protocol

SDE approval requires all:

```text
owner-authorized active mandate + hard limits, TaskAlignment=ALIGNED
exact allowed calldata, recipient=vault, simulation success + fixed stress completed
EffectEvidence complete, consistent and fresh; PriceBand valid/provenance complete
EconomicRisk eligibility PASS, including pre-sign exposure <= owner cap
SMT Check UNSAT; assumption satisfiable
Phi canonical & executable by vault; compiled region satisfiable
SMT Compile UNSAT; certified RiskBound VERIFIED
policy/call/evidence/registry/oracle/proof/Phi/session hashes + versions match
nonce/deadline/budget fresh enough for preflight (vault still rechecks atomically)
```

- Only immutable `APPROVED decision ID` flows into isolated attestor; private signer endpoint must **re-read trusted decision and verify** all immutable IDs/hashes. Never accept arbitrary EIP-712 struct from AI/public API.
- Signing key separated from owner/relayer, never inside LLM context, logs or Git. Restrict chain/vault allowlist, rate-limit, rotate/revoke support and audit each signature.
- `SAT`/`UNKNOWN`/stale/timeout/cancelled/REPLAN/EXPIRED means **attestor receives NO request or refuses request**.
- Relayer must not rebuild call from `intent`; submit stored immutable signed swap and Phi bytes. If calldata/ABI mismatch, abort; never self-correct by editing signed bytes.

### 7.3 Extend existing `PolicyVault` (not a second contract executor)

Preserve V1 owner/admin, EIP-712 PDR, nonces, daily cap, pause/revoke, SafeERC20, nonReentrant, restricted adapter. Add V2-only guarded execution entrypoint (could be `executeApprovedSwapV2`), and ensure **V1 Agent-executable entrypoint cannot bypass mandatory V2 proof**: disable V1 path for V2 deployment or restrict/retire it safely. Admin owner-only withdrawal is a separate recorded trusted escape hatch.

Recommended execution ordering (real code may optimize without breaking invariants):

```text
1. Check whenNotPaused + nonReentrant.
2. Verify EIP712 ApprovalV2 / authorized attestor / domain / chain/vault.
3. Verify active owner policyHash/version, expiry, nonce unused.
4. Verify exact calldataHash & canonical Phi hash against signed PDR.
5. Verify adapter, selector, pair, path, recipient=vault, amountIn/minOut,
   allowed tokens, policy bounds incl. reverse trade cap.
6. Verify session exists/owner-authorized, active, startsAt/expiry, policy bound.
7. Verify daily spend + session risk + global UTC-day risk headroom (checked math).
8. Snapshot ALL mandatory tracked assets and allowance pairs (from owner registry,
   not only signer-provided incomplete Phi); enforce registry ↔ Phi completeness.
9. Approve exactly amountIn; restricted exact-input swap (no arbitrary call).
10. Revoke residual allowance as required; snapshot after balances and allowance.
11. Enforce: input spent exact-in; output >= effective minOut;
    tracked deltas within signed min/max; remaining allowance caps;
    optional runtime exposure only if real feature enabled.
12. Consume nonce, charge USDC daily spend (only USDC input), charge certified
    session/global risk once, emit event with intent/proof/actual deltas.
13. Commit when all pass; any revert rolls back EVM state/counters/events.
```

CEI/reentrancy: exact ordering of nonce/counter updates may differ (before external call often safer) **provided any revert rolls back**, nonReentrant guards and invariants hold. Test callbacks/reentrancy, allowance cleanup, malicious adapter behavior. Limit tracked assets/allowance arrays on-chain to control gas/DoS.

### 7.4 On-chain limits and sessions

```solidity
// design-only invariant, adapt existing storage/access control
require(session.active && session.policyHash == currentPolicyHash);
require(block.timestamp >= session.startsAt && block.timestamp <= session.expiresAt);
require(riskDebit <= session.riskLimitUsdE8 - sessionRiskUsedUsdE8);
require(riskDebit <= globalDailyRiskLimitUsdE8 - globalDailyRiskUsedUsdE8[utcDay]);
if (tokenIn == USDC) {
    require(amountIn <= maxUSDCPerSwap);
    require(amountIn <= maxDailyUSDCSpend - dailySpentUSDC[utcDay]);
} else {
    require(tokenIn == WAVAX && amountIn <= maxWAVAXPerSwap);
}
```

Arithmetic examples above are conceptual; handle underflow guards. `sessionId` must be generated/authorized by owner and bound to policy/vault/chain, not created/recycled by agent. Global daily risk cap remains on session renewal. Event history covers owner policy/session changes, revocations, pauses, trade commitments.

**Risk debit trust boundary:** vault verifies signed debit and cap, **does not prove debit was calculated correctly**. The attestor is trusted to only sign independently certified debit. A compromised attestor can lie within owner hard caps; document as residual risk.

### 7.5 Exposure runtime feature (optional, distinct gate)

`enforceExposureOnchain=false` (default): mandatory **off-chain** projected exposure check stays in RiskEvaluator; UI/report explicitly label `PRE-SIGN ONLY`. No claim of guaranteed 25% ratio under drift.

If owner requests runtime exposure guard and source is credible: compute actual post-trade portfolio using **on-chain trusted oracle** with timestamp/decimals/freshness validation, check 25% with safe fixed-point/cross-multiplication, reject missing assets and stale prices; test price/snapshot drift. Alternative pre-state-aware SMT requires on-chain enforced allowed pre-state envelopes + two-sided deltas; do not implement as a fake flag. **Not required for the core proof-gated swap release** unless explicit feature claim is made.

### 7.6 Deployment and migration from V1

- Determine if V1 vault is immutable vs proxy; **never assume upgradeable storage**. For ordinary immutable deployment, deploy **new PolicyVaultV2 address** on Fuji and migrate test assets via owner-authorized actions, not via direct storage change.
- Recreate owner policy/session, attestor allowlist, tracked assets and adapter. Read on-chain after configuration and compare against expected policy hash.
- Never send mainnet funds or private keys; use mock tokens/test AVAX only. Verify `eth_chainId=43113` at runtime and before each deployment/signing.
- Update backend/frontend to correct V2 contract ABI and deployed address atomically using config/version, not hardcoded scatter across files.
- V1 API consumers requiring old PDR must be rejected or read-only during V2 cutover; avoid sending V1 signature into V2.

**Exit gate Phase 3:** local Foundry tests of PDR/nonce/budget/postcheck pass, Python↔Solidity golden hashes match, correct simulator and relayer use V2 guarded path, no bypass route.

---

## 8. PHASE 4 — INTEGRATE BACKEND/APIs, STATE MACHINE, DB, UI (P1)

### 8.1 Orchestration: one entrypoint

Reuse V1 orchestrator/controller. A single `run_security_pipeline(intentId)` invokes stages and persists status. Proof module is a library/service dependency, **not** a separate public signer. Do not expose `POST /proofs/compile` as a public way to get sign permission.

Minimal state machine:

```text
PROPOSED → ALIGNED → BUILT → SIMULATED → EVALUATED
  → PROOF_CHECKED → CONDITIONS_COMPILED → PROOF_COMPILED
  → APPROVED → ATTESTED → SUBMITTED → CONFIRMED

Terminals/alternatives:
REJECTED | ESCALATED | REPLAN_REQUIRED | PROOF_INCONCLUSIVE
EXPIRED | REVERTED | PENDING_RECONCILIATION
```

- Explicit transition guards + idempotent event keys. `CONFIRMED` only after chain receipt status=1 and selected confirmation policy, not merely txHash. Receipt status=0 → `REVERTED`; `eth_getTransactionReceipt=null` → pending, not failure.
- Chain reorg: store block hash/number and required confirmations; invalidate/reconcile if canonical chain changed.
- Replan max 2 as V1 owner policy, each retry **new** call → full re-sim/proof/sign; repeated protected revert triggers signer quarantine/manual escalation, avoids gas grief.
- State drift between preflight and broadcast: runtime vault is final enforcement; do not trust stale off-chain budget. Good preflight only reduces unnecessary reverted tx.

### 8.2 APIs: backward-compatible-first

Discover actual existing routes first. Extend current endpoint payloads additively where safe. If backend follows V1 FastAPI design, suggested mapping:

| Current/target purpose | API decision |
|---|---|
| mandate / propose / build / simulate / risk / decision | extend existing; add versions if schema breaking |
| proof introspection | `GET /v2/proofs/{proof_id}` authenticated, sanitized |
| proof Check/Compile | **internal functions**; internal-only endpoints **only if** architecture already demands process boundary |
| attest | existing private signer endpoint only, uses immutable approvedDecisionId |
| execute | existing relayer endpoint receives stored ApprovalV2/Phi; no client-supplied arbitrary signed bytes |
| treasury sessions | `GET /v2/treasury/sessions/{id}` reads current chain and stores lastSyncedBlock |
| transaction detail | add proof verdicts, signed Phi, budgets, receipt and reason codes |

Use strict versioned Pydantic/JSON schema, auth/RBAC, input size limits, rate limits for expensive simulations/SMT, no cross-origin public signing. Feature flags must default to `NO_SIGN` if V2 fully enabled but proof config absent.

### 8.3 Persistence migration (idempotent)

Keep V1 tables and migrations intact. Add/extend **only necessary** schema:

```text
proof_artifacts:
  id, intent_id, evidence_root, policy_hash, call_hash, registry_hash,
  oracle_evidence_hash, encoder_version, solver_version,
  check_verdict, compile_verdict, risk_verdict, risk_debit_usd_e8,
  post_conditions_hash, query_artifact_refs, witness_ref,
  status, created_at

compiled_postconditions:
  proof_id, canonical_abi_blob_or_ref, post_conditions_hash, schema_version

sessions_read_model:
  session_id, policy_hash, active, limit_usd_e8, used_usd_e8,
  global_daily_limit/used, last_synced_block/hash   # NON-AUTHORITATIVE

attestations (add): pdr_version, proof_id, post_conditions_hash,
  session_id, risk_debit_usd_e8
executions (add): protected_revert_type, postcheck_results_ref,
  receipt_block_number/hash, confirmations
portfolio_snapshots (add): state_block_hash, registry_hash
```

Never copy full raw SMT traces into hot SQL rows if content-addressed artifacts available. Migrations have upgrade/downgrade or documented rollback; unique constraints on proof/evidence/signature identity and idempotent receipt processing. DB counters are **cache**, on-chain is authoritative for budget.

### 8.4 UI — extend existing dashboard

Display:

- Mandate limits with version, controlled oracle/testnet disclaimers, `enforceExposureOnchain` label.
- Proposal details, TaskAlignment, baseline and stress results.
- PGS pane: `CHECK=UNSAT`, `COMPILE=UNSAT`, bound Phi in readable units, certified risk debit, solver/encoder version, witness if SAT; don't imply SAT is success.
- Sessions: `riskUsed/limit`, global daily risk, USDC daily spend; display **Certified Risk Consumption** distinct from realized modeled loss and gas.
- Timeline: APPROVED vs ATTESTED vs SUBMITTED vs CONFIRMED/REVERTED/PENDING. Fuji explorer link only from actual verified tx hash.
- Reason-coded no-sign and protected revert; no unexplained green checkmark for `PROOF_INCONCLUSIVE`.

UI is **presentation** of security protocol and cannot implement substitute approval logic.

**Exit gate Phase 4:** full local end-to-end trace persisted, meaningful statuses, no frontend bypass, DB migration works on existing data, backward-compatible functions confirmed or documented breaking changes.

---

## 9. PHASE 5 — SECURITY TEST PLAN / PROPERTY / FUZZ / DRIFT (P0 RELEASE GATE)

### 9.1 Priority scenarios — **MUST PASS**

| ID | Setup | Required assert |
|---|---|---|
| N1 | Legitimate swap, fresh oracle, valid budget | Check UNSAT + Compile UNSAT + risk verified → signed → committed (local and Fuji if available) |
| N2 | Better-than-simulated output | Transaction succeeds if all signed bounds satisfied |
| P1 | Prompt injection asks attacker recipient | Shield reject; builder/vault deny even if Shield mocked to miss |
| V1-R | Replay/changed router, calldata, tokens, nonce, policy, deadline, chain | Reject as V1, no regression |
| D1 | Reserve shift undercuts effective output bound | `PROTECTED_REVERT`; no token movement; relayer gas may be charged |
| D2 | In-tolerance drift, Phi still holds | Confirm; avoid false revert |
| D3 | Output >= old V1 `minOut` but **Value Policy fails** | V2 tighter Phi/SMT refuses or vault reverts; demonstrate incremental value |
| D4 | Unauthorized loss of other tracked asset | Postcondition revert; registry completeness tested |
| S1 | Residual allowance over cap | Revert, no retained allowance/counters on revert |
| B1 | Concurrent PDR daily spend: 700 + 200 + 200 > 1000 | At most one 200-USDC trade succeeds |
| B2 | Multiple small in-policy trades exceed session risk cap | Last signed attempt cannot commit over budget |
| B3 | Agent invents/reuses/revokes session or owner rotates policy | Rejected; global daily cap not bypassed |
| B4 | Two sessions each debit under local cap but global/day exceeded | Global cap blocks second/extra |
| B5 | Postcondition revert after precheck budget | nonce/session/global/daily counter unchanged |
| E1 | V1 7,700 USDC + $2,300 WAVAX, buy 500 | `REPLAN` exposure 28% > 25%, no PDR |
| E2 | Pre-sign exposure passes, inclusion state drifts >25% | If runtime feature OFF: report limitation; ON: must revert |
| Z1 | Solver finds counterexample | SAT witness independent evaluation; NO SIGN |
| Z2 | Unknown/timeout/invalid band/proof/Phi mismatch | NO SIGN |
| Z3 | Deliberately mutate ProofArtifact/hashed context between SDE and signer | Attestor rejects |
| O1 | Stale/missing/invalid oracle or price band | NO SIGN |
| T1 | Unsupported token/fee-on-transfer/rebasing/unpriced assets | Reject unless semantics explicitly supported |
| G1 | Repeated protected reverts/spam | max replan/rate limit/quarantine, gas logged |
| A1 | Agent attempts arbitrary signer payload / owner method | No unauthorized signature or admin action |
| C1 | Full V1 workflow baseline | Stable functional behavior |

**Tests must verify actual token balance deltas, nonce, risk counters and receipts, not only error strings.** For reverts, check state **same as pre-tx** (gas cost separate), because reverting a transaction does not reverse earlier confirmed transactions.

### 9.2 Pure formal/property tests

- Enumerated/rational model vs Z3 equivalence for simple 2-token value model; SAT witness must violate the exact policy.
- `UNSAT` never accepted with contradictory price bands, bad units or infeasible Φ region.
- For randomly sampled `Phi` satisfying assumptions: any accepted Delta and valid prices obey value policy and risk debit cap.
- `Phi` canonicalization order-independent before sorting, deduplicated, length-limited; any attempted tamper post-sign rejects.
- `used <= limit` is invariant after all successful executions; race budget overdraw impossible; session ID monotonic usage.
- Unexpected balance loss from tracked registry violates checked Φ; asset omitted by signed Phi is rejected at runtime.
- Check signed int arithmetic, uint boundaries, decimals 6/18, mixed price scaling, zero/large values, deadline boundary, stale block, reorg/pending.
- Malicious swap adapter reentrancy/callback, unauthorized approvals, target/selector mismatch, `forceApprove` behavior.
- PDR v1 cannot execute a v2 transaction through legacy entrypoint or with altered domain; owner admin path doesn't become Agent execution path.

### 9.3 Foundry / backend integration / e2e

- **Foundry:** unit, fuzz, invariants for contract accounting and permission; compare post-state token balances. Use `forge test -vvv` if repo uses Foundry.
- **Backend:** schema validators, fee/oracle freshness, proof engine, signer isolation, typed errors, persistence/idempotency; use repo's real test framework.
- **Cross-language fixtures:** backend ABI hash vs Solidity `keccak256(abi.encode(Phi))`, EIP712 digest/signature known vectors.
- **E2E local:** simulate through **same `PolicyVaultV2` protected path**, sign test PDR, submit, monitor; deterministic oracle and mock pool states.
- **Fuji:** owner config, normal guarded swap, controlled adverse state causing guarded revert, replay/tamper, session cap; **only when credentials exist and after local pass**. Record on-chain IDs and RPC confirmation policy.

### 9.4 Minimum CI gates

- Dependency install from lockfile; lint/typecheck; unit tests; security-focused Foundry tests; backend↔Solidity ABI vectors; integration test with local chain; frontend build (if current repo has it).
- No CI dependency on `Proof-Gated-Signing/`; CI must pass after clone **without** local reference folder.
- No real secrets in CI logs; use deterministic private test accounts/local mocks. Do not require live Fuji RPC for every PR (separate opt-in smoke).
- Existing V1 tests must remain passing or have a documented, intentional, correctly versioned breaking change with replacement tests.

---

## 10. PHASE 6 — BENCHMARK / ABLATION / PERFORMANCE / RELIABILITY (P1 RELEASE GATE)

### 10.1 Fair ablation, use FULL V1 baseline

| Config | Included | Expected question |
|---|---|---|
| A `FULL_V1` | **Entire existing V1** including Task Alignment, Risk Evaluator, existing vault minOut/day/nonce/allowlist | Baseline actual safety |
| B `V1_PLUS_PHI` | A + broader tracked balance/allowance postchecks; no SMT proof | Guard expansion value |
| C `PGS_CORE` | B + SMT Check/Compile + proof-bound PDR | Formal verification incremental value |
| D `V2_1_CORE` | C + certified session/global risk budget | Slow-drain/race protection |
| E `EXPOSURE_RUNTIME` | D + optional on-chain exposure guard | Exposure drift protection and cost |

**Không tắt TaskAlignment trong A rồi thêm lại ở E**: nó đã có trong V1. Match attack fixtures, initial chain state, mandates, attack capability, oracle source and transaction validity. If full V1 can't be executed (broken tests), mark A unavailable; do not reconstruct a weaker fake baseline.

### 10.2 Metrics và reporting

Record per scenario:

```text
attackFamily, config, seed, setupBlock, policyVersion, actualResult
preSignRefuse / protectedRevert / unsafeSuccessful / benignConfirmed
attackerGain (defined independently from safety policy), actualTokenDeltas
certifiedRiskDebit, modeledRealizedLoss (explicit formula), budgetRemaining
sim_ms, extract_ms, SMT_check_ms, SMT_compile_ms, riskbound_ms
attest_ms, relay_ms, confirm_ms, endToEnd_ms
solidityGasUsed, deltaGasVsV1, revertGas, retryCount, solverUnknown
```

Aggregate APR/BPR with denominators, per-family outcomes, false-positive rate, worst-case and p50/p95/p99 latency; report environment CPU/RPC/solc/optimizer/network. Define APR/BPR clearly (harmful scenarios prevented, benign scenarios successfully allowed). No inherited paper percentages and no claiming statistically significant wins from tiny fixture sets.

### 10.3 Stability / liveness controls

- Benchmark tradeoff `oracleBandBps × toleranceBps × maxRelativeLossBps × fixedLoss` on same benign suite; record false rejections.
- Test very conservative Phi causing too many protected reverts, and show why fallback tau=0 is safe but can reduce liveness.
- Compare `Σ certified debit` vs **actual modeled realized loss** to quantify over-reservation; don't call risk budget actual PnL.
- Timeout budgets for external RPC/simulation/solver; limited retries with exponential backoff for retriable infrastructure only, never repeat a signed execution blindly when receipt is unknown (check chain nonce/tx hash first).
- Measure gas for Phi array length, two tracked assets and allowance; forbid unbounded arrays in public calldata.

**Exit gate Phase 6:** report with actual numbers, provenance commands and known limitations; no performance promise without data.

---

## 11. PRIORITY, DEPENDENCIES VÀ ITERATION ORDER

| Order | Package | Depends on | Deliverable | Completion gate |
|---:|---|---|---|---|
| 0 | Repo inventory, V1 baseline, PGS ignore | none | inventory + baseline + `.gitignore` | paths/tests/ignored verified |
| 1 | PGS local study, source map and licenses | 0 | source map | reference assumptions understood |
| 2 | Policy/schema/units/oracle + registry | 0 | canonical typed model | golden conversion/validation tests |
| 3 | Simulation/effects upgrade | 2 | trusted complete evidence | exact path + block consistency |
| 4 | Proof Engine pure | 2,3 | check/compiler/compile/risk | SAT/UNSAT/UNKNOWN, corner tests |
| 5 | Canonical Phi/PDR golden vectors | 2,4 | ABI spec & vectors | Python/Solidity parity |
| 6 | Vault V2/atomic budget checks | 5 | contracts + Foundry | access/replay/budget/drift tests |
| 7 | SDE/signing/relayer integration | 4,5,6 | guarded E2E | only verified proof signed |
| 8 | Persistence/monitor/frontend | 7 | traceable UI | statuses and counters correct |
| 9 | Fuji deployment/smoke (external creds) | 7,8 | tx receipts + on-chain evidence | confirmed chain records |
| 10 | Ablation/performance/release audit | 7,8,9 if available | report + gates | compare FULL V1, no unjustified claims |

**Parallelizable:** pure proof tests and Foundry postcondition helpers after freeze of ABI/schemas; dashboard schema can be prepared after state machine contract. **Not parallelizable without freeze:** Python/Solidity signing schema. Agent nên hoàn thành các small milestones để giữ V1 runnable throughout.

### 11.1 Task-size discipline

- Mỗi commit/PR logic nhỏ: `gitignore/inventory`, `policy/schemas`, `effect extraction`, `proof engine`, `ABI + Vault`, `signer/relayer`, `monitor/UI`, `tests/benchmark`.
- Trước khi đổi API/ABI: search all callsites, update types/tests/migrations/contract fixtures trong cùng change set.
- Không rename hàng chục file không liên quan, không refactor planner/frontend chỉ để “cho sạch”.
- Nếu gặp một risk model duplication: extract shared pure utility **từ code đang chạy**, deprecate duplicate sau khi tests pass.
- Dependencies mới phải giải thích vì sao cần, pin version, cập nhật lockfile. Không import whole upstream testbed chỉ để dùng một function.

---

## 12. RELEASE GATES — CHỈ ĐÁNH DẤU COMPLETE NẾU ĐẠT

### Gate A — Baseline và migration discipline

- [ ] `Proof-Gated-Signing/` ignored và không track; local reference vẫn tồn tại.
- [ ] Có verified repo inventory và full V1 baseline tests; không claim từ design doc.
- [ ] Diff tối thiểu; không duplicate SDE/signer/executor/monitor.
- [ ] Legacy V1 security invariants còn hiệu lực.

### Gate B — Formal correctness

- [ ] SAT/UNSAT/UNKNOWN handled correctly; empty assumptions/empty Phi rejected.
- [ ] Loss formula/units/tolerance được cross-check bằng independent exact arithmetic.
- [ ] Compiled `Phi ⇒ ValuePolicy` certificate có source-bound query/version/assumptions.
- [ ] Risk debit upper bound certified & rounded upward; never negative.
- [ ] Tracked assets complete; canonical sorted ABI; all hashes match golden vectors.

### Gate C — Signing / on-chain

- [ ] No valid Agent path without current ApprovalV2; no owner/admin bypass under Agent identity.
- [ ] Attestor re-verifies immutable SDE APPROVED artifact and refuses arbitrary payload.
- [ ] Mutated calldata/Phi/session/policy/chain/nonce/expiry rejects.
- [ ] Input/output/tracked asset/allowance conditions atomically enforced.
- [ ] Daily spend + session/global risk are atomic under concurrency and roll back on revert.
- [ ] Reverse WAVAX trade hard cap defined/enforced or feature safely disabled.
- [ ] No unconditional 25%-exposure guarantee asserted when runtime guard disabled.

### Gate D — End-to-end and resilience

- [ ] Agent → simulation → proof → attestor → vault → monitor works locally.
- [ ] Normal Fuji guarded swap and postcondition revert proven with **real** tx hashes when infrastructure available; otherwise report blocked.
- [ ] UI and database reflect proof status, signed Phi, risk debit, chain counters, protected reverts and pending receipts.
- [ ] Missing RPC, stale price, solver timeout, receipt uncertainty and reorg never produce false APPROVE/CONFIRMED.
- [ ] CI installs fresh from repo without PGS reference directory.

### Gate E — Performance + honest claims

- [ ] FULL V1 vs V2.1 ablation uses same test cases and reports gas/latency/benign pass/reject metrics.
- [ ] Demonstrated incremental value beyond V1 minOut (e.g. valued-loss, tracked-asset drift, cumulative certified risk).
- [ ] No prediction of real-world APR from paper; clear testnet, controlled oracle, unaudited scope.
- [ ] All test/compile/build commands and outputs included in final report.

### Final delivery artifacts in project repo

```text
docs/migration/v2_1_repository_inventory.md
docs/migration/v2_1_pgs_reference_map.md
docs/migration/v2_1_progress.md
docs/security/policy_coverage_v2_1.md
docs/security/proof_assumptions_v2_1.md
docs/security/abi_hash_vectors_v2_1.md  # or machine-readable fixture + companion doc
docs/evaluation/v1_vs_v2_1_ablation.md
# code + tests + migrations + CI changes in actual existing repo layout
# root .gitignore contains /Proof-Gated-Signing/
```

**Final agent message MUST include:** (1) what was reused vs added, (2) actual files changed, (3) test commands + counts + failures, (4) new contract address/tx hash if truly deployed, (5) unresolved assumptions/blockers and exact next action, (6) confirmation local PGS folder is not Git-tracked.

---

## 13. SECURITY REVIEW CHECKLIST — DESIGN PITFALLS TO AVOID

| Risk | Why it matters | Required mitigation |
|---|---|---|
| V1 already has minOut | Fake PGS superiority if demo only minOut revert | Add tests that V1 passes but ValuePolicy/Φ rejects |
| `UNSAT` with unsatisfiable band | Vacuous truth | SAT assumptions first, validated ranges |
| Φ omissions | Untracked wallet asset losses | Registry↔Phi completeness enforced |
| Loss policy not exposure policy | Lower deltas don't bound post-trade portfolio share | Explicit pre-sign only or runtime oracle guard |
| USDC-only amount cap in reverse trade | WAVAX→USDC can trade large notional | Owner-configured reverse hard cap / disabled until defined |
| Certified risk ≠ realized loss | Unnecessarily low throughput or misleading UI | Show reserved vs realized separately, measure over-reservation |
| Reverted tx still costs gas | Gas grief not budgeted by riskDebit | Relayer cost caps, replan limit/quarantine, track gas |
| Signer trusts DB ID | Mutable artifact could be swapped after proof | Immutable content hashes, signer revalidation |
| Crypto digests mismatch | Python/Solidity type/canonical order conflict | EIP712/ABI golden vectors + tamper tests |
| Simulation bypass | Proof models different execution from actual vault | Same guarded V2 path with documented fork test-attestor |
| Signing from LLM | Full policy bypass | Isolated attestor, no direct key/tools exposed |
| Live Fuji legacy vault | Old deployed bytecode immutable | New V2 vault deploy, explicit migration |
| Paper code copied directly | Upstream unguarded path and local-only assumptions | Port methods/tests not complete wallet, license compliance |
| Session reset / concurrent approvals | Risk budget bypass | Owner-only session, global daily cap, atomic counters |
| Full PGS array generality | Unnecessary gas and complexity in 2-token MVP | Fixed registry, bounded arrays, only active checks |
| Silent optional feature | False guarantee claims | Feature flags + coverage manifest + acceptance gates |
| Unbounded retries | Gas/time abuse | max replans 2, infrastructure retry policy, quarantine |

---

## 14. QUY TẮC XỬ LÝ TRƯỜNG HỢP CHƯA CÓ THÔNG TIN

Không tự đặt thông số để “cho chạy đẹp” rồi gọi đó là owner policy. Phân loại:

1. **Discoverable in code** (routes, deps, deployed config, mock decimals, signer wiring): inspect thực tế, implement tự chủ.
2. **External infrastructure** (Fuji private key, funded account, real RPC credential): không hardcode; làm local tests và report external blocker.
3. **Owner risk appetite** (`s`, `f`, `beta`, `tau`, risk caps, reverse trade cap): lấy từ owner config hiện có nếu có. Nếu chưa có, tạo validated test fixtures và **disable live attestation** đến khi values được xác nhận; giữ toàn bộ code/test chạy được với fixture.
4. **Optional scope** (runtime exposure guard, receipts/ownership, real DEX): tách phase không block core, ghi feature-gated/not implemented, không present là done.
5. **Existing project incompatibility** (Python vs Node backend, Hardhat vs Foundry): giữ stack hiện có, map abstraction; không thêm cả stack chỉ vì paper dùng khác stack.

---

## 15. SOURCE LINKS VÀ TRIỂN KHAI CÓ KIỂM CHỨNG

- Design V1 supplied: `AI_Treasury_Security_System_Design_v1.0(1).md`, sections 2–12; nếu trong repo tên khác, tìm tài liệu tương đương.
- Design V2.1 supplied: `AI_Treasury_Security_System_Design_v2.1.md`, sections 3–18; source of target behavioral rules, **not** implementation evidence.
- Paper: Bravish Ghosh (2026), *Proof-Gated Signing: Solver-Checked Transaction Guards that Hold Under State Drift for Onchain AI Agents*, https://arxiv.org/abs/2610.00354.
- Reference source publicly available: https://github.com/LoopGlitch26/Proof-Gated-Signing (README references `pgs/guard.py`, `pgs/chain.py`, `contracts/Testbed.sol`, `tests/`, `eval/`). **Use local `Proof-Gated-Signing/` for exact code/version before porting**.
- Existing V1: Avalanche Fuji chain ID `43113`, EIP-712 PDR + `PolicyVault`, daily spend and atomic minOut; ensure chain-specific configuration verified at run time.
- For non-mock deployment, review current Foundry, OpenZeppelin, Z3, Avalanche documentation at the specific pinned tool/library version; do not assume a design snippet is compilable or audited.

### SHORT EXECUTION PROMPT (paste into coding agent with this file)

> Read `IMPLEMENTATION_PLAN_V1_TO_V2_1.md` completely. Your task is to **implement V2.1 by modifying the existing V1 project**, not generating a new project. Begin with Phase 0: inspect repository, run V1 baseline, append `/Proof-Gated-Signing/` to root `.gitignore`, ensure PGS isn't tracked. Study local PGS code strictly as read-only reference. Then implement phases 1–6, preserving existing architecture, tests, API behavior and security invariants. Work incrementally, execute tests after each phase, and write the exact progress and blockers in `docs/migration/v2_1_progress.md`. Never claim security properties without tests/proof, never deploy with secret keys unless supplied through secure environment and authorized, and do not copy paper's unguarded wallet path. If external credentials/owner settings are absent, finish everything locally and mark only those external actions blocked. The acceptance gates of this document, not mere code generation, determine completion.

---

**End of implementation specification.** This plan deliberately treats actual V1 repository layout, test status and PGS local clone content as **UNKNOWN until inspected by the coding agent**. It is designed to be safe to hand to an agent that has the actual project checkout and permission to edit it.
