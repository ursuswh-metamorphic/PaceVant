# Rà soát Live Demo: 12 bước, kỹ thuật, USP và bằng chứng xử lý

> Checkpoint trước khi chỉnh sửa. Các phát hiện đã được xử lý trong [bản hoàn thiện và kiểm chứng](LIVE_DEMO_OBSERVABILITY_20261121.md); nội dung dưới đây giữ nguyên để đối chiếu lịch sử.

Ngày kiểm tra: **21/11/2026, Asia/Saigon**. Đối tượng: source đang có trong workspace, nền Git `9174ffd` với các thay đổi frontend có sẵn của người dùng. Không thay đổi source frontend/backend trong lượt rà soát này.

## Kết luận

**12 ô đủ làm khung trình bày luồng bảo vệ giao dịch hiện hành, nhưng giao diện chưa thể hiện đầy đủ kỹ thuật, USP và quá trình xử lý của từng bước. Chỉ đổi chữ “module” thành “bước” chưa đáp ứng yêu cầu minh bạch đầu vào → xử lý → đầu ra.**

Backend có 16 thư mục nghiệp vụ, không đồng nghĩa có 16 bước chạy tuần tự hay 16 dịch vụ. Một số là điều phối/lưu trữ/giám sát, một số là compatibility/optional. Không nên đưa tất cả lên graph như thể chúng đều chạy trong mỗi demo.

Luồng payment thành công mới có **11 sự kiện timeline** nhưng hiển thị **12 ô**: `Relayer & PolicyVault` và `Receipt` cùng sử dụng `OUTCOME`; Receipt còn đọc `RECONCILIATION` khi có. Đây là cách chia phần trình bày hợp lý, không phải bằng chứng của 12 module độc lập.

## Bằng chứng và giới hạn kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Frontend thông thường `5173`, backend `18040` | Ban đầu `enabled=false`, `configured=false`, mode `ANVIL_FORK`; Live chưa bật |
| Phiên kiểm thử riêng | Frontend `5174`, backend `18041`, chỉ nạp cấu hình model; `ANVIL_FORK`, không nạp khóa ký ví public |
| Payment chạy mới | **CONFIRMED**, job `judge_32f1907ddf55416faab15e6807246aa7`, 11 sự kiện, 12 ô verified |
| Payment thực nhận | `10000` base units = **0,01 USDC**, `actual_deltas=[-10000,0,0,0]`, `payee_received=10000` |
| Môi trường kết quả payment | `ANVIL_FORK`, `public_chain_broadcast=false`, `public_chain_receipt=false` |
| Swap chạy mới | **UNAVAILABLE**, job `judge_15fde1c0381e43c2bc0b2273027d87d9`, `FRESH_CHAINLINK_SIGNING_WINDOW_UNAVAILABLE`, chờ khoảng 91,7 giây, chưa có workflow/model call/transaction |
| Sáu lựa chọn tấn công | Đều mở preview; tổng số POST tạo job phát sinh từ sáu preview là **0** |
| Mở từng ô | Kiểm tra đủ 12 ô trước chạy và sau payment, đồng thời quan sát panel ở các stage đang chạy |
| Hiển thị desktop/mobile, VI/EN | 36 lượt mở panel bằng response payment vừa thu: 12 VI desktop, 12 EN desktop, 12 VI mobile; 0 lỗi JavaScript và 0 trường hợp tràn ngang panel/page. Đây là kiểm tra hiển thị, không phải 36 lần thực thi |
| Bản ghi thành công payment/swap và guard | Render trực tiếp component hiện tại với `fixtures/judge/*.json`; đây là kiểm tra hiển thị bản ghi, không phải ba lần chạy mới |
| Kiểm tra trạng thái chạy chưa có kết quả | Tái hiện riêng bằng partial workflow, ghi nhãn synthetic; xác nhận panel chi tiết không render dù đã có dữ liệu upstream |
| Frontend regression | **21/21 tests passed**, 3 test files |
| Judge API và metrics regression | **10/10 tests passed**, 2 deprecation warnings từ dependencies |

