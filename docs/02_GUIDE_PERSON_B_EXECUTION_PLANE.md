# AI Treasury Security — Hướng dẫn triển khai cho Người B

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

> Historical / compatibility document. For the current runtime use [V2.1 system design](AI_Treasury_Security_System_Design_v2.1.md) and [readiness audit](audit/V2_1_READINESS_REVIEW.md). Old A/B layouts, PoC evidence and removed pre-refactor paths describe their original checkpoint; they are not current deployment instructions or new validation evidence. References to removed artifacts are retained as plain code text.

**Vai trò:** Blockchain & Transaction Verification / Execution Plane  
**Phiên bản:** Team split v1.1 — 16/11/2026  
**Deadline demo:** 20/11/2026 (21/11 dự phòng/submission)  
**Tài liệu bắt buộc đọc cùng:** `03_SHARED_INTEGRATION_CONTRACT.md` — nguồn chuẩn duy nhất cho API, schema, hash và EIP-712.

> **Mục tiêu:** Người B chạy được **một giao dịch mock USDC → WAVAX có policy-enforced execution**, xuất typed evidence cho A và nhận PDR để thực thi. Bạn không phải đợi AI/SDE của A: dùng `TransactionProposal` fixture và local test attestor trong Anvil/Foundry.
>
> **Giới hạn MVP:** Fuji chain ID `43113`, mock ERC20 + mock AMM, `PolicyVault.sol` tự xây; đây **không** phải Smart Account ERC-4337 hoàn chỉnh. Không hỗ trợ arbitrary calldata/bridge/lending; không giữ tiền thật.

## 1. Ranh giới trách nhiệm

| Bạn sở hữu | Bạn KHÔNG sở hữu |
|---|---|
| `PolicyVault.sol`, adapter, mock tokens, Foundry tests | AI Planner, prompt-injection detector |
| Transaction Builder + quote adapter | Economic Risk Evaluator / portfolio exposure policy |
| Anvil/local fork harness; baseline + fixed MEV stress scenarios | Security Decision Engine decision logic |
| Deterministic Evidence Extractor + artifacts/provenance | Trusted Attestor private key trong production |
| On-chain relayer, receipt monitor, chain context | Feedback + Experience Retrieval / Dashboard |
| API B và TypeScript/Python cross-sig tests phối hợp A | Các chính sách semantic do LLM quyết định |

## 2. Repo layout và stack

```text
contracts/
  src/PolicyVault.sol
  src/interfaces/ISwapAdapter.sol
  src/adapters/MockSwapAdapter.sol
  src/mocks/MockUSDC.sol
  src/mocks/MockWAVAX.sol
  test/PolicyVault.t.sol
  test/PDRGoldenVector.t.sol
  script/Deploy.s.sol
apps/execution-plane/
  app/api/                # FastAPI B on port 8001
  app/transaction/        # deterministic builder
  app/simulation/         # Foundry Anvil runner + scenarios
  app/evidence/           # traces, balances, approvals, hashes
  app/execution/          # signed PDR relayer + receipt monitor
  app/chain/              # chain context and pinned block
  tests/
fixtures/                   # shared input/output fixtures
packages/contracts-api/     # shared DTO / JSON schema
```

**Tech:** Solidity ^0.8.x, Foundry forge/anvil/cast, OpenZeppelin Contracts v5, Python FastAPI + web3.py + Pydantic, pytest. Deploy local first, Fuji later. Owner/test-attestor/relayer are different accounts.

## 3. Build sequence để làm độc lập

### B1. Mock tokens & swap adapter (P0)

- Deploy `MockUSDC` (6 decimals) và `MockWAVAX` (18 decimals), mint treasury balances bằng test-only admin.
- `MockSwapAdapter` có swap `exactInput(tokenIn, tokenOut, amountIn, minOut, recipient)` và liquidity/price setup riêng test mode. Không gọi contract untrusted.
- Mock adapter hỗ trợ kịch bản `normal`, `reserve_shift`, `protected_revert` qua thay đổi trạng thái pool trong fork/local harness; đừng ghi là đã tái tạo MEV ngoài đời.
- `recipient == PolicyVault`; adapter phải dùng `transferFrom` theo allowance exact amount và chuyển output token cho Vault.

### B2. `PolicyVault.sol` (P0, critical path)

**Owner:** cấu hình mandate/hard constraints, active policy hash, attestor, allowlist router/tokens, pause/unpause, revocation. Owner/agent/relayer tách biệt.

**Execute API (minh họa):**

