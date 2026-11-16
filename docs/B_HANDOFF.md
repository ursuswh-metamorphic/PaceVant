# Bàn giao control plane của thành viên A

Phạm vi và quyền sở hữu theo Guide Người A và Shared Integration Contract v1.1. System Design v1.0 được dùng cho kiến trúc tổng thể. B sở hữu calldata adapter, PolicyVault, EVM simulation, relayer và receipt.

## Chạy với B

1. Dùng `PACEVANT_MODE=LOCAL` với B và một EVM local có chain ID 43113. Dùng `FUJI` sau khi có Vault, token test và fork evidence Fuji. Hai profile có DB riêng mặc định và cần attestor key khác nhau trong vận hành. Profile `MOCK` tự sinh khóa phiên, bất kể cấu hình khóa.
2. Owner thực hiện cấu hình policy trên Vault. Người vận hành ghi read model `Mandate` do owner xác nhận vào `PACEVANT_MANDATE_FILE`. Xem cấu trúc trong `fixtures/mock/mandate.json` và thay địa chỉ, policy hash, version, giới hạn, stress policy và hạn sử dụng bằng giá trị của deployment. A đọc lại owner, token, router, hard limits, pause, policy hash/version và quyền ký qua B. Các giới hạn off-chain dựa trên read model đã đăng ký. Việc tự kiểm tra owner signature trên từng trường off-chain cần định nghĩa commitment và test vector từ B.
3. Cấu hình `PACEVANT_ORACLE_FILE` trỏ tới JSON do nguồn oracle test tin cậy ghi. Các trường gồm `chain_id`, `vault_address`, `price_usdc_usd_e8`, `price_wavax_usd_e8`, `price_source=TRUSTED_TEST_ORACLE` và `price_timestamp`. Giá là string e8, timestamp là Unix seconds. Cập nhật nguồn thực trước khi chạy, A chặn giá quá 60 giây. Ví dụ 1 USDC = `"100000000"` và 1 WAVAX = `"2000000000"` dùng cho fixture thử nghiệm.
4. Cấu hình `PACEVANT_B_URL` là HTTPS origin hoặc HTTP loopback. `B_TOKEN`, `OPERATOR_TOKEN` và `INTERNAL_TOKEN` dùng các Bearer credential riêng. Nạp attestor key bằng biến môi trường `PACEVANT_ATTESTOR_KEY`. Đặt owner và relayer ở các tiến trình riêng; A so sánh ba địa chỉ với chain context ở cổng ký và trước submit. Dùng `uv run --locked --env-file .env.local python scripts/serve.py` với file cấu hình riêng. Dashboard tích hợp chỉ được mount ở `MOCK`.
5. Gọi `POST /v1/workflows/start` với `goal` và `mandate_id`. A giữ workflow ID trong `X-Request-Id` khi gọi B, dùng khóa idempotency riêng cho build, simulate và execute. Theo dõi `GET /v1/workflows/{id}`. Nếu receipt chưa sẵn sàng, gọi lại GET để reconcile.

## Chi tiết wire đề xuất cho phần v1.1 chưa chốt

Các route và field đã công bố của `TransactionProposal`, `BuiltTransaction`, `SimulationEvidence`, `PortfolioSnapshot`, `EconomicRiskAssessment`, `SecurityDecision`, `SignedPDR` và `ExecutionResult` dùng theo v1.1. Model Python và JSON Schema nằm trong `packages/contracts-api`. A đã triển khai các chi tiết dưới đây cho mock và test double HTTP. B cần đối chiếu phần bổ sung này trước khi ghép thật.

| Surface | Trường và hành vi dùng ở A |
|---|---|
| `GET /v1/chain/context` | `deployment` (`LOCAL` hoặc `FUJI`), `chain_id`, `vault_address`, `owner`, `router`, `token_in`, `token_out`, `token_in_decimals=6`, `token_out_decimals=18`, `policy_hash`, `policy_version`, `paused`, `attestor`, `relayer`, `block_number`, `block_timestamp`, `bytecode_hash` của runtime Vault, `max_usdc_per_swap_base_units`, `max_usdc_spend_per_day_base_units`. Với query `nonce` trả `nonce_used`; với `fork_block` trả `fork_block`, `fork_block_hash` và `fork_block_timestamp`. Các giá trị hiện tại lấy từ block chain đã được chấp nhận, kể cả lúc reconcile. |
| `GET /v1/portfolio/onchain-snapshot` | `chain_id`, `vault_address`, `policy_hash`, `block_number`, `block_timestamp`, `usdc_base_units`, `wavax_base_units`, `utc_day` (Unix seconds chia nguyên cho 86400), `daily_spent_usdc_base_units` từ Vault, `daily_execution_cost_usd_e8` từ phí receipt thực trong ngày và `max_fee_per_gas_wei` theo cấu hình relayer. Số tiền và gas fee là string. |
| Evidence manifest | Các trường đã nêu ở v1.1 cộng với `fork_block_hash`, `fork_block_timestamp` và `artifact_hashes` dạng map logical ref → Keccak‑256 của bytes gốc. `evidence_root` lấy Keccak‑256 của manifest RFC 8785. |
| Evidence artifact refs | `artifact_refs[0]` là báo cáo JSON chuẩn hóa gồm `intent_id`, `build_id`, `nonce`, `deadline`, `simulation_mode`, `source`, `baseline` và `stress_tests` cùng giá trị với summary. A tải manifest và từng artifact qua `GET /v1/artifacts/{path}` cùng origin B. Ví dụ `artifact://simulation/build_001/report.json` ánh xạ sang `/v1/artifacts/simulation/build_001/report.json`. |
| Receipt monitor | Cả `SUBMITTED` và `PENDING` giữ reservation. `CONFIRMED` cần block, gas, event refs, input delta exact và output ≥ minOut. `REVERTED` cần hai delta bằng string `"0"`; `MIN_OUTPUT_NOT_MET` được ghi `PROTECTED_REVERT`. |