Payment dùng model thật và EVM fork thật. Swap bị chặn bởi dependency là một kết quả kiểm tra hợp lệ, **không phải bằng chứng đã phát hiện tấn công**. Không thực hiện payment/swap public, không renew policy/session, không deploy contract. Không dùng kết quả testnet fork để chứng nhận trạng thái website production.

Harness ban đầu gặp lỗi locator khi mở accordion sau khi payment đã confirmed. Phần kiểm tra panel hoàn tất được tiếp tục bằng chính response payment vừa thu được, phục vụ lại riêng GET job cho trình duyệt kiểm thử. Payment không bị gửi lại. Phần swap tiếp theo đi qua backend thật. Báo cáo máy và script trong `data/live-module-audit/` ghi rõ ranh giới này.

## Bảng đối chiếu đủ 12 bước

Các mục “thiếu” bên dưới nói về khả năng giải thích/quan sát trên UI, không mặc định là backend chưa thực hiện kiểm tra.

| # | Bước | Input / output đang thấy sau khi có kết quả | Cần bổ sung để người dùng hiểu đầy đủ |
|---|---|---|---|
| 1 | Owner Policy | Output có policy/session active, pause, balances, authority, proof policy, allowlists. Chưa có khối input riêng. | Input từ manifest, chain/vault/session và block tham chiếu; tóm tắt role, code identity, expiry, ngân sách còn lại, giới hạn recipient. Phân biệt cấu hình Owner với kết quả đọc/kiểm tra hiện tại. |
| 2 | Agent & Intent | Request cố định, điều khoản trong accordion; output candidate intent và explanation. | Giữ request/điều khoản hiển thị khi AI đang chạy. Bảng đối chiếu yêu cầu gốc ↔ đề xuất, provider/model thực dùng, thời gian; làm rõ AI chỉ đề xuất trong phạm vi đã cấp quyền. |
| 3 | Trusted Builder | Input chủ yếu là typed intent; output min-output, quote, route, target/value; calldata ở phần bổ sung. | Input policy/context của builder, target registry và token/adapter identity. Giải mã phương thức/arguments thay vì bắt đọc calldata; giải thích báo giá LFJ và nguồn Chainlink độc lập. |
| 4 | EVM Simulation | Input hiển thị min-output/route; output before/after/deltas, received, allowances, gas và execution status. | Input chính là transaction/build và pinned block/context; hiện chưa đủ ở khối input. Tóm tắt tác động theo token, kiểm tra allowance, phân biệt ước lượng simulation với receipt thật. |
| 5 | Economic Risk | Input effects/proof-policy/oracle deadline; output PASS/FAIL, reasons, nguồn oracle, gas economics. | Bảng `điều kiện → giới hạn → giá trị đo → kết quả` cho freshness, debit, min-output, allowance, gas. Không trình bày PASS như lời giải thích cho mọi giới hạn kinh tế; một phần kiểm tra nằm ở builder/Z3/vault. |
| 6 | Shield + ITAG | Input chỉ intent và một phần build; output semantic verdict/summary, references, metadata và Shield check IDs. | **Đồ thị ITAG bị lọc khỏi panel**. Thiếu history được dùng, phân loại trust/provenance và kết quả từng interception. Shield hoạt động từ planning/build/simulation, không phải chỉ bắt đầu tại ô 6. |
| 7 | Z3 & Phi | Input Risk, ITAG, price intervals; output VERIFIED, Phi, risk/spend debit, assumptions, SAT/UNSAT. | Input build/effects đầy đủ hơn, từng nghĩa vụ với expected/actual, phạm vi giả định, đường liên kết Phi → hash được ký → constraint vault. Input thực của solver là intent/build/effects/context; Risk/ITAG là gate upstream, không nên gọi là toàn bộ đầu vào solver. |
| 8 | Security Decision | Input Risk/ITAG/Proof status; output verdict, reason và expiry, hashes ở phần bổ sung. | Bảng tổng hợp các gate với evidence refs, điều kiện phải đủ và bước tái kiểm tra tiếp theo. Không lẫn quyết định cho phép ký với xác nhận thực thi. |
| 9 | Attestor | Input SDE verdict/expiry và Phi; output signer, nonce, deadline, domain/chain/contract/hash metadata. | Intent/operation được ký, policy/session/proof bindings và kết quả revalidation/sign-once. Khi đang ký hiện không có input. Không cần công khai secret hay raw signed transaction. |
| 10 | Exact Preflight | Input signer/nonce/deadline; output mô phỏng cuối, balances/deltas/gas, exact-signed flag. | Liên kết build, operation, Phi/hash với payload đã kiểm tra; kết quả tái kiểm tra state trước relay. Tránh gây cảm giác đây là lần simulation ban đầu được phát lại. |
| 11 | Relayer & PolicyVault | Input preflight status; output `OUTCOME`, tx hash, block, deltas, gas/expense. | Mốc journal/reservation → submitted → confirmations và kiểm tra vault bằng evidence. Nhiều thao tác bảo vệ thật chưa có sự kiện công khai riêng nên UI chưa thể hiển thị trực tiếp. |
| 12 | Receipt | Output cùng `OUTCOME` như ô 11, thêm `RECONCILIATION` khi có; delta/received/gas. | Tóm tắt giao dịch thực tế ↔ intent/expected effects, trạng thái canonical/confirmations mới nhất, reconciliation/gas settlement. Đầu vào hiện lấy theo `OUTCOME` mapping nên lặp preflight giống ô 11. |

