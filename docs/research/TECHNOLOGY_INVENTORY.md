# Technology Inventory — Toàn bộ công nghệ PaceVant

## Cập nhật bắt buộc — Public MVP ngày 21/11/2026

**Ưu tiên bảng này cho public deployment; các bảng bên dưới giữ inventory các thành phần và checkpoint nghiên cứu (bao gồm legacy).** Việc một module tồn tại trong repo **không** đồng nghĩa module được expose trên public website.

| Thành phần | Trạng thái public MVP mới | Nguồn xác thực |
| --- | --- | --- |
| Website | **React 19 + TypeScript + Vite 8**, React Flow (`@xyflow/react`), Tailwind v4, Radix UI, TanStack Query, Motion, Lucide, static Nginx | [package.json](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/frontend/package.json), [current review](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md) |
| Backend | Python/FastAPI modular monolith, public Judge worker, SQLite journal, systemd service; **không** có Node server/Docker production | [public runbook](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PUBLIC_FUJI_RUNBOOK.md) |
| Contract | **PolicyVaultMVP + PolicyVaultV3 base, LFJSwapAdapterV3**, signed EIP-712 domain v3, exact operation | [PolicyVaultMVP.sol](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/contracts/src/PolicyVaultMVP.sol), [deployment report](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/mvp-public-deployment-20261121.json) |
| Public operations | **USDC_PAYMENT (0,01 test USDC)** và **SWAP_EXACT_IN (0,000001 test USDC → WAVAX)** qua allowlisted scope | [current system review](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md) |
| Simulation & risk | Anvil **baseline pinned fork** + effect extraction, Chainlink reference, economic/effect checks, ITAG, Z3/Phi | [runtime coordinator](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/backend/src/treasury_backend/modules/workflows/treasury.py), [economic audit](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/MVP_ECONOMIC_RISK_AUDIT.md) |
| MEV research | Hypothetical reserve-shift/stress **LOCAL/research**; **không** phải engine MEV stress độc lập mặc định của public `TreasuryWorkflows.run()` | [Simulation research module](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/backend/src/treasury_backend/modules/execution/simulation/README.md) |
| Research/legacy only | ERC-20 transfer LOCAL, V2/V3 research, Demo User gas credit, optional rebalance/autonomy | [merge analysis](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/MAIN_MERGE_20261121.md), [current review](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md) |

**Bằng chứng của public deployed path:** [Fuji receipts, code hashes và browser acceptance](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/public-fuji-live-acceptance-20261121.json) (tương ứng release/checkpoint trong JSON; **không** phải xác nhận mọi commit `main` được deploy). Public có fixed scenario và six UI **attack previews**; không có backend attack injection khi chọn preview.

---

### Inventory nguồn trước đây (bảo lưu để truy vết nghiên cứu)



> **Phạm vi:** mô tả **các thành phần đã có trong mã nguồn**, source references và những tính năng **không** thuộc runtime hiện tại. Những tên công nghệ xuất hiện trong nghiên cứu nhưng chưa chạy không được tự động gán nhãn “đã tích hợp”. Đối chiếu cuối với [module map](../../backend/MODULES.md) và [System Design V2.1](../AI_Treasury_Security_System_Design_v2.1.md).

## 1. AI Agent & AI Security

| Công nghệ / phương pháp | Vai trò cụ thể | Code / báo cáo | Ranh giới |
| --- | --- | --- | --- |
| DeepSeek provider | Planning, task decomposition, semantic assessment; các lần real-model evaluation | [Planning](../../backend/src/treasury_backend/modules/planning/README.md), [Alignment](../../backend/src/treasury_backend/modules/alignment/README.md) | Output không tự tạo quyền |
| Groq / Gemini / Xingchi adapters | Provider routing/fallback theo cấu hình | [Planning](../../backend/src/treasury_backend/modules/planning/README.md) | Có adapter không đồng nghĩa tất cả provider đều đã đo chất lượng độc lập |
| LLM task decomposition | Tách semantic task từ user instruction đã xác thực | [Hybrid TaskShield design](../security/HYBRID_TASK_ALIGNMENT.md) | Model paraphrase không thay authenticated text |
| Typed intent envelope / source spans | Cấu trúc hóa token, amount, recipient, minOut, deadline... | [Hybrid TaskShield design](../security/HYBRID_TASK_ALIGNMENT.md) | Ambiguity/unsupported phrasing → uncertain |
| Source-bound task binding | Nối action với một task/revision có quyền | [Alignment module](../../backend/src/treasury_backend/modules/alignment/README.md) | Không cộng contribution từ task không liên quan |
| Deterministic constraint checks | So sánh số học/token/địa chỉ/chain/router | [Hybrid TaskShield results](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md) | Không thay thế semantic drift detection |
| Semantic alignment / prompt-injection detection | Relevance, unauthorized purpose, malicious TOOL-role content | [TaskShield design](../security/HYBRID_TASK_ALIGNMENT.md), [Web attack runbook](../demo/LIVE_WEB_DEMO.md) | Real-model coverage hạn chế; model may fail |
| Strict evidence-aware fusion | Mandatory FAIL → veto; unknown → không approve | [Hybrid TaskShield design](../security/HYBRID_TASK_ALIGNMENT.md) | Ưu tiên safety, có chi phí benign uncertainty |
| Intent-Aware Temporal Action Graph | Typed action/task/provenance graph + history/budget | [Temporal module](../../backend/src/treasury_backend/modules/temporal/README.md) | Graph có evidence, không tự chứng minh động cơ ẩn |
| Graph-bound semantic catalog | LLM chọn objective/candidate/evidence bằng selectors, server grounding | [ITAG semantic report](../evaluation/itag-semantic-reliability/FINAL_REPORT.md) | LLM không được bịa node/citation |
| Experience / replanning | Gợi ý điều chỉnh theo outcome và policy | [Experience](../../backend/src/treasury_backend/modules/experience/README.md) | Suggestion phải chạy lại security pipeline |

