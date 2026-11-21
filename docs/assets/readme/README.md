# PaceVant README — Thư viện visual assets

> Các file SVG trong thư mục này là **ảnh vector biên tập cho tài liệu GitHub**, không phải screenshot từ frontend đang chạy. Source text được giữ trong SVG để có thể cập nhật và review như code.

| Asset | Hiển thị | Nguồn dữ liệu / ngữ cảnh |
| --- | --- | --- |
| [hero-dark.svg](hero-dark.svg) | Hero khi GitHub dark mode | Nhận diện sản phẩm, minh họa quyền hạn → verification → PolicyVault |
| [hero-light.svg](hero-light.svg) | Hero khi GitHub light mode | Nội dung giống dark; cấu trúc riêng tối ưu tương phản |
| [attack-defense.svg](attack-defense.svg) | LOCAL Anvil budget isolation | 2 × 10 USDC trong ngân sách 20 USDC; request thứ ba bị chặn trước ký. Đọc [evidence gốc](../../evaluation/itag-final/ANVIL_BUDGET_ISOLATION.json) |
| [metrics.svg](metrics.svg) | Kết quả nổi bật | Public Fuji MVP payment/swap acceptance 21/11/2026; 8/12 deterministic ITAG scripted adverse; 95,67% TaskShield component regression (constraints-only bằng điểm) |
| [innovations.svg](innovations.svg) | Ba lớp năng lực (không tuyên bố mọi lớp đều novel) | Task Integrity, Long-Horizon ITAG, Proof-Bound Execution |
| [architecture.svg](architecture.svg) | Tổng quan 3 vùng security, source-aligned | Sơ đồ khái quát public MVP; [source workflow hiện hành](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/backend/src/treasury_backend/modules/workflows/treasury.py) định nghĩa thứ tự thực tế. MEV reserve stress thuộc nghiên cứu LOCAL |

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

> **Lưu ý checkpoint:** SVG `metrics.svg` hiện hiển thị public payment + swap từ [current acceptance](https://github.com/ursuswh-metamorphic/PaceVant/blob/main/docs/audit/public-fuji-live-acceptance-20261121.json), và phân biệt rõ dữ liệu scripted ITAG/TaskShield regression. Các biểu đồ SVG là graphic biên tập, **không phải screenshot runtime**.
