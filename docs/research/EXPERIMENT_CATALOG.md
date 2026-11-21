# Catalog thí nghiệm PaceVant — Benchmark, ablation và negative results

## E08 — Current Public MVP: payment/swap Fuji (21/11/2026)

**Môi trường:** `PUBLIC FUJI`, chain ID 43113, PolicyVaultMVP mới tại [`0x70e1…5b6d5`](https://testnet.snowtrace.io/address/0x70e1395F959dba530cF4A53B060c809b715bB6d5). **Public acceptance report:** [manifest/receipt/effect verification](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/public-fuji-live-acceptance-20261121.json).

| Scenario | Kết quả | Transaction / source |
| --- | --- | --- |
| Browser **USDC_PAYMENT** | `CONFIRMED`, recipient nhận **10.000 base units = 0,01 test USDC**, relayer trả gas | [0x10f6…4470b8c](https://testnet.snowtrace.io/tx/0x10f6a04e22179f4186459e3738c61597048e9b2aac724c01347ba306f4470b8c) |
| Browser **SWAP_EXACT_IN** | `CONFIRMED`, Vault giảm **1 base unit Circle test USDC**, tăng **13.266.545.691.051 wei WAVAX** | [0xa708…e4b2d](https://testnet.snowtrace.io/tx/0xa708f44e355b6926c02693282f8ca6514fd043199ae8d23d3a031d64f82e4b2d) |
| Public policy guard | `PAYEE_NOT_ALLOWED`, **không ký / không broadcast** | [Guard record trong acceptance JSON](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/public-fuji-live-acceptance-20261121.json) |
| Browser acceptance | Payment/swap pages PASS với release SHA riêng; F5 resume không tạo duplicate POST | Acceptance JSON, `browser_acceptance` |

**Cảnh báo:** hai release browser SHA trong acceptance không mặc nhiên bằng `main` HEAD; nhánh phục vụ website là `develop` theo [Public Runbook](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PUBLIC_FUJI_RUNBOOK.md). Sáu lựa chọn attack trên UI là preview, **không** phải sáu backend attacks đã chạy live. Lỗi semantic schema có một case fail-closed và một job `FORK_RUN_INTERRUPTED` trước broadcast cũng được giữ trong report.

## E09 — Merge Hybrid TaskShield vào fixed public operation pipeline

[Merge report](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/MAIN_MERGE_20261121.md) xác nhận nối TaskShield authenticated source/operation adapter vào V3/MVP. Kiểm các trường operation/token/amount/recipient/chain/deadline/minOut/slippage/sender và giữ semantic uncertainty fail-closed. 59 workflow/hybrid tests và 45 focused final integration/security/API tests pass (1 skip), cùng MVP Foundry suite và React build + 10 tests trong checkpoint merge.

**Không chạy lại paid-model 300-case evaluation, không tạo public transaction và không deploy VPS trong riêng task merge.** Kết quả 300-case A/B/C/D vẫn là benchmark component gốc, không tự suy thành đo lại adapter mới.

---

### Catalog thí nghiệm trước checkpoint public mới (giữ nguyên provenance)



> **Lưu ý:** đây là bản catalog tiếng Việt cho reviewer tại checkpoint 21/11/2026. Các tỷ lệ là số đo **trong tập xác định**, không tự động chuyển thành ước lượng production. Nhiều báo cáo là kết quả checkpoint trước HEAD; đọc nguồn gốc đi kèm.

## Quy ước đọc kết quả

- **SCRIPTED:** response hoặc verdict được dựng trước để kiểm test wiring/deterministic invariants; không được coi là đo chất lượng LLM.
- **REAL MODEL:** gọi provider thực tế; phải phân biệt validated output với raw model judgment.
- **LOCAL ANVIL:** EVM thật trên chuỗi/fork local có tài sản test và kịch bản giả định.
- **PUBLIC FUJI:** transaction thực sự nằm trên Avalanche Fuji; evidence theo tx/block cụ thể.
- **REGRESSION:** tập đã được dùng trong vòng phát triển; không phải independent untouched test.
- **NO WRITE / READ-ONLY:** đọc state, replay local hoặc eth_call; không gửi public transaction.

## E01 — Hybrid TaskShield: A/B/C/D (300 case)

| Cấu hình | Nguồn / bản chất | Accuracy | False Accept / 232 | Nhận xét |
| --- | --- | ---: | ---: | --- |
| A — Original TaskShield | Frozen prior real-provider run | 49,00% | 132 | Score-only authorization, 11 unavailable |
| B — Aggregation fix | Offline replay trên score matrices cũ | 68,67% | 40 | Sửa tổng điểm chưa đủ; 43 explicit false rejects |
| C — Constraints-only | Production parser/verifier; offline diagnostic | 95,67% | 0 | Không gọi LLM và không tự authorize wallet |
| D — Full Hybrid | Fresh DeepSeek Flash run | 95,67% | 0 | 12 uncertain/unavailable, 1 false reject |

**Nguồn:** [Hybrid results](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md), [error analysis](../evaluation/HYBRID_TASK_ALIGNMENT_ERRORS.md), [quality report](../evaluation/curated-300/benchmark_300_quality_report.md).

**Bộ dữ liệu:** 300 curated **SWAP** Uniswap V2 đã được bổ sung context, gồm 68 ACCEPT và 232 REJECT. Không có transfer gốc được xác nhận. Đây là component-level paper/adapter evaluation; cả 300 source transactions không được broadcast qua LFJ. Bản D có 55/68 benign approved đúng, 12 uncertain, 1 false reject; 232/232 adverse bị REJECT.

**Giới hạn chính:** Tập đã bị quan sát trong phát triển; có gold-label inconsistencies được ghi nhận; không khẳng định hiệu quả trên dữ liệu độc lập. C và D accuracy bằng nhau — chưa đủ bằng chứng AI tạo lift thêm trên corpus này. Bản D có 367 inference calls và 403.573 provider-reported tokens theo final run; không tính development iterations.

## E02 — ITAG deterministic benchmark (12 adverse + 12 benign)

| Configuration | Interventions trên 12 adverse | Approvals trên 12 benign |
| --- | ---: | ---: |
| A — Wallet guardrails | 0/12 | 12/12 |
| B — Wallet + TaskShield | 0/12 | 12/12 |
| C — Deterministic ITAG | 8/12 | 12/12 |
| D — Shield + deterministic ITAG | 8/12 | 12/12 |

Các ca adverse gồm budget/order/history/purpose. Có **4 purpose conflicts trong hạn mức số học** mà scripted deterministic variants không chặn được.

**Nguồn:** [ITAG Final Validation](../evaluation/itag-final/FINAL_VALIDATION.md). Đây là authored/scripted benchmark; không có independent human labels.

## E03 — ITAG graph-aware AI: lỗi phiên bản đầu và cải tiến v3.x

| Checkpoint | Valid semantic findings | Benign approvals | Conflict observations |
| --- | ---: | ---: | ---: |
| Original v2.3 replication | 0/6 | 0/3 | 0/2 |
| v3.0 — sáu case × hai lượt | 1/12 | 0/6 | 1/4 |
| v3.1 — sáu case × hai lượt | 12/12 | 3/6 | 4/4 |
| v3.2 — mười case × hai lượt | 16/20 | 9/10 | 7/8 |
| Final scripted six-case interface | 6/6 | 3/3 | 2/2 |

**Gốc lỗi:** model output tham chiếu node/evidence sai phạm vi, sao chép trích dẫn không đủ chuẩn hoặc thiếu operator scope; strict validation chuyển thành unavailable/escalation. **Sửa đổi:** graph-bound catalog, field selectors, server-resolved anchors, schema+factual grounding; giữ nguyên cấm AI grant authorization.

**Nguồn:** [ITAG Semantic Reliability Final Report](../evaluation/itag-semantic-reliability/FINAL_REPORT.md). Số 7/8 là validated lift trên **observations**, không phải 7 trong 8 attack families độc lập. Một trong 20 observations bị upstream TaskShield chặn trước graph-model; chỉ 19 graph calls thực tế, 16/19 outputs valid theo report.

**Điều chưa chứng minh:** semantic factual accuracy toàn bộ free-text, generalization độc lập, causal speedup, hoặc phát hiện planner đã thật sự bị compromise.

## E04 — ITAG LOCAL Anvil budget enforcement

- Kịch bản: task budget **20 USDC**, hai swap **10 USDC** được xác nhận; đề xuất thứ ba **10 USDC**.
- Trong paired counterfactual tại cùng context/proof/risk, wallet-only và TaskShield-only approve; deterministic ITAG từ chối theo cumulative budget.
- **Kết quả actual LOCAL:** giao dịch thứ ba không có attestation; relayer nonce giữ nguyên. Có receipts cho hai giao dịch trước.
- **Nguồn:** [Final Validation](../evaluation/itag-final/FINAL_VALIDATION.md), [Anvil budget isolation artifact](../evaluation/itag-final/ANVIL_BUDGET_ISOLATION.json).

**Phân biệt:** LOCAL Anvil có execute thật; không phải public Fuji transaction.

## E05 — Hybrid TaskShield LOCAL integration & real-model smoke

- Kiểm thử swap + ERC-20 transfer qua simulation → risk → proof → SDE → attestor → PolicyVault → receipt.
- Các security regressions chủ yếu sử dụng **scripted AI** để tái hiện ổn định.
- Có **một real-model LOCAL transfer** và **năm authored real-model semantic smoke cases**; đây là smoke evidence, không phải mẫu đủ lớn để đo population accuracy.
- **Nguồn:** [Hybrid Results](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md), [Regression artifact](../evaluation/hybrid-task-alignment/REGRESSION_RESULTS.json).

## E06 — Public Fuji: core pipeline / web demo / gas accounting

**Web demo swap**: tx [0x315a…9656ba](https://testnet.snowtrace.io/tx/0x315a9bff8ba111487d295903ebd0f6389b1baefd40ea9526fc33bc014a9656ba), block **61375517**; actual token deltas + gas debit reconciled; có 14 chain checks và 3 negative historical eth_call checks trong report.

**Core checkpoint trước đó**: tx [0xf975…61b10](https://testnet.snowtrace.io/tx/0xf975361607032ec0709140d32c6d5e98a266f8df6917226e1d6ecb6cf6361b10), block **61371323**; có proof artifacts, oracle/chain evidence và audit theo checkpoint.

**Nguồn:** [Web live review](../audit/WEB_DEMO_LIVE_REVIEW.md), [Core historical review](../audit/SYSTEM_SECURITY_REAL_DATA_REVIEW.md).

**Không suy ra:** thử nghiệm Fuji cho code sau PR Hybrid TaskShield, production readiness, mainnet, lời/lỗ kinh tế thực hoặc on-chain gas payment của Demo User (relayer trả gas).

## E07 — MEV stress, oracle, Z3 và enforcement

- **Fork baseline:** exact guarded call trên pinned Anvil fork, verified effects.
- **MEV stress:** reserve perturbations với hypothetical actor trên local fork; actor setup/funding và mức tác động là assumption của scenario.
- **Oracle:** Chainlink Fuji rounds làm reference; cần round provenance và freshness; test asset price reference không chứng minh redeemability.
- **Z3:** SAT/UNSAT của các proof obligations bounded; proof có assumptions và commitment.
- **Smart contract:** Forge tests gồm policy/session/replay/call integrity/postcondition/rollback; báo cáo checkpoint có 60 tests pass, trong đó fuzz cases.

Nguồn: [Simulation module](../../backend/src/treasury_backend/modules/execution/simulation/README.md) · [System Design](../AI_Treasury_Security_System_Design_v2.1.md) · [Smart contract tests](../../contracts/test/README.md).

**Không có** một con số “MEV detection accuracy” hoặc “Z3 model precision” duy nhất được xác minh ở đây; không tự chế tác những metric đó.

## Bảng kiểm tái hiện cho nghiên cứu tiếp theo

| Check | Yêu cầu |
| --- | --- |
| Dataset | Provenance, split, label-review, duplicate policy, fixture constraints |
| Model | Provider/version, prompt hash, tool-role, retries/fallbacks, token usage |
| Reproducibility | Source commit SHA, run command, environment, artifact IDs |
| Comparison | Same cases/context, matched denominators, abstentions/failures shown |
| Safe execution | Read-only by default; public writes require separate operator approval |
| Reporting | Positive, negative, errors, limitations, *what has not been proven* |

Tái hiện benchmark theo [TaskShield reproduction](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md#reproduction), [ITAG reproduction](../evaluation/itag-final/FINAL_VALIDATION.md#reproduction) và [semantic reliability reproduction](../evaluation/itag-semantic-reliability/FINAL_REPORT.md#reproduce). Không chạy lại benchmark chỉ bằng cách cập nhật README và không sửa frozen labels để phù hợp kết quả mong muốn.
