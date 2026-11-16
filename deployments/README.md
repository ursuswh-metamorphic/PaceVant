# Deployment manifests

`npm run deploy:local` tạo `execution-local.json` (gitignored). `npm run deploy:fuji` tạo `execution-fuji.json` sau khi có cấu hình attestor của A. Manifest chứa addresses, chain ID và bytecode hashes thật; không tạo địa chỉ placeholder.

Manifest Fuji/Smart Account của PoC trước đây đã được loại bỏ vì không phải deployment PolicyVault v1.1. Xem tài liệu lịch sử trong `docs/` nếu cần tra lại.