Sau payment, cả 12 ô có output. **11/12 ô có khối input**, Owner Policy chưa có. Có khối input không có nghĩa đã bao quát tất cả tham số backend sử dụng.

## Các USP đang được thể hiện đến đâu

| Kỹ thuật / USP thực tế | Trạng thái UI | Nhận xét |
|---|---|---|
| Quyền Owner và AI chỉ đề xuất | Có, khá rõ sau khi có kết quả | Cần đối chiếu term-by-term và role separation dễ đọc |
| Task Shield kiểm soát cả lời gọi và dữ liệu công cụ | Có nhãn, mô tả và IDs | Chưa thấy từng lần interception; vị trí ô 6 dễ làm người xem bỏ lỡ bảo vệ từ đầu luồng |
| Temporal ITAG, trust/provenance, history/citations | Có semantic summary và references | **Chưa thể hiện đầy đủ đồ thị và lịch sử** trong panel click |
| LFJ quote + Chainlink độc lập, pinned state/code identity | Có dữ liệu, phần lớn ở bổ sung/context | Thiếu lớp giải thích freshness/round/đối chiếu giá và identity checks |
| Đo effects bằng EVM simulation | Có before/after/delta/allowance/gas | Là một trong những phần thể hiện tốt hơn; cần đầy đủ input transaction/context |
| Economic risk; tách payment principal khỏi loss; tách gas khỏi trading loss | Có kết quả, debit và budget | Thiếu giải thích bằng số đo so với giới hạn, đặc biệt payment chuyển tiền nhưng risk debit có thể bằng 0 |
| Z3 bounded proof → Phi → ký → vault atomic enforcement | Có từng ô riêng và SAT/UNSAT | Chưa nối thành chuỗi bằng chứng dễ theo dõi; đây là USP nên làm nổi bật nhất |
| EIP-712 bound operation, nonce, expiry, revalidation | Có metadata | Thiếu bản đối chiếu các thành phần được bind và các lần kiểm tra lại |
| Sign-once/idempotency/journal/recovery chống gửi lặp | Có code và phục hồi session | Chưa có trình bày bằng chứng theo module; không cần biến persistence thành một ô giả lập độc lập |
| System Relayer trả phí và đối soát gas | Có payer/gasUsed/effective price/expense | Cần phân biệt fee fork/public, gas thực tế/giới hạn và không gọi token usage là hóa đơn USD |
| Owner pause/revoke/policy rotation | Được backend/contract kiểm tra | Đọc policy/pause phù hợp; không cần đưa nút quản trị Owner vào demo anonymous |
| Test chống tấn công | Sáu preview có mô tả các gate | **Chưa phải sáu bài kiểm tra được chạy trong frontend**; guard API riêng không được nối qua sáu lựa chọn này |

