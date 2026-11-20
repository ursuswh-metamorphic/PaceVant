# PaceVant README — Thư viện visual assets

> Các file SVG trong thư mục này là **ảnh vector biên tập cho tài liệu GitHub**, không phải screenshot từ frontend đang chạy. Source text được giữ trong SVG để có thể cập nhật và review như code.

| Asset | Hiển thị | Nguồn dữ liệu / ngữ cảnh |
| --- | --- | --- |
| [hero-dark.svg](hero-dark.svg) | Hero khi GitHub dark mode | Nhận diện sản phẩm, minh họa quyền hạn → verification → PolicyVault |
| [hero-light.svg](hero-light.svg) | Hero khi GitHub light mode | Nội dung giống dark; cấu trúc riêng tối ưu tương phản |
| [attack-defense.svg](attack-defense.svg) | LOCAL Anvil budget isolation | 2 × 10 USDC trong ngân sách 20 USDC; request thứ ba bị chặn trước ký. Đọc [evidence gốc](../../evaluation/itag-final/ANVIL_BUDGET_ISOLATION.json) |
| [metrics.svg](metrics.svg) | Kết quả nổi bật | 95,67% adapted 300-case TaskShield regression; 8/12 scripted adverse ITAG; public Fuji receipt checkpoint trước Hybrid PR #10 |
| [innovations.svg](innovations.svg) | Ba đóng góp | TaskShield, ITAG, proof-bound on-chain enforcement |
| [architecture.svg](architecture.svg) | Tổng quan 3 tầng | Sơ đồ khái quát; không thay thế luồng chi tiết và trust boundaries trong [system design](../../AI_Treasury_Security_System_Design_v2.1.md) |

## Những ảnh *chưa có* và không nên giả lập

- **Screenshot frontend thực tế:** chỉ thêm sau khi chụp từ phiên bản backend/UI xác thực; loại bỏ private credentials, thông tin người dùng và journal nội bộ.
- **GIF/video attack → defense:** quay từ UI thật với mode LOCAL Anvil/scripted hoặc real-model được ghi rõ; gắn workflow/trace tương ứng.
- **ITAG graph screenshot:** chụp từ graph viewer có task/revision, evidence và quyết định tương ứng; không dựng graph giả rồi gọi là test result.

Không nâng cấp clip diễn giải thành “public Fuji adversarial execution” nếu trên thực tế tình huống chỉ chạy LOCAL. Không viết mọi báo cáo vào SVG và không sửa số liệu không truy được về raw artifact.

## Hướng dẫn dùng trên GitHub

- Hero dùng `<picture>` với `prefers-color-scheme: dark/light`.
- Các asset còn lại dùng `<img src="docs/assets/readme/...svg" width="100%">` để GitHub render và thu phóng tương đối.
- Text, diagram và kết quả cần có phần **HTML alt text** trong README, kèm link về báo cáo bằng chứng.
- Nếu thay đổi metrics, cập nhật đồng thời SVG, văn bản README và citations. Không tự suy số liệu mới từ commit vừa push.

[Quay lại README chính](../../../README.md)
