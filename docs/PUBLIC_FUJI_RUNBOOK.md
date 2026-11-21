# Vận hành Judge demo public Fuji

Website: https://pacevant.live. Nhánh triển khai: **develop**. Trạng thái và bằng chứng hiện hành: [system review](PACEVANT_CURRENT_SYSTEM_REVIEW.md). Các hướng dẫn fork cũ trong repo không mô tả chế độ đang chạy trên VPS.

Hai kịch bản thực sự tiêu tài sản testnet:

- Payment: **0,01 Circle USDC**, Vault → một trong ba EOA đã duyệt; Relayer trả AVAX gas.
- Swap: **0,000001 Circle USDC → WAVAX**, qua LFJ V1, output về Vault; Relayer trả AVAX gas.

Mở Demo trực tiếp, chọn kịch bản bình thường và chạy. Panel hiện trạng thái xử lý; bấm từng module để xem dữ liệu thật. F5 trong cùng trình duyệt/tab sẽ khôi phục phiên. Sau CONFIRMED, mở link Fuji để kiểm receipt. Minh chứng/History lưu các lượt chạy của visitor đó; không phải lịch sử mọi visitor.

Các lựa chọn tấn công hiện là preview, chưa chèn tấn công backend. Guard backend riêng kiểm policy thật; lỗi provider/oracle không được coi là phát hiện tấn công.

Chainlink public Fuji không luôn có round đủ mới. Runtime chờ tối đa **720 giây**, timeout job **900 giây**, vẫn giữ oracle age 300 giây. Nếu quay video ba phút, bắt đầu khi oracle đang fresh; không giả tiến độ hoặc gọi replay là giao dịch live. Session/policy hiện hết hạn epoch **1795832966**; Owner cần gia hạn/cấp vốn khi hết budget, server không có Owner key.

## Cập nhật code trên VPS

Chờ phiên hiện tại kết thúc rồi chạy:

```bash
curl -fsS https://pacevant.live/judge/config
sudo pacevant-update
systemctl is-active pacevant-judge nginx
curl -fsS https://pacevant.live/healthz
```

Chỉ update khi `busy=false`; deployment restart service nên không thực hiện giữa một phiên. Source `/opt/pacevant-source`, releases `/opt/pacevant/releases/<sha>`, current symlink `/opt/pacevant/current`. Không reset DB, xóa journal hay chạy lại deployment contract khi update application.

Public data nằm tại `/var/lib/pacevant/judge-public`. Private service environment `/etc/pacevant/judge.env` có explicit public activation, signed manifest path và **chỉ Attestor/Relayer keys** cùng model credentials. Owner/deployer keys bị cấm trong service. Bản source env riêng do operator giữ không phải environment của daemon.

Nếu cần tạo lại public service config, thực hiện bằng operator trên VPS đã có release:

```bash
cd /opt/pacevant/current
sudo .venv/bin/python tools/operations/configure_public_judge.py \
  --source /etc/pacevant/private/source.env \
  --output /etc/pacevant/judge.env \
  --manifest /opt/pacevant/current/deployments/mvp-fuji.json \
  --data-dir /var/lib/pacevant/judge-public
sudo chown root:pacevant /etc/pacevant/judge.env
sudo chmod 640 /etc/pacevant/judge.env
# Chỉ restart sau khi hết phiên đang chạy.
sudo systemctl restart pacevant-judge
```

Không bật lại env fork/model-only lên service public. Không đưa private env, cookie browser, signing journals hay wallet keys lên Git. Không mở Anvil RPC, port 8000 hoặc admin API ra Internet.

Một job đồng thời; 6 runs/visitor/ngày, 6 starts/IP/giờ, 30 runs toàn hệ thống/ngày. Khoảng 1 USDC được cấp cho Vault ban đầu; payment giảm dần số này, không có vòng chuyển tự động từ EOA trở lại Vault. Kiểm tra số dư Vault, AVAX Relayer, expiry và budget khi vận hành lâu dài. Gas Fuji trong receipt là phí thực trả tại thời điểm đó, không phải báo giá gas cố định.
