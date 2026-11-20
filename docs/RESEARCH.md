# Nghiên cứu chính thức — 12/11/2026 (giờ Việt Nam)

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

> Historical / compatibility document. For the current runtime use [V2.1 system design](AI_Treasury_Security_System_Design_v2.1.md) and [readiness audit](audit/V2_1_READINESS_REVIEW.md). Old A/B layouts, PoC evidence and removed pre-refactor paths describe their original checkpoint; they are not current deployment instructions or new validation evidence. References to removed artifacts are retained as plain code text.

## Kết quả xác nhận

- [Team1](https://team1vn.xyz/) cho phép dự án chạy trên Fuji. Không bắt buộc tạo L1. Một phần sản phẩm cần tích hợp Avalanche thực sự; phần tích hợp chiếm 25/100 điểm. Deadline công bố: 23:59 ngày 21/11/2026, giờ Việt Nam. Cần repository, slides và video demo 2–3 phút có quyền truy cập cho giám khảo.
- [Builder Hub event](https://build.avax.network/events/596c0b2d-63aa-4cf0-a0ad-a7e34ddbfdc0) xác nhận chương trình 2–30/11/2026. Địa điểm chung kết trên event khác FAQ Team1 hiện tại; cần xác nhận với ban tổ chức nếu dự chung kết. Không suy luận rubric bổ sung.
- [Starter catalog](https://team1vn.xyz/demos.html), dữ liệu [index.json](https://team1vn.xyz/demos/index.json): có `nft-mint-contract`, `wallet-connect-dapp`, `mint-from-the-ui`, `privy-agent-wallet` và các mẫu khác. Các mẫu blockchain đã xem được phục vụ bằng từng file/ZIP; không thấy GitHub repo riêng trong metadata của các mẫu đó. Catalog có GitHub cho NullMaps nhưng không liên quan PoC.
- Đã đọc [NFT README](https://team1vn.xyz/demos/nft-mint-contract/README.md), [deploy script](https://team1vn.xyz/demos/nft-mint-contract/scripts/deploy.mjs), [React ABI](https://team1vn.xyz/demos/mint-from-the-ui/src/lib/contract.ts), [Privy README](https://team1vn.xyz/demos/privy-agent-wallet/README.md). Tận dụng quy trình: kiểm chain → balance → deploy → receipt → public manifest → React read/write. Không sao chép code hay dùng preset mainnet. Privy mẫu tự ghi chưa kiểm thử live; cần tài khoản/secret và không phù hợp yêu cầu chính sách thực thi bằng contract, nên không chọn.
- [Primary Network](https://build.avax.network/docs/primary-network): C-Chain hỗ trợ EVM/Solidity. Fuji: chain 43113, [RPC](https://api.avax-test.network/ext/bc/C/rpc), [explorer](https://explorer-test.avax.network/c-chain).
- [C-Chain RPC](https://build.avax.network/docs/rpcs/c-chain): API Ethereum JSON-RPC; public node không giữ ví ký giao dịch. Receipt cung cấp gas thực tế; không dùng gas trong block header để tính chi phí giao dịch.
- [Hardhat integration](https://build.avax.network/integrations/hardhat) xác nhận dùng Hardhat với Avalanche. [Academy](https://build.avax.network/academy) có khóa Solidity; không yêu cầu học/tạo L1 cho PoC này.
- [Hardhat getting started](https://hardhat.org/docs/getting-started), [Node support](https://hardhat.org/docs/reference/nodejs-support), [viem tests](https://hardhat.org/docs/guides/testing/using-viem), [script deployments](https://hardhat.org/docs/guides/deployment/using-scripts): Node hiện có 24.21.0 phù hợp; sử dụng Hardhat 3, viem, node:test. Pin phiên bản và package-lock để tái lập.
- [Faucet chính thức](https://build.avax.network/console/primary-network/faucet): trang có bước kiểm tra điều kiện; không khẳng định mọi ví tự động được cấp vốn.

## Truy cập và phiên bản

Web reader không mở được hai trang Team1, nhưng Node fetch trực tiếp trả HTTP 200 cho cả hai và đọc được catalog cùng source ở trên. URL hướng dẫn Hardhat cũ `/docs/tooling/smart-contracts/hardhat` không đọc được; dùng integration và Hardhat docs hiện tại.

Npm registry tại thời điểm chạy: Hardhat 3.21.2, viem 2.57.19, Solidity/solc 0.8.38, React 19.3.1, Vite 8.3.8, OpenZeppelin Contracts 5.6.1. Package-lock là bằng chứng phiên bản thực cài. Không nâng phiên bản theo phỏng đoán.

## Quyết định kỹ thuật của PoC

Kết quả chạy thực tế bổ sung: Fuji public RPC giới hạn `eth_getLogs` 100 block mỗi request, đã thấy HTTP 429/Retry-After 60 và CORS trên trình duyệt. Vì vậy UI dùng proxy cùng origin, chia lô và cache tăng dần; đây là xử lý kỹ thuật từ kết quả đo, không phải quy định UniHack. Cấu hình proxy theo [Vite server.proxy](https://vite.dev/config/server-options#server-proxy) và [preview.proxy](https://vite.dev/config/preview-options#preview-proxy).

Đây là đề xuất triển khai, không phải quy định cuộc thi: hai contract, owner và agent riêng, native test AVAX, owner approve/execute riêng, revalidate recipient/limit/current agent khi thực thi, frontend React/Vite đọc public RPC và ký qua injected Core/MetaMask. Compiler cố định `evmVersion: cancun` theo yêu cầu người dùng. Local EVM chỉ kiểm chứng logic; không đại diện cho đo gas/thời gian trên Fuji. Không dùng dịch vụ trả phí, không mainnet, không private key trong frontend.