Autonomy/rebalance optional, legacy transfers và research code không phải tính năng đang được demo công khai trong luồng hai operation. Không nên đưa chúng vào danh sách kỹ thuật “đã chạy” chỉ vì có code trong repo.

## Phát hiện ưu tiên

### P1 — Input bị ẩn trong lúc xử lý và khi bước chưa có output

`StageDetail` trả `null` khi không tìm thấy event của chính bước, **trước khi** dựng input từ dữ liệu upstream. Vì vậy panel planning/build/simulation/ITAG/Attestor/preflight chỉ có guide và câu chờ, dù đã có intent hoặc kết quả bước trước.

Đã thấy trực tiếp trong payment chạy mới và tái hiện bằng partial Attestor có đủ SDE/Proof. Ảnh: [Attestor đang chạy](live-demo-modules-20261121/payment-running-ATTESTATION.png), [ITAG đang chạy](live-demo-modules-20261121/payment-running-ITAG.png).

Nguồn: [stage-detail.tsx](../../frontend/src/app/components/stage-detail.tsx), đoạn `if(!timeline.length||!workflow)return null` và `dependencies`.

### P1 — API có mốc stage, chưa có tiến trình con để frontend mô tả xử lý thật

Coordinator phát `active_stage` rồi lưu event với evidence khi một phần xử lý đã hoàn tất. Không có schema thống nhất cho `started_at`, checkpoint của từng kiểm tra, `completed_at`, duration và expected/actual. Frontend poll 1 giây; các bước ngắn có thể chuyển thẳng sang verified giữa hai lần lấy dữ liệu.

Trong payment, event PROOF đã tồn tại trong khi stage còn PROOF để xử lý Shield evidence; SDE event đã có khi còn cần kiểm tra lời gọi trước khi ký. Vì vậy label stage hiện tại cũng chưa giải thích hết tác vụ đang thực hiện. `runtime_metrics` có thông tin model ở kết quả cuối nhưng chưa được UI/types dùng để mô tả từng bước, và meter gán call theo active stage, không phải theo từng vai trò AI.

Muốn trình bày live từng thao tác cần backend emit thêm evidence/checkpoint; frontend không nên dựng checklist “đã đạt” từ timer hoặc từ mô tả tĩnh.

Nguồn: [treasury.py](../../backend/src/treasury_backend/modules/workflows/treasury.py), [judge_worker.py](../../backend/src/treasury_backend/operations/judge_worker.py), [App.tsx](../../frontend/src/app/App.tsx), [types.ts](../../frontend/src/app/lib/types.ts).

### P1 — ITAG graph bị bỏ khỏi panel

`ignored` chứa `graph`; cả phần hiển thị chính và supplemental đều loại nó. Bản payment mới có **3 graph nodes, 1 edge** và **6 Shield check IDs** ở thời điểm ITAG, nhưng click ô 6 không cho thấy graph/trust/history. Các check ID không tương đương kết quả kiểm tra chi tiết. Đây là số ở snapshot ITAG, không phải tổng số interception của cả workflow.

Raw evidence drawer cấp toàn workflow vẫn có thể chứa graph; do đó dữ liệu không mất ở backend, nhưng USP không dễ khám phá tại nơi người dùng đang xem.

Nguồn: [stage-detail.tsx](../../frontend/src/app/components/stage-detail.tsx), [temporal/operations.py](../../backend/src/treasury_backend/modules/temporal/operations.py), [evidence.tsx](../../frontend/src/app/components/evidence.tsx).

### P1 — Sáu lựa chọn “mô phỏng tấn công” chưa chạy kiểm tra backend

Đã mở đủ ba lựa chọn cho payment và ba lựa chọn cho swap. `onRun` rẽ sang `setAttackPreview(true)` thay vì `api.start`. Không có POST nào tạo job từ sáu thao tác đó. Disclosure có nói là bản mô tả, nhưng “Mô phỏng tấn công”, “sẽ chặn đứng” và “qua 12 lớp” vẫn dễ bị hiểu như một kết quả đã kiểm thử hoặc bảo đảm cho mọi lớp.

