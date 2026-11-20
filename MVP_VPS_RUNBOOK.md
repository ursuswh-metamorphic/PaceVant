# PaceVant — vận hành web demo trên VPS

Cập nhật 21/11/2026, Asia/Saigon. Source đã có phục hồi request, readiness, liveness watchdog và cấu hình hosting. Chưa triển khai lên VPS thực tế, chưa build image trong môi trường này vì Docker Linux engine không hoạt động. Public PolicyVaultMVP vẫn cần Owner migration/signature; không coi việc gom tiền giữa các ví là nghiệm thu contract mới.

## Mức sẵn sàng có thể cam kết

Web có thể giữ dashboard/history/evidence và tiếp tục phục hồi sau restart. Một giao dịch mới chỉ chạy khi token/route/giá, oracle, model provider, session, vốn và ngân sách còn hợp lệ. Không thể cam kết giao dịch luôn success tại mọi thời điểm khi testnet/Chainlink/provider có thể gián đoạn hoặc pool sai giá. UI báo điều kiện còn thiếu, tự refresh có backoff, không giả dữ liệu hay nới economic risk để che lỗi.

Preset mặc định: forward swap **0,000001 USDC**, payment **0,01 USDC** đến Owner-approved EOA. Chọn preset rồi bấm Verify and execute. Không tự chuyển sang reverse hoặc protocol khác khi một route bị chặn. Mỗi submission vẫn qua toàn bộ pipeline.

## Chuẩn bị một lần

1. Owner thực hiện migration đã review, fund **5 USDC** vào vault mới đã xác minh, ký manifest. Không gửi vào predicted address chưa có code.
2. Copy public V2 manifest vào `deploy/treasury-fuji-v2.json`, signed MVP manifest vào `deploy/treasury-fuji-mvp.json`. Giữ V2 history; không overwrite để giả compatibility.
3. Tạo private `deploy/runtime.env` theo template, chỉ chứa Attestor/Relayer keys, ba service credentials khác nhau và model credentials. Không copy root `.env` hay Owner private key lên server. Không đưa token vào frontend bundle.
4. Copy `deploy/hosting.env.example` thành `deploy/hosting.env`, điền hostname thực. DNS trỏ VPS, cho phép 80/443. File này chỉ có hostname, không wallet/service secrets.
5. Dùng một backend instance/worker và persistent disk. Compose chỉ publish frontend loopback 8080 và HTTPS entrypoint, không publish RPC Anvil hay execution backend riêng.

```bash
docker compose --env-file deploy/hosting.env -f compose.yaml -f compose.mvp.yaml -f compose.vps.yaml config --quiet
docker compose --env-file deploy/hosting.env -f compose.yaml -f compose.mvp.yaml -f compose.vps.yaml up -d --build
```