Trong `FUJI`, A còn dùng RPC Fuji công khai để đối chiếu chain ID, canonical fork block, thời điểm block và runtime code Vault tại fork và hiện tại. Chứng cứ `FORK_SIM` là điều kiện bắt buộc. Snapshot và fork phải trong phạm vi 3 block lúc quyết định và lúc ký, giá và block không quá 60 giây. B và Vault tiếp tục xác minh decoded calldata, nonce, policy, daily budget và postconditions. RPC của A chỉ dùng các phương thức đọc. [Avalanche C‑Chain RPC](https://build.avax.network/docs/rpcs/c-chain)

## Quy tắc ký và theo dõi

- `POST /v1/approvals/attest` chỉ nhận `decision_id` và yêu cầu internal token. `POST /v1/risk/evaluate` và `POST /v1/decisions` trả kết quả đã tính từ các tham chiếu khớp đúng DB, được tạo bởi orchestrator. Quy tắc này loại đường ghi kết luận do caller tự cung cấp.
- SQLite lưu decision immutable và có unique gate theo decision/nonce trước khi ký. Một vault được giữ chỗ đến khi receipt kết thúc hoặc có xác nhận hết hạn. A kiểm tra lại policy, artifact, nonce, số dư, budget và giá lúc ký và lúc submit. Deadline hiệu lực tối đa 30 giây, đồng thời nằm trong cùng ngày UTC của budget đã kiểm.
- `SUBMITTING` sau timeout nghĩa là A chưa có tx hash. Dùng khóa `execute-<decision_id>` để tra log hoặc idempotency record của B. Khi tìm được hash, chạy `uv run --locked --env-file .env.local python scripts/recover_submission.py <workflow_id> <tx_hash>`. CLI xác minh receipt của đúng decision/build/chain từ B trước khi chuyển trạng thái. Với nonce còn nguyên ở một block được B chấp nhận sau deadline, lần đọc workflow kế tiếp có thể kết thúc ở `EXPIRED`. Với nonce đã dùng, reservation giữ đến khi reconcile được receipt.
- `RECEIPT_MISMATCH` giữ reservation để điều tra qua receipt hiện tại của B. Khi preflight cho biết approval stale, workflow kết thúc; giao dịch mới đi qua build, mô phỏng, risk và chữ ký mới.
- Daily spend lấy từ Vault theo ngày UTC. A ước lượng phí với `gas_used × max_fee_per_gas_wei` và giá oracle WAVAX làm đại diện phí AVAX trong demo. Exposure dùng delta mô phỏng ở giá snapshot và số nguyên. Khi giá hoặc state dịch chuyển sau preflight, enforce exposure tại thời điểm thực thi cần thêm oracle/guard phía Vault. Đây là điểm nên ưu tiên nếu mở rộng ngoài demo.
- Chữ ký theo [EIP‑712](https://eips.ethereum.org/EIPS/eip-712), evidence manifest theo [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785). Hash chứng minh summary nào đã được cam kết. Chất lượng EVM simulation và độ tin cậy của evidence producer vẫn phụ thuộc B.

## Gate thực tế

| Gate | Kết quả hiện tại |
|---|---|
| A‑01 đến A‑10 | Kiểm thử bằng Python với fixture, negative cases và B HTTP test double |
| G0/G3 phía A | Schema và golden vector được kiểm qua Python và Solidity harness; B cần thử trên Vault và dữ liệu deploy của B |
| G2/G5 phía A | SDE, alignment, stale state, tampering, replay gate và phân loại protected revert đã được kiểm |
| G1/G4/G6 | Cần B cung cấp PolicyVault, EVM simulation thật, credential test và receipt local/Fuji |
