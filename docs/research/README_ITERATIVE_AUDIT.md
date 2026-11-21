# README PaceVant — Báo cáo tự phản biện nhiều vòng

> **Docs-only · review branch · 21/11/2026.** Đây là tự đánh giá chất lượng **truyền đạt kỹ thuật của README**, không phải kiểm toán an ninh, chứng nhận benchmark, ý kiến của giám khảo thực tế hay xác nhận website hiện luôn khả dụng. [README](../../README.md) · [Báo cáo repositioning vòng trước](README_REPOSITIONING_REVIEW.md).

## Phương pháp: lặp đến khi qua rubric nhưng không bỏ qua khuyết điểm

- **Vòng 0 — hiện trạng trước lượt chỉnh:** README đã có dữ liệu nghiên cứu tốt, nhưng một lần phản biện trước chấm **8,1/10** do phần kiến trúc quá dày, hình ITAG chỉ nêu budget và khó theo dõi bằng chứng E2E.
- **Vòng 1 — sửa thông điệp/kiến trúc/bằng chứng:** Giữ 16 bước giải thích ở tài liệu chuyên sâu; README rút còn 8 chặng, có ba câu hỏi trực quan; bổ sung semantic purpose-drift visual và **một job Fuji gắn các gate verdict, proof hash, attestation và receipt**. Tự kiểm thấy vẫn còn chữ nhỏ trên mobile và thiếu hai nghiên cứu trong bảng prior work; **chưa được coi là hoàn thành**.
- **Vòng 2 — sửa những lỗi tự phát hiện:** Thêm infographic mobile, nguồn evidence minh bạch, glossary 16 thuật ngữ cho người mới, bổ sung đủ **4 bài báo nền tảng**, phân biệt graph-vs-history là research question chưa được giải quyết độc lập. Kiểm tra 25/25 relative file/image links có thể fetch trên review branch; giữ deep-dive và research catalog. Qua rubric tổng hợp dưới đây.

## Rubric cuối: 9.19/10 (tự đánh giá có trọng số)

| Tiêu chí | Trọng số | Điểm thành phần | Đóng góp |
| --- | ---: | ---: | ---: |
| Thông điệp & định vị | 17% | 9.5/10 | 1.61 |
| Độ đúng kỹ thuật so với code hiện hành | 20% | 9.3/10 | 1.86 |
| Bằng chứng & provenance | 19% | 9.4/10 | 1.79 |
| Dễ hiểu kiến trúc | 17% | 9.1/10 | 1.55 |
| Trung thực nghiên cứu & novelty | 14% | 9.2/10 | 1.29 |
| Đọc lướt, điều hướng, liên kết | 8% | 8.7/10 | 0.70 |
| Visuals / accessibility | 5% | 8/10 | 0.40 |
| **Tổng** | **100%** |  | **9.19/10** |

**Tại sao không cho 10/10?** README chính vẫn dài; hình SVG chưa được browser screenshot/render review độc lập; semantic visual là illustration chứ không phải ảnh UI thật; chưa có full raw-stage evidence chain tái dựng từ bên ngoài; benchmark graph vs plain-history LLM chưa thực hiện; chưa có third-party reviewer đánh giá readability. Vì vậy tự chấm visual chỉ **8/10**, navigation **8,7/10**, research honesty **9,2/10** chứ không tự nhận hoàn hảo.

**Mốc >9 là ngưỡng chấm theo rubric viết tài liệu do nhóm tự áp dụng**, không thể đảm bảo mọi giám khảo sẽ cho trên 9. Những giới hạn khách quan được liệt kê rõ để người đọc tự phản biện.

## Những thay đổi có thể kiểm chứng

