# Hình thiết kế hệ thống V2.1

SVG được render từ 10 khối Mermaid trong [system design hiện tại](../../AI_Treasury_Security_System_Design_v2.1.md), theo thứ tự xuất hiện. Đây là engineering diagrams của code/config hiện có; topology deploy mô tả cấu hình dự kiến, không xác nhận đã có hosting/Fuji deployment.

| Hình | SVG | Nội dung |
| --- | --- | --- |
| 1 | [Runtime](01-runtime.svg) | FastAPI, workflow, execution, proof, stores và chain |
| 2 | [Module dependencies](02-modules.svg) | Composition, client port và shared SDK |
| 3 | [Trust boundaries](03-trust.svg) | Owner/operator/attestor/relayer và vault giữ tài sản |
| 4 | [Successful workflow](04-workflow.svg) | Goal → simulation → proof → sign → relay → receipt |
| 5 | [Atomic vault execution](05-vault.svg) | Checks, counters, external call, postconditions và rollback |
| 6 | [State machine](06-states.svg) | Logical workflow transitions, pending và reorg |
| 7 | [Submission recovery](07-recovery.svg) | Lost broadcast response và known-hash recovery |
| 8 | [Storage model](08-storage.svg) | Control/execution logical data model |
| 9 | [Deployment](09-deployment.svg) | Frontend/backend, durable disk, fork processes và admin |
| 10 | [Commitments](10-commitments.svg) | Call/evidence/proof/Phi hashes đi vào ApprovalV2 |

Source có thẩm quyền là các khối Mermaid trong file design. Khi sửa diagram, cập nhật SVG tương ứng; không chỉnh text trong SVG rồi để source lệch. Một số khái niệm được rút gọn để dễ đọc, các chú thích dưới mỗi hình trong system design xác định giới hạn: EVALUATING là logical grouping, records–submissions là logical binding, proof artifacts không bắt buộc có compiled Phi nếu proof không thành công.

Rendered/checked bằng Mermaid 11.12.2 và disposable headless Chrome. Đây là tooling tạo docs, không phải dependency của backend/frontend runtime. Các SVG dùng native SVG text, không cần Mermaid/Node để xem. Không nhúng khóa, token, địa chỉ ví cá nhân hoặc dữ liệu private runtime.
