# Deployment manifests

> **DOC STATUS: COMPONENT_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

`npm run deploy:local` tạo `execution-local.json` (gitignored). `npm run deploy:fuji` tạo `execution-fuji.json` sau khi có cấu hình attestor của A. Manifest chứa addresses, chain ID và bytecode hashes thật; không tạo địa chỉ placeholder.

Manifest Fuji/Smart Account của PoC trước đây đã được loại bỏ vì không phải deployment PolicyVault v1.1. Xem tài liệu lịch sử trong `docs/` nếu cần tra lại.