Nên ghi rõ **“Xem mô tả tình huống — chưa chạy kiểm tra”**; nếu muốn chứng minh attack prevention, nối từng preset được hỗ trợ vào runner có evidence thực, hiển thị gate dừng và lý do. Không gọi lỗi model/oracle là phát hiện tấn công. Guard preset phía server hiện có không tự chứng minh sáu tình huống UI này đã được thực thi.

Nguồn: [App.tsx](../../frontend/src/app/App.tsx), [attack-select.tsx](../../frontend/src/app/components/attack-select.tsx).

### P2 — Nhiều input quan trọng và phép đối chiếu còn thiếu ở lớp đọc chính

Ví dụ simulation chỉ nhận min-output/route trong khối input, chưa chỉ transaction/build/context; ITAG chưa hiện history/trust graph; Proof input hiển thị gate upstream nhưng chưa thể hiện đủ intent/build/effects/context. Risk chủ yếu trình bày PASS và metadata, thiếu expected/actual. Revalidation, sign-once, journal/gas reservation có thật trong code nhưng chưa có trace công khai chi tiết.

Một phần giải quyết bằng curator frontend; một phần cần backend phát thêm dữ liệu. Không nên tuyên bố “hiện đầy đủ quy trình” chỉ vì có raw JSON ở drawer toàn cục.

### P2 — Đơn vị và localization chưa nhất quán ở nested evidence

Các trường như `per_payment`, `per_day`, `per_session`, `session_spent`, `daily_spent` chưa có quy tắc đổi base units/nhãn rõ ràng trong `Facts`; một số tham số gas/budget cũng hiển thị như số thô. Chẳng hạn cap USDC có thể xuất hiện là `100000` thay vì `0.1 USDC`. Nhiều nhãn bổ sung và assumptions vẫn là tiếng Anh/tên nội bộ trong giao diện tiếng Việt. Slot thứ ba của balance registry đang là phần dự phòng/disabled của MVP nhưng hiển thị “Tài sản khác”.

Cần registry định nghĩa asset, decimals, đơn vị và ý nghĩa từng trường; không dùng vị trí mảng hoặc tên gần giống để suy đoán cho mọi operation tương lai.

### P2 — “12 module độc lập” và “phát hiện vi phạm” mô tả chưa đúng

Overview vẫn có “12 mô-đun bảo mật độc lập”; progress/panel vẫn gọi module. Nên đổi đồng bộ sang **“12 bước trong quy trình bảo vệ giao dịch”**.

Swap chờ oracle rồi UNAVAILABLE được giữ đúng, nhưng `BlockReason` vẫn dùng nhãn **“Bước phát hiện vi phạm” / “Intercepted at gate”**. Đây là dependency không sẵn sàng, không phải bằng chứng có giao dịch vi phạm. Nên dùng “Bước dừng / lý do chưa thể tiếp tục” cho unavailable/error, dành ngôn ngữ vi phạm cho rejection có evidence tương ứng.

Nguồn: [overview-copy.ts](../../frontend/src/app/lib/overview-copy.ts), [execution-panels.tsx](../../frontend/src/app/components/execution-panels.tsx), [run-session.tsx](../../frontend/src/app/components/run-session.tsx).

### P2 — Receipt có thể hiện kết quả cũ và mới liên tiếp mà chưa ưu tiên trạng thái mới

Node state dùng outcome/latest evidence, nhưng panel render toàn bộ `OUTCOME` rồi `RECONCILIATION` theo thứ tự cũ → mới, cùng heading “kết quả”. Hàm `stage()` lấy event đầu tiên cho các dependency. Tái hiện bằng dữ liệu synthetic: `OUTCOME=CONFIRMED`, sau đó `RECONCILIATION=REORGED`, node unknown nhưng panel vẫn hiện “Đã xác nhận” trước trạng thái mới.