```solidity
struct Approval {
    bytes32 policyHash;
    bytes32 evidenceRoot;
    address router;
    address tokenIn;
    address tokenOut;
    uint256 amountIn;
    uint256 minAmountOut;
    bytes32 calldataHash;
    uint256 nonce;
    uint256 deadline;
}

function executeApprovedSwap(
    Approval calldata approval,
    bytes calldata routerCalldata,
    bytes calldata attestorSignature
) external nonReentrant whenNotPaused;
```

**Checks BẮT BUỘC:**

1. EIP-712 domain `TreasuryPolicyVault`, version `1`, chainId, verifyingContract; recover signer là current attestor owner-set.
2. `approval.policyHash == activePolicyHash`; policy active, nonce chưa dùng, `block.timestamp <= deadline`.
3. Router, tokens và swap selector phải allowlisted, `recipient` trong decoded calldata phải bằng Vault, `calldataHash == keccak256(routerCalldata)`; decoded token/amount/minOut phải khớp Approval.
4. `amountIn <= maxPerSwap`, `dailySpentUsdc[day] + amountIn <= maxSpendPerDay` với input USDC, `day = block.timestamp / 86400` UTC; atomic update.
5. `balanceInBefore - balanceInAfter == amountIn` và `balanceOutAfter - balanceOutBefore >= minAmountOut`; no arbitrary target.call, no delegatecall/batch.
6. Cấp allowance đúng amount, thu hồi dư theo pattern SafeERC20 phù hợp; reentrancy guard; signature replay/revoke/malformed calldata đều revert.
7. Emit `SwapExecuted(nonce, policyHash, evidenceRoot, tokenIn, tokenOut, amountIn, amountOut)` và `PolicyUpdated`, `Paused`/`Unpaused` events.

**PolicyVault không xác minh:** Semantic Task Alignment hoặc USD exposure 25% (cần oracle/portfolio pricing). PDR `evidenceRoot` chỉ là cam kết hash có provenance off-chain; Vault chỉ verify signer/bindings/constraints.

**MVP scope clamp:** P0 chỉ exact-input USDC→WAVAX; `USDC↔WAVAX` còn chiều WAVAX→USDC chỉ làm nếu đã định nghĩa phù hợp daily-spend budgets; không giả định USDC limit áp cho mọi token.

### B3. Deterministic Transaction Builder (P0)

**Input từ A:** `TransactionProposal`. **Output:** `BuiltTransaction {build_id, chain_id, vault_address, router, token_in, token_out, amount_in_base_units, min_amount_out_base_units, router_calldata, calldata_hash, policy_hash, nonce, deadline, quote_ref}`.

- Hard validate chain/vault/router/token/recipient; parse amount là base-unit string, không float.
- Quote từ controlled MockSwapAdapter; `minOut = quoteOut * (10_000 - slippageBps) // 10_000`; đảm bảo slippage ≤ mandate max.
- Encode selector/data bằng ABI allowlisted; data identical → keccak identical (cùng nonce/deadline/quote snapshot).
- Không tin raw calldata do LLM tạo; builder tự sinh.
- Return `build_id` + immutable artifact cho A; mỗi lần đổi amount, route, minOut → `build_id` mới, sim mới.

### B4. Baseline simulation (P0)

**Input:** `BuiltTransaction` (hoặc build_id) + frozen block/chain context.  
**Output:** raw execution artifacts, receipt, balances/approvals trước-sau, trace, scenario labels.

**Giải quyết vòng phụ thuộc “phải ký sau SDE nhưng sim trước SDE”:**

- Local/Anvil simulation dùng **ephemeral test attestor** được cấu hình **chỉ trên instance/fork mô phỏng**, ký một Approval có **cùng dữ liệu giao dịch/constraints** với bản dự kiến; chạy qua đúng code `PolicyVault.executeApprovedSwap`.
- On-chain Fuji thật vẫn giữ trusted attestor khác; **chỉ A ký PDR sản xuất sau APPROVE**. Không có endpoint giả mạo hoặc key test trên Fuji.
- Reconstruct balance/mandate/adapter state giống snapshot được xác định; đánh dấu `simulation_mode=LOCAL_TEST_ATTESTOR`, `provenance`, `fork_block`, `bytecode_hash` và **nêu giới hạn fidelity** nếu local simulation khác deployed chain. **Fuji attestor chỉ chấp nhận `FORK_SIM` với bytecode/state đã đối chiếu**, hoặc phải chuyển demo sang local và gắn nhãn không phải Fuji. Bản sim có test-only signer vẫn chỉ chứng minh execution-path behavior; sự tương thích chữ ký production phải có golden-vector test riêng.
- Khi dùng Anvil fork Fuji về sau, việc thay authorized signer trong fork phải không đụng live chain, và ghi rõ state override. Nếu không tái dựng được tương đương, trả `INCONCLUSIVE`, không giả APPROVE.

