# Quy chuẩn trình bày README PaceVant — Presentation & Typography v1

> **Phạm vi:** style guide cho README GitHub, **không** thay nội dung sản phẩm/benchmark, mã nguồn hay những ảnh glassmorphism đã được duyệt. Bản triển khai nằm trên nhánh `docs/readme-tieng-viet-review-20261121`.

## 1. Nguyên tắc biên tập

**Technical Editorial × Premium Security × Minimal Glass** — hình ảnh giữ màu trắng kính/xanh cobalt, còn văn bản dùng Markdown/GitHub typography mặc định để đọc rõ trên nhiều nền và có thể tìm kiếm.

- Người đọc phải nhận ra ngay **vấn đề → bằng chứng → kiến trúc → giới hạn** mà không cần nhìn nhiều nhãn màu.
- Chỉ dùng điểm nhấn khi có lý do: không in đậm cả đoạn dài để tạo cảm giác quan trọng.
- Không sửa một claim hay số liệu để làm đẹp. Nguồn và caveat luôn ở cạnh kết quả cần hiểu đúng.
- Không đưa CSS/font tùy ý vào GitHub README; font thương hiệu dùng cho SVG/PNG, văn bản README dùng typography chuẩn của GitHub.

## 2. Vai trò của từng kiểu chữ

| Vai trò | Quy định | Ví dụ |
| --- | --- | --- |
| Logo/hero | Dùng nguyên PNG đã duyệt; không viết chồng nội dung lên ảnh | `hero-glass.png` |
| Tagline | Dùng *italic* (trong HTML `<em>`) để nhẹ hơn heading/CTA | *Intent-Aware Security for Autonomous On-Chain Treasury Agents* |
| Heading H2/H3 | Giữ cấu trúc nội dung; tên heading mô tả vấn đề/giá trị, không dùng caption làm heading | `## PaceVant đã chạy thật được gì?` |
| **Bold** | Ưu tiên một điểm chính/đoạn, giữ nguyên bold ở metric và nhãn quan trọng; tránh chuỗi nhiều cụm bold liên tiếp | **Không cấp quyền ký** |
| *Italic* | Tagline, câu giải thích/giả định nhẹ, các khái niệm đối chiếu | *đúng nhiệm vụ* |
| `Inline code` | Hash, định danh, tên biến, operation, verdict được ghi dưới dạng dữ liệu kỹ thuật | `SWAP_EXACT_IN`, `PASS` |
| Badge | Tối đa 3–4 trạng thái có bằng chứng và click được về nguồn | Fuji Testnet, Research MVP, Not Audited |
| GitHub Alert | Chỉ dùng khi nếu đọc sai sẽ làm sai kết luận | `IMPORTANT` cho giới hạn của Fuji receipts, `WARNING` cho scope chưa chứng minh |
| `<details>` | Giữ chi tiết kỹ thuật phụ/nguồn bổ trợ có thể thu gọn; không giấu kết luận chính | Mermaid deep dive |
| Divider `---` | Chỉ dùng ở điểm chuyển ý lớn; không ngăn sau mọi H2 | Trước Evidence, Architecture, Evaluation, Library |

## 3. Quy tắc trình bày bằng chứng

1. Số liệu phải đứng cùng **mẫu số và môi trường**; 95,67%, 8/12, 7/8 không đồng nghĩa cùng một accuracy.
2. Sử dụng monospace cho verdict/machine-generated field; không coi `PASS` trong backend JSON là verified result được Snowtrace kiểm độc lập.
3. `PUBLIC FUJI`, `LOCAL ANVIL`, `REAL MODEL`, `SCRIPTED`, `HISTORICAL` và `NOT VERIFIED` là nguồn/ngữ cảnh khác nhau; nhãn phải được hiểu ngay tại chỗ.
4. Liên kết có tên mô tả nội dung thay vì nhãn chung chung như “click here”; giữ SHA/tx hash, source và raw evidence để người ngoài kiểm tra.
5. Không gắn badge `100% Secure`, `Audited`, `Production Ready` khi không có bằng chứng tương ứng.

## 4. Bảng, danh sách và trải nghiệm mobile

