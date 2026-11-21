# Báo cáo phản biện và tái định vị README PaceVant — 21/11/2026

> **REVIEW ONLY / DOCS-ONLY / UNMERGED**. Nhánh: `docs/readme-tieng-viet-review-20261121`. Không sửa contract, runtime, deployment, model prompt hoặc private config. Không chuyển nhánh deploy `develop` và không suy ra `main` HEAD đã được cài lên VPS.

## 1. Mục tiêu và nguồn đã đối chiếu

Bản README trước đây mạnh về danh sách công nghệ và nghiên cứu nhưng chưa trình bày đủ rõ **tại sao một giao dịch hợp lệ vẫn có thể là hành động sai mục đích trong chuỗi dài**, và chưa phản ánh public MVP hiện tại. Lần sửa này biến README thành một giới thiệu sản phẩm dựa trên bằng chứng, đồng thời giữ lịch sử nghiên cứu.

**Ưu tiên nguồn:**
- [`TreasuryWorkflows.run()` hiện trên main](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/backend/src/treasury_backend/modules/workflows/treasury.py): thứ tự gates thực tế.
- [Current public system review](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md), [public judge runbook](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/PUBLIC_FUJI_RUNBOOK.md).
- [Public Fuji acceptance JSON](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/public-fuji-live-acceptance-20261121.json), [deployment manifest journal](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/mvp-public-deployment-20261121.json).
- [Main merge report](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/MAIN_MERGE_20261121.md), [Frontend package](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/frontend/package.json), [PolicyVaultMVP](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/contracts/src/PolicyVaultMVP.sol).
- [TaskShield A/B/C/D](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md), [ITAG Final Validation](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/evaluation/itag-final/FINAL_VALIDATION.md), [Semantic Reliability](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/evaluation/itag-semantic-reliability/FINAL_REPORT.md).
- [PACE paper notes](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/paper/PACE_Policy_Attested_Contract_Execution.md) và [Proof-Gated Signing paper notes](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/paper/Proof_Gated_Signing_Solver_Checked_Transaction_Guards.md); không tự khẳng định novelty đã peer-reviewed.

**Trạng thái Git lúc đối chiếu:** nhánh review tách từ `176f63fa`, có các docs commits riêng; `main` đã có thêm implementation/acceptance mới, `develop` là nhánh deploy được mô tả trong runbook và không nhất thiết đồng nhất SHA với `main`. Để tránh mượn nhầm bằng chứng, link tới reports/source chỉ có trên main dùng URL rõ ref `main`, **không** copy code mới hoặc rebase nhánh review.

## 2. Review chi tiết từng section

| Section | Điểm tốt trước sửa | Điểm yếu trước sửa | Đã chỉnh gì | Vì sao quan trọng | Source / evidence |
| --- | --- | --- | --- | --- | --- |
| Hero | Có banner SVG dark/light và branding | Message chung chung “AI có thể lập kế hoạch” | Headline **“Một giao dịch có thể hợp lệ. Cả chuỗi hành động vẫn có thể sai mục đích.”**; CTA Demo/Evidence/Architecture | Đưa failure mode + USP lên đầu | README + hero SVG |
| Product thesis | Có nêu wallet security | Lẫn AI trading, security layers và broad DeFi | Định vị **Intent-Aware Security for Autonomous On-Chain Treasury Agents** với public scope | Người đọc hiểu đây là lớp kiểm soát, không phải trading bot | Public MVP review |
| Threat explanation | Có token, budget, MEV | Rời rạc, quá nhiều thuật ngữ | Một ví dụ USDC→WAVAX xuyên suốt, phân biệt single-tx, cumulative, semantic, economic, state drift | Phân biệt loại nguy cơ và lớp xử lý phù hợp | Runtime + ITAG reports |
| Attack/Defense | Có budget isolation image | Ngầm làm ITAG giống bộ cộng tiền | Hai scenario riêng: deterministic budget **LOCAL** và purpose drift **REAL-MODEL SMALL** | Không quy 8/12 deterministic thành AI detections | ITAG Final + Semantic Reliability |
| Core contributions | Có ba “innovations” | Dễ làm người đọc tưởng PDR/Z3/sim là phát minh mới | Đổi thành **ba lớp năng lực**: Task Integrity, Long-Horizon Intent, Proof-Bound Execution | Tách research differentiator khỏi engineering integration | PACE/PGS notes |
| Live Evidence | Có V2/Demo User receipts | Thiếu new MVP PolicyVault, web payment/swap và public guard | Bổ sung website, contract MVP, 2 tx từ browser và acceptance JSON; historical receipt để research archive | Cho reviewer tự kiểm ở Fuji đúng contract/version | Acceptance + deploy journal |
| Benchmark | Minh bạch 49→95,67%, 8/12, 7/8 | KPI 95,67% quá lớn, không nhắc constraints-only đồng điểm | Metrics graphic **Fuji evidence trước**, sau đó ITAG và TaskShield, có caveat ngay cạnh | Không đánh đồng độ chính xác component với bảo mật sản phẩm | A/B/C/D + ITAG |
| Architecture | Mermaid nhiều module | Chưa giải thích tại sao cần từng lớp, sai MEV public path | Tóm tắt ba trust zones + 16 bước Input/Purpose/How/Output/Threat/Limit; source-aligned order | Giám khảo hiểu “tại sao không chỉ dùng một gate?” | `TreasuryWorkflows.run()` |
| Transaction execution | Có Z3/PDR/Vault | Mô tả V2 cũ, chưa rõ typed V3, public payments | Nêu EIP-712 domain V3 và PolicyVaultMVP, scope payment/swap | Phản ánh code deployed mới, không ám chỉ arbitrary DeFi | PolicyVaultMVP, public acceptance |
| Tech stack | Có đủ AI/blockchain/proof | Frontend HTML/CSS/JS, Docker/VPS không còn đúng current | React/TS/Vite/React Flow/Tailwind/Radix/TanStack, Nginx/systemd; research tooling tách biệt | Reviewer không đánh giá nhầm engineering stack | `frontend/package.json` |
| Prior work | Có sử dụng PACE/PGS trong nghiên cứu | README chưa nhận giới hạn novelty | So sánh với PACE, PGS; **không** tuyên bố benchmark superiority | Câu chuyện học thuật đứng vững | Paper notes + economic audit |
| Operational guide | Có Fuji Demo User hướng dẫn cũ | Commands/runtime khác public judge | Link public runbook, judge local-mode startup, ngăn chain write vô ý | An toàn cho người đọc muốn tái hiện | Public runbook |
| Research archive | Có 4 docs research chỉ mục | Các nguồn mới sau ngày tách nhánh chưa được nhận diện | Giữ artifact cũ, thêm bảng CURRENT 2026-11-21 và historical sections | Không mất công sức nghiên cứu, tránh nguồn cũ “override” runtime mới | Research index, inventory, catalog |