Đây là rủi ro diễn giải tái hiện được, **không phải một reorg đã xảy ra trong payment mới**. Nên đặt latest verified state lên đầu và đưa sự kiện cũ vào lịch sử có timestamp.

Nguồn: [workflow-nodes.ts](../../frontend/src/app/lib/workflow-nodes.ts), [stage-detail.tsx](../../frontend/src/app/components/stage-detail.tsx), [format.ts](../../frontend/src/app/lib/format.ts).

## Cấu trúc panel nên có

Giữ 12 ô hoặc gom phần nhìn thành nhóm đều được. Bên trong mỗi ô cần cùng một cấu trúc:

1. **Vai trò và phạm vi:** bảo vệ điều gì, không tự cấp quyền cho điều gì.
2. **Đầu vào:** dữ liệu đã có, nguồn bước nào, block/time/evidence refs; hiển thị ngay cả khi đang chờ kết quả.
3. **Đang xử lý:** chỉ những checkpoint backend thực sự phát; phân biệt waiting/running/passed/rejected/unavailable/unknown/skipped.
4. **Kết quả từng kiểm tra:** điều kiện, ngưỡng, giá trị quan sát, verdict, lý do.
5. **Đầu ra và chuyển tiếp:** artefact/hash nào đi vào bước kế tiếp.
6. **Bằng chứng kỹ thuật:** mở rộng cho người cần đối chiếu, có đơn vị và nhãn rõ ràng, latest state lên đầu.

Ví dụ nội dung ô ITAG cần là `intent + transaction + owner scope + history → graph/trust/citation checks → semantic verdict + evidence references`, thay vì chỉ `PASS + danh sách IDs`.

Event contract tối thiểu để làm được phần live: `stage_id`, `event_type`, `occurred_at`, `input_refs`, `check_id`, `expected`, `observed`, `status`, `reason_code`, `output_ref`; duration từ mốc thật. Giữ giải thích ngắn đã có từ model; không biến raw model reasoning thành tiến trình xử lý và không tự tạo intermediate results.

## Thứ tự thực hiện đề xuất

1. Sửa `StageDetail` để input độc lập với sự tồn tại của output; bổ sung nguồn input đúng cho 12 ô. Đổi thuật ngữ module/bước và copy unavailable/preview.
2. Hiển thị ITAG graph/trust/history và bảng actual-vs-limit của Risk/Oracle; thống nhất units/labels.
3. Phát sự kiện checkpoint an toàn từ backend cho Shield interception, revalidation, sign-once, journal, submission và reconciliation. Sau đó mới xây timeline xử lý con.
4. Nối chuỗi proof/Phi → typed hash/attestor → preflight → vault/receipt để USP đọc được theo một đường đi.
5. Kiểm tra lại payment/swap/guard, unavailable và recovery/reorg bằng nguồn bằng chứng được ghi nhãn; kiểm tra desktop/mobile và VI/EN. Không dùng timer hoặc bản ghi để giả làm một lượt chạy live.

## Artefact

- [Kết quả kiểm tra và metadata lưu cùng báo cáo](live-demo-modules-20261121/summary.json).
- [Payment hoàn tất](live-demo-modules-20261121/payment-desktop.png), [swap dừng do oracle](live-demo-modules-20261121/swap-desktop.png), [panel Z3 trên mobile](live-demo-modules-20261121/detail-390-6.png).
- [Báo cáo máy từ browser](../../data/live-module-audit/browser-report.json).
- [Payment response mới](../../data/live-module-audit/payment-job.json), [swap response mới](../../data/live-module-audit/swap-job.json).
- [Kiểm tra component và partial state](../../data/live-module-audit/render-report.json).
- [Kiểm tra hiển thị bản payment vừa thu](../../data/live-module-audit/display-report.json).

`data/` là khu vực ignored theo quy ước repo. Các link này có hiệu lực trong workspace hiện tại; không mặc định đã được commit hoặc publish. Báo cáo này không phải chứng nhận bảo mật tổng thể, kiểm tra mọi execution branch hay xác nhận mới cho production.