**Quan sát:** status, gas, token balances, allowance changes, logs, call trace, minOut/revert, actual simulation root; dùng receipt/trace từ tool, không nhờ LLM đọc số.

### B5. MEV stress tests cố định (P1)

- Tối thiểu `baseline`, `reserve_shift_mild`, `reserve_shift_adverse` theo cùng snapshot.
- Kịch bản thay đổi pool price/reserve **trước** tx; chạy lại chính xác calldata/PDR test mode.
- Phân loại `SUCCESS_SAFE`, `PROTECTED_REVERT`, `UNSAFE_EXECUTION`, `INCONCLUSIVE`.
- Với minOut 24.9 WAVAX, stress quote 24.6 WAVAX: execution revert và token không chuyển đi; classify `PROTECTED_REVERT`, **không ghi mất 0.3 WAVAX thật**.
- Kết quả thử nghiệm không chứng minh sandwich ngoài đời hoặc xác suất thực tế.

### B6. Deterministic Evidence Extractor (P0)

Nhận raw sim output; xuất `SimulationEvidence` dùng chung cho A. Include:

- `intent_id`, `build_id`, `chain_id`, `vault_address`, `fork_block`, `policy_hash`, `calldata_hash`, `nonce` và `deadline`.
- `baseline.execution_status`, `token_in_delta_base_units`, `token_out_delta_base_units`, `gas_used`, `unexpected_transfer`, `unauthorized_approval`.
- `stress_tests[]` + result code, scenario hash, output or revert reason.
- `verification_status`, `evidence_root`, `evidence_manifest_ref`, `artifact_refs`, `parser_version`, `source = REAL_LOCAL_SIM | FORK_SIM`.

**Quan trọng:** `evidence_root` được tính từ canonical JSON bytes (định dạng shared doc); cung cấp cả manifest qua `evidence_manifest_ref` để A tự tính lại hash, raw trace lưu artifact riêng có content hash. SDE không được tin nếu `calldata_hash/policy_hash/chain_id` lệch hoặc verification incomplete. Bảo đảm dữ liệu output có thể tái lập trên cùng fork block + bytecode + scenario seed.

### B7. PDR verification + Relayer + Execution Monitor (P0)

**Input từ A:** `SignedPDR` (PDR + signature) có nguồn gốc từ `SecurityDecision=APPROVE` immutable và `build_id` đã commit; B không chấp nhận một `router_calldata` khác build đã lưu.  
**Output:** `ExecutionResult {tx_hash, status, block_number, gas_used, actual_deltas, events, evidence_refs}`.

- Đối chiếu typed-data hash domain/chain/vault; check signature từ A (on-chain là trọng tài cuối).
- Preflight chain context/policyHash/nonce/deadline; nếu changed thì trả `STALE_REQUIRES_REEVALUATION` (không lặng lẽ thay minOut/calldata).
- Submit qua relayer testnet, lưu tx hash, chờ receipt với timeout và phân biệt `SUBMITTED`, `CONFIRMED`, `REVERTED`, `PENDING`.
- Receipt `status=0` phải báo `REVERTED`; actual delta tính từ logs/chain reads có provenance, không suy từ dự đoán.
- Chain data là source of truth. Return result cho A cập nhật Portfolio State/Experience. Khi phát hiện mismatch critical, yêu cầu PAUSE/REVIEW.