- Giữ bảng cho **baseline comparison, threat matrix, technology inventory, case/evidence mapping** vì đọc theo cột sẽ tốt hơn.
- Với **quy trình tám bước**, chuyển bảng rộng thành ordered list có hai dòng cho mỗi bước: *Câu hỏi thực tế / đầu ra* và *Nếu bỏ qua thì sao?*. Giữ nguyên 8/8 mô tả gốc.
- Không chèn nhiều ảnh mới làm gián đoạn mạch nghiên cứu. Các PNG đang có là bộ người dùng đã duyệt; không crop, regenerate hoặc thay thế khi chưa được yêu cầu.
- Tách các đoạn dài tại dấu kết câu, nhưng không thay từ hay ý. Dùng khoảng trắng để tạo nhịp đọc; tránh nhiều list trong một section ngắn.

## 5. Hero và trạng thái MVP

- Ảnh hero giữ nguyên. Tagline được chuyển từ chữ đậm sang italic để không cạnh tranh thị giác với logo.
- Navigation có **Live Demo · Security Evidence · Architecture · Research**, mỗi link dẫn đến tài liệu/trang đang tồn tại.
- Ba badge metadata có thể click: **Avalanche Fuji Testnet**, **Research MVP**, **Not Independently Audited**. Badge chỉ phản ánh các trạng thái sẵn có trong README; ảnh badge lấy từ Shields.io nên phụ thuộc dịch vụ ngoài.
- README không thêm H1 bằng chữ lặp lại tên ngay dưới hero vì ảnh đã hiển thị wordmark; đây là một trade-off thị giác. Nếu yêu cầu heading semantics/accessibility mạnh hơn, cần duyệt riêng thiết kế H1.

## 6. Đối chiếu trước và sau lượt chỉnh style

| Kiểm tra | Trước (README trước styling) | Sau |
| --- | ---: | ---: |
| Cụm bold Markdown | 164 | 146 |
| GitHub Alerts | 0 | 2 (`IMPORTANT`, `WARNING`) |
| Metadata badges đầu trang | 0 | 3 |
| Số dòng bảng Markdown | 84 | 74 (8 stage chuyển thành list) |
| Đường dẫn file/ảnh nội bộ | — | **24/24 tồn tại** trên review branch |
| PNG đã duyệt | 6 ảnh / 8 tham chiếu (hero xuất hiện ba lần) | **Giữ nguyên** đường dẫn và binary blobs |

**Kiểm tra tính toàn vẹn nội dung:** đối chiếu blob gốc `2c153647688d44da4609d4ca78089acb0a9c5a25` với README sau styling. Sau khi loại phần chỉ là điều hướng mới, badge mới và đoạn 8-stage được tái định dạng, phần văn bản được chuẩn hóa (bỏ ký tự emphasis/inline-code và whitespace) **khớp hoàn toàn**. Tám dòng kiến trúc được đối chiếu từng cell, không mất dữ liệu.

**Giới hạn QA:** các đường dẫn được xác minh theo GitHub repository source, không phải screenshot render. Chưa kiểm tra thực tế hiển thị trên GitHub desktop/mobile, accessibility reader hoặc tải Shields.io trên mọi mạng. Không thay source code, smart contract hay nhánh deploy.

## 7. Checklist cho mọi lần sửa README sau này

- [ ] Nội dung/claim/benchmark giữ nguyên trừ khi có yêu cầu biên tập nội dung riêng.
- [ ] Mỗi đoạn chỉ có các cụm bold thực sự mang nghĩa; không dùng bold thay cho heading.
- [ ] Các verdict, identifiers, paths dùng inline code khi cần tái hiện chính xác.
- [ ] GitHub Alerts xuất hiện hiếm, đúng loại và có nội dung source-backed.
- [ ] Bảng và danh sách chọn theo cách đọc trên mobile; không ép mọi giải thích vào bảng.
- [ ] PNG đã duyệt, alt text, liên kết evidence và raw SHA/hash còn nguyên.
- [ ] Diff không chứa thay đổi ngoài Markdown docs/metadata; không thay backend hoặc chain code.
- [ ] Source-level link checks và, khi có môi trường phù hợp, GitHub render screenshots cho light/dark, desktop/mobile.

[Quay lại README](../../README.md) · [Báo cáo self-audit nghiên cứu](README_ITERATIVE_AUDIT.md).