## 2. DeFi, Ethereum & Blockchain

| Công nghệ / thành phần | Vai trò cụ thể | Source / evidence | Ranh giới |
| --- | --- | --- | --- |
| EVM | Mô hình thực thi transaction và ABI | [Execution](../../backend/src/treasury_backend/modules/execution/README.md) | Không đại diện mọi blockchain |
| Avalanche Fuji testnet | Chuỗi public demo | [Web live report](../audit/WEB_DEMO_LIVE_REVIEW.md) | Testnet, không phải mainnet / production |
| LFJ / Trader Joe | Route exact-input swap qua allowlisted adapter | [LFJ adapter](../../contracts/src/adapters/LFJSwapAdapter.sol) | Không phải general-purpose DEX aggregator |
| Circle test USDC, WAVAX | Token pair của live Fuji route | [Live web runbook](../demo/LIVE_WEB_DEMO.md) | Test token/reference USD không chứng minh redeemability |
| Chainlink Data Feeds | Reference price / round/updatedAt provenance | [Oracle](../../backend/src/treasury_backend/modules/oracle/README.md) | Oracle freshness, mappings, trust assumptions |
| Ethereum JSON-RPC / Web3 | Chain reads, blocks, receipts, eth_call | [Execution](../../backend/src/treasury_backend/modules/execution/README.md) | RPC trả pending/không đồng bộ có thể ảnh hưởng liveness |
| Solidity | Chính sách và enforcement trên chain | [Contracts](../../contracts/README.md) | On-chain không chạy LLM/Z3 |
| PolicyVault V2 | Owner policy, session, caps, replay, Phi/postcondition | [PolicyVault.sol](../../contracts/src/PolicyVault.sol) | Bị ràng buộc theo cấu hình / trusted attestor |
| LFJSwapAdapter | Hạn chế chức năng contract/DEX execution | [LFJSwapAdapter.sol](../../contracts/src/adapters/LFJSwapAdapter.sol) | Adapter khác cần review riêng |
| EIP-712 | Typed-data signed policy decision record | [Signing](../../backend/src/treasury_backend/modules/signing/README.md) | Signed payload phải được bind đúng fields |
| Keccak-256 / commitments | Ràng buộc call, proof, evidence, Phi | [Shared SDK](../../packages/contracts-api/README.md) | Hash đúng không tự xác nhận semantics đúng |
| OpenZeppelin | Dependency Solidity pin/cache, tested imports | [Contracts](../../contracts/README.md) | Không thay security audit |

## 3. Transaction Security, Risk & Formal Methods