## 3. Before / After

| Thuộc tính | Trước | Sau |
| --- | --- | --- |
| Headline | “AI có thể lập kế hoạch, quyền sử dụng tài sản phải được xác minh” | “Một giao dịch có thể hợp lệ. Cả chuỗi hành động vẫn có thể sai mục đích” |
| Product positioning | Treasury security với nhiều module | **Security control layer** cho autonomous on-chain treasury agents, scope 2 operation |
| Điểm khác biệt | Ba innovations được đặt ngang nhau | **ITAG + evidence-grounded purpose** là differentiator; các lớp còn lại là security architecture / integration |
| Kiến trúc | Mermaid và module names, stage order chưa đúng MVP | Ba zone, 16 bước, mỗi bước có mục tiêu/đầu vào/phương pháp/đầu ra/nguy cơ/giới hạn |
| Demo & evidence | V2/Demo User Fuji checkpoint trước | Public PolicyVaultMVP + confirmed payment/swap + guard refusal, giữ evidence cũ trong archive |
| Evaluation | 95,67% nổi bật nhất | Công khai original/baselines, chú thích đúng sample type và negative results |
| Runtime/Frontend | HTML/JS và Fuji serve kiểu cũ | React/TS/Vite/Nginx, judge public deployment theo runbook riêng |
| MEV | Có vẻ là một stage stress mặc định | Public có baseline/guards; reserve-shift stress được ghi rõ thuộc research/LOCAL |
| Public interaction | Attack choices dễ bị hiểu là live attack | **Sáu UI previews**, không inject backend, public guard chính sách là case khác |

## 4. Technical corrections và claims đã hạ mức

1. **Không viết:** “Tất cả public swap đã chạy MEV sandwich stress.” **Viết:** runtime có baseline simulation và các bounded guards; hypothetical reserve-shift experiments ở LOCAL/research.
2. **Không viết:** “Hybrid AI tốt hơn deterministic 95,67%.” **Viết:** constraints-only và Hybrid đều 95,67% trên same adapted regression; AI value phải xét riêng semantic ITAG.
3. **Không viết:** “ITAG AI chặn 8/12 attacks.” **Viết:** deterministic ITAG có 8/12 scripted interventions; graph-aware model v3.2 có 7/8 validated conflict *observations*.
4. **Không viết:** “Có sáu attack trên web đã bị chặn live.” **Viết:** sáu UI attack previews không tạo backend attack jobs; separate public policy guard `PAYEE_NOT_ALLOWED` bị từ chối trước broadcast.
5. **Không viết:** “Chạy contract V2/website chỉ HTML/JS.” **Viết:** PolicyVaultMVP/LFJSwapAdapterV3 và React/TS/Vite static frontend; các phiên bản cũ là historical/research.
6. **Không viết:** “Đã phát minh ra PDR, Z3 hay on-chain postconditions.” **Viết:** kết hợp các cơ chế có prior work (PACE/PGS) với long-horizon intent security và evidence grounding.
7. **Không viết:** “Public receipts chứng nhận mọi main HEAD.” **Viết:** release-specific acceptance trên `develop` và hashes/transactions được ghi ở JSON; README branch không phải deploy.
8. **Không viết:** “Z3 đã chứng minh mọi trạng thái EVM.” **Viết:** bounded off-chain proof với trusted token/price/oracle assumptions, Phi enforce trên những fields được ràng buộc.