Caddy cấu hình [automatic HTTPS](https://caddyserver.com/docs/automatic-https) và reverse proxy theo hostname. Certificate state nằm trong persistent volumes. Mở `https://<hostname>`; browser cần HTTPS để dùng credential và request identity an toàn. Organizer cấp operator access cho người được phép demo; public visitor không được nhận system credentials. Không mở unauthenticated raw execution.

## Readiness và vận hành

* `/healthz`: process liveness; không gọi oracle/model. Backend watchdog kiểm tra mỗi 30 giây, sau ba lỗi liveness liên tiếp thì thoát để Compose restart. Oracle/session hết hạn không làm restart loop.
* `/readyz`: HTTP 200 khi có ít nhất một preset đủ điều kiện sơ bộ, 503 khi chưa đủ. `/mvp/readiness` luôn trả JSON trạng thái/route-specific reasons. Đây không phải attestation hay guarantee transaction success.
* Readiness được cache tối đa khoảng 20 giây, không chạy model, không cấp nonce hay gửi transaction. Giao dịch luôn kiểm lại state thật. Concurrent probes không xếp hàng vô hạn.
* Dashboard vẫn hiện số dư on-chain khi giá chưa verified; allocation USD được đánh dấu unavailable. Không ký bằng giá zero/fallback.
* Backend đang xử lý vault sẽ từ chối nhanh request mới bằng `MVP_EXECUTION_BUSY_RESUME_REQUEST`, giữ HTTP worker cho status/recovery. Model inference bị giới hạn theo deadline còn lại, tối đa 180 giây và có safety margin; lỗi provider không chuyển mock.
* Pending request key/body/deadline được ghi vào sessionStorage **trước POST**, không lưu credentials. Mất response/reload: đăng nhập lại, Resume dùng GET theo key/workflow ID; nếu chưa accepted thì gửi lại đúng key/body, không tạo payment mới. Không xóa storage khi trạng thái còn unknown.
* Polling có backoff và dừng khi tab hidden; không broadcast từ background poll. Retry POST không do proxy tự thực hiện.

Nginx dùng resolver Docker để không giữ upstream IP cũ sau backend recreation, không tự retry proxy mutation. Tham chiếu [Nginx proxy semantics](https://nginx.org/en/docs/http/ngx_http_proxy_module.html). Compose có init, grace period 90 giây, restart policy và log rotation; xem [Docker Compose reference](https://docs.docker.com/reference/compose-file/services/). Container đưa log ra stdout để rotation có tác dụng, không tạo backend.log vô hạn bên trong volume.

## Session và budgets cho tuần demo

Draft Owner config mới, **chưa áp dụng public**, trong `fixtures/mvp/OWNER_REVIEW_REQUIRED.json`:

| Thông số | Draft |
|---|---:|
| Policy/session lifetime | 7 ngày |
| Max actions/session | 500 |
| Max payment | 0,1 USDC |
| Payment aggregate/payee daily | 1 USDC |
| Payment aggregate/payee session | 5 USDC |
| Preset payment | 0,01 USDC |
| Initial treasury funding | 5 USDC |

Loss threshold, uncertainty bands, oracle freshness và signature/Phi enforcement giữ nguyên. Draft `owner_reviewed=false`; regenerate unsigned migration để Owner duyệt lại. Đây là khả dụng **trong thời hạn và vốn đã cấp**, không indefinite spending. Payment đi về Owner; treasury không tự thu lại tiền để reset cap. Không giữ Owner key trên VPS để auto-renew/fund.

Khi gần hết session, Owner chuẩn bị renewal không redeploy contract:

```bash
uv run --locked python tools/operations/prepare_mvp_renewal.py --manifest deploy/treasury-fuji-mvp.json
```

Tool tạo **3 unsigned transactions**: rotate policy lifetime (giữ economic thresholds/daily counters), create replacement session, authorize hai operation. Dừng yêu cầu mới và đối soát pending trước rotate. Owner ký bên ngoài backend, sau inclusion chạy `seal_mvp_manifest.py --plan data/mvp-owner-renewal.json`, Owner ký manifest mới, thay file atomically rồi restart backend. Không xóa DB/volume; không redeploy hay auto-reset budget.

## Restart và kiểm tra trước khi mời giám khảo

Restart dùng cùng volume: kiểm `/healthz`, `/readyz`, dashboard và các pending IDs. Không dùng `docker compose down -v`. Giữ database, proof artifacts, raw journal và system expense ledger; backup khi backend dừng để có snapshot SQLite nhất quán.

Kiểm tra trên VPS thật: HTTPS/certificate, DNS/proxy sau backend restart, signed manifest/code/session, actual treasury balance/Relayer gas, real provider availability, persistent data và disk space. Sau Owner activation, chạy một payment nhỏ và forward swap, kiểm public canonical receipts/actual effects/gas. Không cần chạy lại attack suite để kiểm một cấu hình hosting.

Nếu oracle chưa đủ fresh, chờ round mới. Nếu reverse bị `LFJ_UNSUPPORTED_ROUTE` hoặc `ORACLE_PRICE_DEVIATION`, giữ reject. Nếu hết session/action/payment budget, Owner review/renew/refill. Nếu broadcast unknown/reorg/replacement, đối soát cùng hash trước khi gửi mới. Những tình huống này không được sửa bằng cách kéo deadline sau ký hoặc xóa journal.