| Công nghệ / phương pháp | Vai trò cụ thể | Tài liệu | Ranh giới |
| --- | --- | --- | --- |
| Foundry Forge | Build/deploy/test Solidity; fuzz, security regressions | [Contracts test guide](../../contracts/test/README.md) | Unit/fuzz tests theo property được định nghĩa |
| Native Anvil | EVM local/fork trên state pin | [Simulation module](../../backend/src/treasury_backend/modules/execution/simulation/README.md) | Fork ≠ broadcast public chain |
| Baseline EVM simulation | Exact guarded call, state diff, receipt/log/allowance evidence | [Simulation module](../../backend/src/treasury_backend/modules/execution/simulation/README.md) | Phụ thuộc pinned block và RPC |
| MEV / reserve stress scenarios | Perturbation giả định để đo rủi ro execution | [Simulation module](../../backend/src/treasury_backend/modules/execution/simulation/README.md) | Không đảm bảo bao phủ mọi MEV/private order flow |
| Deterministic evidence extractor | State diff/log/receipt → typed evidence + hashes | [Execution module](../../backend/src/treasury_backend/modules/execution/README.md) | Chất lượng phụ thuộc chain trace/source |
| Portfolio Reader | Snapshot, token balances/exposure, historical constraints | [Portfolio](../../backend/src/treasury_backend/modules/portfolio/README.md) | Không thay người dùng tự xác nhận quyền |
| Economic Risk Evaluator | Risk bound/exposure/slippage/simulation impacts | [Risk](../../backend/src/treasury_backend/modules/risk/README.md) | Financial assumptions/Chainlink reference |
| Z3 SMT Solver | Conditional bounded theorem/postconditions | [Proof](../../backend/src/treasury_backend/modules/proof/README.md) | Không phải ZK proof / unrestricted correctness |
| Phi (Φ) | Biên dịch lower-bound token deltas/residual allowance caps | [Proof](../../backend/src/treasury_backend/modules/proof/README.md), [Contracts](../../contracts/README.md) | On-chain enforce compiled limits, không chạy SMT |
| Security Decision Engine | Kết hợp mandatory gates thành APPROVE/REJECT/REPLAN/ESCALATE | [Decision](../../backend/src/treasury_backend/modules/decision/README.md) | AI không được override veto |
| Attestor & revalidation | Xác minh freshness/decision/task trước ký | [Signing](../../backend/src/treasury_backend/modules/signing/README.md) | Trusted component; cần quản lý keys |
| Final guarded preflight | Tránh dùng evidence/calldata sai với bản build được ký | [Simulation](../../backend/src/treasury_backend/modules/execution/simulation/README.md) | Không chứng minh future liquidity sẽ giữ nguyên |

## 4. Software Engineering, Data, Reliability & UI

| Công nghệ | Vai trò | Tài liệu |
| --- | --- | --- |
| Python 3.12 | Core backend / domain models / orchestration | [Backend](../../backend/README.md) |
| FastAPI + Uvicorn | Một API application, control + execution trong process | [Unified backend](../architecture/UNIFIED_BACKEND.md) |
| uv + lockfile | Environment/package management | [Main README](../../README.md) |
| SQLite | Control state, execution journal, task budgets, ledgers | [Persistence](../../backend/src/treasury_backend/modules/persistence/README.md) |
| Typed DTO / SDK | Cross-module hash, ABI, proof, wire contracts | [Contracts API](../../packages/contracts-api/README.md) |
| Durable raw-tx journal + idempotency | Recovery khi broadcast/receipt chưa rõ | [Execution](../../backend/src/treasury_backend/modules/execution/README.md) |
| Outcome Monitor | Receipt reconciliation, canonical block, reorg detection | [Monitoring](../../backend/src/treasury_backend/modules/monitoring/README.md) |
| Gas Credit ledger | Sponsored allowance, hold, actual debit, reorg reversal | [Gas Credit](../../backend/src/treasury_backend/modules/gas_credit/README.md) |
| HTML / CSS / browser JavaScript | Main dashboard, Demo User, task / graph viewer | [Frontend](../../frontend/README.md) |
| pytest / Forge / fuzz | Python, Solidity, local/security integration | [Backend test guide](../../backend/tests/README.md), [Contracts tests](../../contracts/test/README.md) |
| Ruff / secret scan | Source QA, secret scanning | [Contributing](../../CONTRIBUTING.md) |
| Docker / native Foundry | Build & runtime packaging, fork process | [Deployment](../../deploy/README.md) |
| Mermaid (tài liệu) | Sơ đồ kiến trúc kiểm chứng bằng source Markdown | [System Design](../AI_Treasury_Security_System_Design_v2.1.md) |

## 5. Công nghệ được nghiên cứu / cân nhắc nhưng **không tuyên bố đã triển khai**

| Mục | Trạng thái / lý do |
| --- | --- |
| ERC-4337 smart account, bundler, paymaster | **Không có** trong live flow: treasury dùng PolicyVault + signed PDR |
| ERC-7579 modular smart account | **Không có** trong live flow |
| Zero-knowledge proof / on-chain ZK verification | **Không có**: hiện tại là Z3 SMT off-chain |
| Arbitrary DeFi lending, yield farming, multi-hop routing | **Chưa hỗ trợ** trong live Fuji path |
| Multi-user independent wallets / custody / billing | **Chưa nghiệm thu**: Demo User là shared sponsor account |
| Mainnet audited release, HSM, HA, hosted production | **Chưa kiểm chứng** |

## 6. Bảo trì inventory

Khi có công nghệ mới, chỉ thêm vào bảng “đã triển khai” nếu có **source reference, runtime profile, test/evidence và limitation**. Nếu mới là ý tưởng, giữ riêng “đề xuất / future work”. Các phiên bản dependency thực tế phải tra trong lockfile và Foundry config; không tự điền version không kiểm chứng.

[Research Index](RESEARCH_INDEX.md) · [Experiment Catalog](EXPERIMENT_CATALOG.md) · [Security Coverage Matrix](SECURITY_COVERAGE_MATRIX.md)
