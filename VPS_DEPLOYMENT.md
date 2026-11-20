# PaceVant — native Ubuntu deployment, không Docker

Target: Ubuntu 22.04 x86_64, 2 vCPU/4 GB RAM/50 GB SSD. Runtime: Python 3.12/uv + FastAPI/Uvicorn + native Anvil/Z3 + SQLite, Nginx static frontend/reverse proxy, systemd. React được build bởi Vite, không có Node server/SSR. Node chỉ cần lúc build release.

Code/config đã chuẩn bị; chưa có SSH/domain của VPS đích, nên không tuyên bố deploy public VPS. Linux QA hiện có là **Ubuntu 24.04 WSL**, không phải Ubuntu 22.04 VPS. Xem `docs/audit/judge-deployment-report.json` cho phạm vi được kiểm thật.

## 1. Cài native tools

SSH bằng operator account có sudo, clone repository:

```bash
git clone --branch develop https://github.com/ursuswh-metamorphic/PaceVant.git
cd PaceVant
sudo bash scripts/vps/install.sh
```

Script cài OS dependencies, native Nginx/Certbot, dedicated user `pacevant`, uv **0.12.10**, managed Python 3.12 dưới `/opt/pacevant/python`, Node **24.21.0** và Foundry **1.7.1**. Node tar kiểm SHA-256 theo official checksums; Foundry theo digest release metadata. Không tự deploy contract hay đọc Owner key. Nếu checksum/digest không có thì dừng để review. Không đổi lockfile phiên bản dependencies.

| Đường dẫn | Vai trò |
|---|---|
| `/opt/pacevant/releases/<sha>` | Release immutable source/venv/build/artifacts |
| `/opt/pacevant/current` | Symlink tới release chạy |
| `/opt/pacevant/bin` | uv/node/npm/forge/anvil/cast native |
| `/etc/pacevant/judge.env` | Model-only private environment, root:pacevant 0640 |
| `/var/lib/pacevant/judge` | Persistent quota/jobs/evidence; không xóa khi restart |
| `/var/cache/pacevant` | Cache có giới hạn disk/quota checks |
| `/var/lib/pacevant/.svm` | Compiler cache được chuẩn bị ở build stage |

## 2. Secrets riêng, không root .env

```bash
sudo install -o root -g pacevant -m 0640 deploy/native/judge.env.example /etc/pacevant/judge.env
sudoedit /etc/pacevant/judge.env
```

Điền model provider credentials đã được review. Giữ `PACEVANT_SHIELD_MODE=wallet_pipeline`, fresh-oracle/risk gates. Có thể dùng SCP/SFTP qua SSH đến file tạm private trên VPS rồi `sudo install -o root -g pacevant -m 0640 <private-file> /etc/pacevant/judge.env`; không đưa secrets vào Git, URL, command arguments, clipboard frontend hay issue. Xóa file tạm sau khi cài.

**Không** upload root `.env`, Owner/Attestor/Relayer public signing keys hoặc operator tokens cho judge service. Startup/worker filtering từ chối/loại bỏ chúng. Các role ký trong mỗi fork được tạo tạm trong memory; keys không được persist/expose. Public RPC là HTTPS exact-configured source, chỉ native loopback Anvil được mutate. Serving không tự load `.env`.

Mặc định secure cookie ON. Có thể tắt chỉ trong QA localhost riêng; production HTTPS phải ON. Chưa có model key: frontend/replay vẫn chạy, live config báo Not configured. Không fall back scripted semantics tự động.

## 3. Deploy release từ develop

```bash
bash scripts/vps/deploy.sh
```

Script từ chối dirty checkout, fetch `origin/develop`, archive exact SHA sang release mới, `uv sync --locked --no-dev`, `npm ci --prefix frontend`, build Vite/TypeScript và Solidity một lần, chuẩn bị native compiler cache, cài unit/Nginx lần đầu, restart/smoke, báo SHA. Không git reset/discard production changes, không sửa env hay reset DB/counters. Nếu smoke fail, phục hồi previous symlink/service; giữ state.

SQLite migrations additive tự chạy lúc app khởi động, không cần chạy một engine khác. systemd chỉ một worker, User=pacevant, bind **127.0.0.1:8000**, Restart=on-failure, KillMode=control-group, timeout stop 30s, MemoryMax=2800M, CPUQuota=180%, TasksMax=192, private tmp, read-only system/source, state directories writable. Tối đa một heavy job; baseline fork có thể thêm một simulation fork tuần tự. Mỗi Anvil dùng một execution thread; process group được terminate/kill khi timeout. Những controls này là bounds, chưa là multi-day load/soak certification cho VPS 2 vCPU.