## 5. Bằng chứng mới đưa vào

| Loại | Nội dung | Mức xác minh |
| --- | --- | --- |
| Public deployment | PolicyVaultMVP + LFJSwapAdapterV3, 13 owner setup transactions | Deployment journal + code-hash checks |
| Public settlement | Browser payment 0,01 test USDC; receipt, payee delta và gas | `PUBLIC FUJI` confirmed |
| Public settlement | Browser swap 0,000001 test USDC → WAVAX; receipt, token deltas và gas | `PUBLIC FUJI` confirmed |
| Public security refusal | Payee not allowlisted → no signature/broadcast | Public backend refusal trace |
| Browser evidence | React UI, refresh resume job ID, panels, no duplicate POST | Acceptance JSON, release-specific |
| TaskShield | A/B/C/D, structured constraints, unknown cases | `REGRESSION` (không independent) |
| ITAG | 12 adverse/12 benign scripted; live-model semantic v3.2 | `SCRIPTED` và `REAL MODEL` tách riêng |
| Local enforcement | Two authorized swaps and withheld third | `LOCAL ANVIL` receipts/counterfactual |

## 6. Giới hạn chưa được xác minh

- **Không có** end-to-end public Fuji attack chain đa bước hoặc hidden-purpose attacker đã được nghiệm thu; long-horizon benchmark nhỏ và do nhóm dựng.
- **Không có** independent held-out AI security test quy mô lớn hoặc external mainnet security audit.
- **Không có** ảnh chụp màn hình thực từ browser acceptance report (report ghi `screenshots_taken=false`): các SVG là **editorial diagrams**, không tự nhận là product screenshots.
- **Không chứng nhận lại runtime** hoặc phát sinh Fuji transaction trong tác vụ chỉnh docs này; source và acceptance report đã được đối chiếu thông qua GitHub.
- **Không có** đảm bảo mọi thời điểm public demo pass: Chainlink freshness, token funds, quota, session expiry, provider status và gas có thể chặn.
- **Không có** so sánh định lượng PaceVant vs PACE/PGS trên common benchmark.
- **Không merge/rebase** mã nguồn từ `main` vào nhánh review: current evidence được dẫn bằng **URL GitHub trỏ main** khi file không tồn tại trong branch này.

## 7. Checklist nghiệm thu

- [x] Headline rõ failure mode dài hạn và sản phẩm
- [x] Phân biệt cumulative deterministic với semantic purpose drift
- [x] Kiến trúc 3 zone + 16 stage có Input/Purpose/How/Output/Threat/Limitation
- [x] Phi, Z3, signed EIP-712 approval và PolicyVaultMVP diễn giải đúng scope
- [x] Không đưa MEV research thành default public runtime
- [x] React/TS/Vite frontend và public website đã cập nhật
- [x] Public Fuji contract/payment/swap/guard có nguồn
- [x] Tách scripted / real-model / local / public / historical
- [x] Phân biệt PACE/PGS prior work với research differentiator ITAG
- [x] Không sửa source logic hoặc merge/rebase
- [ ] Screenshot/GIF product thật **chưa có trong source**; không bịa để trang trí
- [ ] Live website availability / current balance **không được tái kiểm chứng** trong task docs này
- [ ] Render kiểm thị giác desktop/mobile độc lập **chưa thực hiện**; chỉ kiểm SVG markup/refs/heading/source
- [ ] Independent security review / benchmark lớn hơn vẫn là future work

## 8. Tài liệu và artifact được giữ nguyên

Bản sửa chỉ thay đổi docs/asset SVG. Vẫn giữ nguyên [TaskShield benchmark](../evaluation/HYBRID_TASK_ALIGNMENT_RESULTS.md), [ITAG final](../evaluation/itag-final/FINAL_VALIDATION.md), [semantic reliability](../evaluation/itag-semantic-reliability/FINAL_REPORT.md), [Research Index](RESEARCH_INDEX.md), [Experiment Catalog](EXPERIMENT_CATALOG.md), [Technology Inventory](TECHNOLOGY_INVENTORY.md), [Security Coverage Matrix](SECURITY_COVERAGE_MATRIX.md) và các reports lịch sử để kiểm chứng sự tiến hóa của hệ thống.

**Kết luận:** điểm mạnh của PaceVant không nằm ở việc sử dụng nhiều thuật toán, mà ở việc **mỗi security gate giải quyết một failure mode khác nhau**, được nối với quyết định cấp quyền có bằng chứng và khả năng thực thi on-chain trong phạm vi nhiệm vụ rõ ràng.
