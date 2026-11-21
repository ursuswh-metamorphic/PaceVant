# Vận hành Judge demo public Fuji

Website: https://pacevant.live. Nhánh triển khai: **develop**. Trạng thái và bằng chứng hiện hành: [system review](PACEVANT_CURRENT_SYSTEM_REVIEW.md). Các hướng dẫn fork cũ trong repo không mô tả chế độ đang chạy trên VPS.

Hai kịch bản thực sự tiêu tài sản testnet:

- Payment: **0,01 Circle USDC**, Vault → một trong ba EOA đã duyệt; Relayer trả AVAX gas.
- Swap: **0,000001 Circle USDC → WAVAX**, qua LFJ V1, output về Vault; Relayer trả AVAX gas.

Mở Demo trực tiếp, chọn kịch bản bình thường và chạy. Panel hiện trạng thái xử lý; bấm từng module để xem dữ liệu thật. F5 trong cùng trình duyệt/tab sẽ khôi phục phiên. Sau CONFIRMED, mở link Fuji để kiểm receipt. Minh chứng/History lưu các lượt chạy của visitor đó; không phải lịch sử mọi visitor.

Mỗi nghiệp vụ có đúng hai ca bất lợi: payment tăng amount/phát lại nonce, swap hạ minOutput/đổi router. Nút chạy tạo job backend thật, lưu request idempotent và lịch sử như giao dịch thường. Các ca này dùng `eth_call` trên trạng thái Fuji lịch sử: chạy lại giao dịch đối chứng thành công trước, rồi kiểm đúng custom-error selector của calldata bị sửa/nonce đã dùng. Không ký mới, không broadcast, không chạy AI và không được gọi đây là bằng chứng phát hiện prompt injection. RPC/đối chứng lỗi là UNAVAILABLE, không được tính là chặn thành công.

Chainlink public Fuji không luôn có round đủ mới. Runtime chờ tối đa **720 giây**, timeout job **900 giây**, vẫn giữ oracle age 300 giây. Nếu quay video ba phút, bắt đầu khi oracle đang fresh; không giả tiến độ hoặc gọi replay là giao dịch live. Session/policy được gia hạn ngày 21/11/2026 đến epoch **1795861661**, 500 hành động, ngân sách payment 5 USDC. Owner cần gia hạn/cấp vốn khi hết budget, server không có Owner key. Cookie visitor mặc định 30 ngày và gia hạn khi gọi API, giữ nguyên visitor/history/quota qua restart. Tab vẫn giữ request chưa rõ kết quả để Resume đúng key/body/attack.

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

Một job đồng thời; 6 runs/visitor/ngày, 6 starts/IP/giờ, 30 runs toàn hệ thống/ngày. Cả ca bất lợi cũng chịu quota. Vault đã được thu hồi tiền demo và bổ sung lên 5 USDC; payment tiếp tục giảm số dư. Không tự reset cap hay giữ Owner key trong daemon để thu tiền. Operator dừng nhận job mới, đối soát pending rồi chạy công cụ sau từ máy giữ khóa; mặc định chỉ xem kế hoạch:

```bash
uv run --locked python tools/operations/maintain_mvp_demo.py --journal data/maintenance-UNIQUE-BATCH
# Thêm --broadcast để thực hiện; thêm --renew khi cần phiên 7 ngày mới.
# Retry phải giữ nguyên journal; batch mới dùng thư mục mới.
```

Công cụ thu phần USDC payment vượt khoản dự trữ 20 USDC tại Attestor/Relayer về Vault, Owner bù đến 5 USDC; giữ AVAX trả gas. Renewal giữ nguyên economic thresholds, payees và daily counters, chỉ cấp phiên/ngân sách tuần mới. Sau renewal cập nhật signed manifest và restart khi không có job; public signing/send journals được giữ lâu dài. Kiểm tra số dư Vault, AVAX Relayer, expiry và budget khi vận hành lâu dài. Gas Fuji trong receipt là phí thực trả tại thời điểm đó, không phải báo giá gas cố định. Các kiểm tra thời gian giả lập/restart không thay thế việc soak liên tục nhiều ngày trên VPS.