| Vấn đề phát hiện | Cách sửa | Đường kiểm chứng |
| --- | --- | --- |
| 16 bước kỹ thuật làm README khó đọc | Tách overview **8 chặng**, giữ bản giải thích **16 bước x 6 câu hỏi** và glossary riêng | [Architecture Explained](../architecture/ARCHITECTURE_EXPLAINED.md) |
| KPI ITAG bị đồng nhất với phép cộng ngân sách | Giữ case budget là deterministic, thêm purpose-conflict illustration với nhãn rõ **real-model lab vs live Fuji** | [Semantic graphic](../assets/readme/purpose-drift.svg) · [Semantic report](../evaluation/itag-semantic-reliability/FINAL_REPORT.md) |
| Hình dễ quá nhỏ trên mobile | Thêm portrait 600×1060 px, chữ lớn hơn, responsive source trong README và link open-full-size | [Mobile SVG](../assets/readme/purpose-drift-mobile.svg) |
| Blockchain receipt không tự cho thấy Risk/ITAG/Z3 | Truy vết **job `judge_05e0231adab44474a7fff9fcacd7c48e`** từ reported stage verdict đến on-chain public tx, phơi bày những phần cần raw logs bổ sung | [Fuji Workflow Evidence](../evidence/FUJI_WORKFLOW_EVIDENCE.md) |
| Thiếu đối chiếu hai bài báo nền tảng | Bổ sung Auditable LLM Arbiter (LAST-X/NDSS 2026) và cross-layer survey (ICT Express 2026), cùng PACE/PGS | [Prior-work section](../../README.md#chúng-tôi-khác-gì-với-những-hướng-trước) |
| Overclaim ITAG là full causal graph | Giải thích public graph hiện dùng Task/Candidate/Mandate/Recent outcomes và cạnh `AUTHORIZES`; đồ thị tổng quát và ablation graph-vs-text chưa có | [ITAG operation source](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/backend/src/treasury_backend/modules/temporal/operations.py) |
| Lẫn lộn loại evidence | Phân biệt SCRIPTED / REAL-MODEL / LOCAL ANVIL / PUBLIC FUJI / HISTORICAL, không cộng các mẫu số | [Evaluation section](../../README.md#đánh-giá-kết-quả-ablation-và-cả-thất-bại) |

## Các kiểm tra thực sự đã làm khi chỉnh tài liệu

- Đọc README trực tiếp từ branch review trước và sau mỗi nhóm thay đổi; dùng SHA file của GitHub để tránh ghi đè vô tình.
- Đối chiếu mã điều phối `TreasuryWorkflows.run()`, ITAG `temporal/operations.py`, Solidity `PolicyVaultMVP/V3`, frontend `package.json` và public Fuji acceptance ở ref `main`.
- Đối chiếu số liệu: TaskShield Hybrid **95,67% = constraints-only 95,67%** trên 300 adapted swaps; ITAG **8/12 scripted deterministic interventions**, **7/8 validated real-model semantic observations** trên sample nhỏ; không gom thành security accuracy.
- Kiểm `ARCHITECTURE_EXPLAINED.md`: đúng **16 stage headings**, mỗi stage đủ **Input / Mục đích / Cách làm / Output / Chặn / Giới hạn**.
- Kiểm **25/25** paths file/asset được tham chiếu trực tiếp trong README có thể truy cập bằng connector GitHub trên đúng review branch (ba batch). Đây là existence check, không phải render test hoặc kiểm mọi external HTTP URL.
- Thêm ảnh giải thích purpose drift có `alt` text và responsive mobile variant, **chưa chạy screenshot browser acceptance** cho lần chỉnh docs này.
- Không chạy model benchmark mới, không thực thi giao dịch Fuji, không sửa backend, contract, configs hoặc secrets. Các tx được dẫn từ đã có báo cáo công khai.

## Giới hạn không thể sửa bằng README

1. Public **Fuji website** chỉ hỗ trợ fixed USDC payment / swap, không phải wallet đa người dùng cho arbitrary DeFi; sáu attack UI choices hiện là preview.
2. **Graph-specific value** chưa có paired ablation `plain history + LLM` vs `graph-aware LLM` trên cùng cases; semantic sample có repetitions và labels chưa reviewed độc lập.
3. Full **raw chain of custody** từ authenticated intent / model/tool traces / proof queries đến typed EIP-712 bytes chưa được độc lập dựng lại chỉ từ acceptance JSON; nguồn công khai hiện là summarized stage report + public RPC receipt.
4. Chưa có **independent audit**, mainnet, production custody hoặc broad adverse evaluation, không hứa mọi prompt injection/MEV đều được chặn.
5. Visual chưa có screenshot thật từ `pacevant.live`, desktop/mobile GitHub render chưa kiểm pixel-level; font và viewBox kiểm mức code/source, không tự nhận visual QA đã hoàn tất.

## Kết luận của lượt tự phản biện

**Đạt 9.19/10 theo rubric nội bộ cho chất lượng viết/giải thích.** Điểm tăng vì người đọc giờ có thể đi theo tuyến **problem → phân biệt deterministic/semantic → architecture → proof of integration → source/benchmark**, trong khi **không làm mất** 16-stage deep dive, Research Index, Experiment Catalog, Technology Inventory và Security Coverage Matrix.

**Không coi điểm này là bảo chứng về bảo mật của PaceVant.** Nếu cần điểm cao hơn từ giám khảo thực tế, nên bổ sung video/screenshot thật, independent reader test và benchmark graph-vs-text, không chỉ sửa câu chữ.