## 4. API bạn cung cấp cho A

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/v1/chain/context` | none | chainId, vault, policyHash, current block, supported router/tokens |
| GET | `/v1/portfolio/onchain-snapshot` | none | vault token balances at block, onchain daily budget counters |
| POST | `/v1/build` | `TransactionProposal` | `BuiltTransaction` |
| POST | `/v1/simulations` | `{build_id, expected_policy_hash}` | `SimulationEvidence` |
| POST | `/v1/executions` | `{build_id, signed_pdr}` | `{tx_hash,status}` |
| GET | `/v1/executions/{tx_hash}` | tx hash | `ExecutionResult` |

**Contract:** status `2xx` chỉ cho request hợp lệ và được xử lý theo đặc tả; simulation có thể trả `INCONCLUSIVE`, không được ngầm coi lỗi timeout là PASS. Error envelope + retry behavior ở shared doc.

## 5. Local mock để không phụ thuộc A

- Dùng `fixtures/normal_swap.json` làm `TransactionProposal`, build, execute full vault test trên Anvil.
- Dùng **test-only** local signer để ký PDR trong Foundry; không dùng key attestor sản xuất và không gọi API A.
- Viết `PDRGoldenVector.t.sol` kiểm tra signature do Python của A tạo được và domain đúng.
- Cung cấp `fixtures/simulation_evidence.json`, `fixtures/execution_result.json` cho A trước khi simulator hoàn chỉnh (đánh dấu MOCK).

## 6. Checklist từng ngày — B

### 16/11 — Solidity core
- [ ] Chốt struct Approval/EIP712 với A, fixtures/schema merge trước.
- [ ] Foundry setup, MockUSDC/WAVAX, MockSwapAdapter.
- [ ] Vault owner roles, allowlist, nonce, pause, signature verification skeleton.

### 17/11 — Execution path
- [ ] Hoàn thành `executeApprovedSwap` + hard limit + minOut tests.
- [ ] Transaction Builder exact calldata; baseline simulation local/fork.
- [ ] Xuất `BuiltTransaction` + mock `SimulationEvidence` cho A.

### 18/11 — Evidence & integration
- [ ] Evidence Extractor: state diff/allowance, trace hashes, typed evidence.
- [ ] REST API B, EIP712 golden-vector test với A.
- [ ] Ghép A: APPROVE decision → A ký PDR → B verify/execute.

### 19/11 — Stress/security tests
- [ ] 2–3 fixed reserve shift scenarios.
- [ ] Replay, modified calldata, bad signer, expired PDR, pausing, daily spend boundary tests.
- [ ] Deploy mock contracts trên Fuji, relay một TX hợp lệ.

### 20/11 — Freeze & demo
- [ ] Fix chain/nonce/decimals/RPC timeout; đối chiếu receipts.
- [ ] Chạy 4 scenario N/P/E/M và replay, chuẩn bị tx explorer link (không hardcode txHash trước).

## 7. Acceptance tests B

```text
B-01 valid signed Approval + matching calldata -> EXECUTED
B-02 same PDR again                        -> REVERT (nonce used)
B-03 changed routerCalldata                -> REVERT (hash mismatch)
B-04 changed minOut, token, route          -> REVERT (struct/calldata checks)
B-05 revoked attestor / changed policy     -> REVERT
B-06 expired deadline, wrong chain         -> REVERT / invalid signature
B-07 > max trade                           -> REVERT
B-08 daily 700 + two approved 200 swaps    -> first success, second exceeds 1000 -> REVERT
B-09 output under minOut                   -> REVERT, no partial token transfer
B-10 malicious recipient outside vault     -> REVERT
B-11 simulation result links hashes to build/bytecode/fork block
B-12 no evidence of real sim               -> no `COMPLETE` response
```

## 8. Security pitfalls không được bỏ sót

- *Signature correctness:* Domain separator, type hash, field order + field sizes EIP-712 match exactly A; không dùng raw `personal_sign` thay thế.
- *Call correctness:* Allowlist router là chưa đủ nếu router nhận arbitrary byte payload; contract phải decode được selector/parameters.
- *Accounting:* Không dùng allowance vô hạn; reentrancy guard, SafeERC20; fee-on-transfer/rebase không hỗ trợ.
- *Race:* `dailySpentUsdc` update atomically trên chain; DB lock không thay onchain enforcement.
- *Stale state:* Fork block / price freshness và preflight; minOut onchain bảo vệ giá xấu nhưng không bảo đảm giao dịch sẽ thành công.
- *Key separation:* Owner/config, attestor/signer, relayer/gas wallet khác key; test keys nằm ở local fixture, không mang sang Fuji production demo.
- *Chain scope:* Mock contracts/test tokens; không gọi thật từ tiền người dùng; testnet chưa audit.

## 9. Khi bị blocker

- **A chưa xong AI:** dùng fixture để gọi B; forge + local signed PDR hoàn toàn độc lập.
- **Fuji RPC chập chờn:** dùng Anvil local cho demo bảo mật, sau đó lên Fuji khi có thời gian; không tuyên bố transaction Fuji nếu chỉ chạy local.
- **MEV chưa xong:** chốt baseline + PDR + Vault trước; có thể dùng một reserve-shift test deterministic đơn giản.
- **Trace khó parse:** tối thiểu receipts, trước/sau balances/allowances, logs với provenance; các fact chưa xác minh đánh dấu `INCONCLUSIVE`.

**Done cuối cùng của B:** A đưa `TransactionProposal` → bạn trả `BuiltTransaction`/`SimulationEvidence` → A ký `SignedPDR` sau SDE → bạn thực thi đúng calldata qua Vault, nhận receipt và các token deltas có thể kiểm chứng.
