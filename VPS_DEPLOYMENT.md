# PaceVant — native Ubuntu deployment, không Docker

> **Public Fuji hiện đã bật trên VPS.** Dùng [Public Fuji runbook](docs/PUBLIC_FUJI_RUNBOOK.md) và [system review hiện hành](docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md). Các đoạn cài mới/model-only/fork và acceptance chưa confirmed bên dưới mô tả cấu hình mặc định trước migration; không áp dụng chúng đè lên service public đang chạy. Public data là `/var/lib/pacevant/judge-public`, service chỉ có Attestor/Relayer keys, Owner key bị cấm. Public timeout 900 giây, oracle wait 720 giây; các security window giữ nguyên.

Target: Ubuntu 22.04 x86_64, 2 vCPU/4 GB RAM/50 GB SSD. Runtime: Python 3.12/uv + FastAPI/Uvicorn + native Anvil/Z3 + SQLite, Nginx static frontend/reverse proxy, systemd. React được build bởi Vite, không có Node server/SSR. Node chỉ cần lúc build release.

Đã triển khai trên **Ubuntu 22.04, 2 vCPU/4 GB** tại **https://pacevant.live**, Nginx/systemd native. HTTPS và simulated certificate renewal đã pass. Xem `docs/audit/vps-live-acceptance.json` cho kiểm tra thật; báo cáo WSL cũ giữ nguyên phạm vi lịch sử. Live transactions vẫn phụ thuộc oracle/model/gates; public MVP chưa được kích hoạt.

## Vận hành nhanh trên VPS hiện tại

Code Git nằm ở `/opt/pacevant-source`; release ở `/opt/pacevant/releases/<sha>`, bản active là `/opt/pacevant/current`. Không đặt project trong `/root`. State nằm ở `/var/lib/pacevant/judge`. Bản `.env` đầy đủ được user cho phép copy nằm tại `/etc/pacevant/private/source.env`, root-only 0600; service chỉ dùng model-only `/etc/pacevant/judge.env` 0640. Không đưa secrets vào Git hoặc frontend.

```bash
# Lấy develop mới nhất, build, restart, healthcheck; giữ state và TLS
sudo pacevant-update

sudo systemctl status pacevant-judge nginx --no-pager
sudo journalctl -u pacevant-judge -n 60 --no-pager
sudo bash /opt/pacevant/current/scripts/vps/restart.sh
sudo bash /opt/pacevant/current/scripts/vps/rollback.sh <existing-release-sha>
```

`pacevant-update` từ chối checkout dirty hoặc branch khác `develop`; pull fast-forward, không force/reset. `/etc/pacevant/deploy.env` chứa URL public cho healthcheck sau khi Certbot redirect HTTP. Đã sửa checksum replay Windows/Linux và healthcheck chờ startup tối đa khoảng 30 giây. Cập nhật cùng SHA đang active chỉ kiểm health, không rebuild. Model env thay đổi cần restart service. Deploy có thể ngắt job đang chạy; chọn lúc `/readyz` có `busy=false`.

## 1. Cài native tools

SSH bằng operator account có sudo, clone repository:

```bash
sudo git clone --branch develop https://github.com/ursuswh-metamorphic/PaceVant.git /opt/pacevant-source
cd /opt/pacevant-source
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

## 7. Phạm vi nghiệm thu

SSH/domain/config đã được cung cấp và triển khai thực tế. HTTPS, service restart, health/config, browser và recordings được kiểm riêng với live transaction outcomes. Payment acceptance trên VPS gặp stale oracle; swap có economic risk PASS nhưng ITAG trả `ITAG_SEMANTIC_UNCERTAIN`, chưa ký. Không nới policy để ép success. Chưa có multi-day soak/reboot test và chưa có live transaction CONFIRMED trên VPS. Website/replay hoạt động không đồng nghĩa dependency của mọi giao dịch luôn sẵn sàng.