## 4. Nginx và HTTPS

Config `deploy/native/nginx.conf` phục vụ `/opt/pacevant/current/frontend/dist`. Proxy chỉ `/judge/`, `/healthz`, `/readyz` tới loopback backend. `/mvp/`, execution/admin/debug/docs/raw RPC public đều 404; không tự retry POST. Fixed 4 KB body limit, start/read IP limits và security headers.

Trên VPS mới, script chỉ tắt symlink welcome site mặc định khi checksum trùng cấu hình gốc của package Ubuntu; file cấu hình vẫn được giữ. Các site đã chỉnh sửa được giữ nguyên. Kiểm tra default server block của Nginx khi host có ứng dụng khác. Sau lần deploy đầu, sửa `/etc/nginx/sites-available/pacevant` đặt `server_name` thành domain thật. Deploy script sau đó giữ file TLS/domain này, không overwrite. Deploy lại cùng SHA đang active chỉ healthcheck, không sửa source/virtualenv đang phục vụ.

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d treasury.your-domain.example
sudo certbot renew --dry-run
```

DNS A/AAAA phải trỏ VPS, firewall cho 80/443 và SSH; không mở 8000 hoặc Anvil RPC. Nếu chưa domain, IP HTTP dùng smoke/read-only; không truyền operator credentials qua HTTP. Cấp TLS xong xác minh secure cookie và chạy public anonymous judge job nhỏ.

## 5. Kiểm health, restart, rollback

```bash
systemctl status pacevant-judge --no-pager
journalctl -u pacevant-judge -n 100 --no-pager
journalctl -u pacevant-judge -f
curl -fsS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8000/readyz
curl -fsS https://treasury.your-domain.example/judge/config
bash scripts/vps/healthcheck.sh
bash scripts/vps/restart.sh
bash scripts/vps/rollback.sh <existing-40-character-release-sha>
```

Healthcheck ghi rõ live ready hay chỉ application/replay reachable. `/readyz` hiện kiểm configured worker; live oracle/model availability vẫn phải qua từng request. Không restart service chỉ vì market/oracle khiến giao dịch reject.

Graceful shutdown dừng owned worker/process group. Nếu crash/reboot ở giữa fork job, DB đánh dấu INTERRUPTED và **không tự chạy lại**; job đó không có public asset movement. Same-key lookup trả record cũ, không tạo attempt mới. Current live operator journals ở luồng cũ không bị sửa/xóa bởi judge adapter.

## 6. Vận hành nhiều ngày

* Persistent quota/job DB, sáu visitor runs/ngày, sáu/IP/giờ, global 30/ngày, một job cùng lúc, timeout 240 giây; runtime values có thể giảm trong env.
* Fixed server presets; anonymous request không có amount/token/recipient/calldata fields. Request Origin check, Strict/HttpOnly visitor cookie và Nginx quota là lớp bổ sung, không thay nonce/policy/proof của vault.
* Chỉ model keys được pass cho worker; native Anvil subprocess còn lọc environment tiếp. Không lưu raw provider errors có credential vào public result.
* Disk threshold tối thiểu 512 MB trước job; source cache 60 giây; run directories hoàn tất quá bảy ngày được dọn khi service startup, job/evidence trong SQLite giữ nguyên. Theo dõi `df -h`, không xóa DB để refill quota.
* Nginx logs theo logrotate hệ thống; cấu hình journald `SystemMaxUse=200M` theo chính sách VPS nếu cần, không thay global logging của host khi chưa review.
* Backup state khi service dừng hoặc dùng SQLite online backup cho consistent snapshot. Rollback chỉ release, không rollback/xóa database hoặc on-chain state.
* Không giữ Owner key trên VPS để auto-renew/fund. Public contract migration là công việc riêng, vẫn yêu cầu Owner review/sign; website fork không đòi public migration.

## 7. Cần bạn cung cấp để nghiệm thu VPS

SSH endpoint/account/quyền sudo, domain/DNS và private model-only environment. Không cần dán private keys vào chat. Khi chưa có access, phần đã giao là **VPS deployment prepared**, chưa phải deployment accepted. Cần smoke trên Ubuntu 22.04 thực tế, HTTPS, resource cap, service restart/reboot (khi được cho phép), persistent quota/history và một live fork job dưới tải đo được.
