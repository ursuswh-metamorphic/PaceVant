# Chuẩn bị chạy toàn hệ thống trên Fuji

> **DOC STATUS: HISTORICAL_REFERENCE - OLD / SUPERSEDED.** Retained checkpoint/reference only; not current system state, readiness or operating instructions.
> Use the [current system design](../AI_Treasury_Security_System_Design_v2.1.md) and [documentation index](../README.md). Addresses, defaults, test counts and limitations below belong to their original checkpoint. Raw evidence keeps its original scope.

Live update 2026-11-20: [Circle / Chainlink / full Fuji demo](../demo/FUJI_LIVE_END_TO_END.md). Earlier faucet-USDC blockers and controlled/mock descriptions below belong to their historical profiles.


Lượt kiểm tra ngày 19/11/2026 đọc public Fuji, số dư của ba ví đã cấu hình và các route LFJ. Các private keys tiếp tục ở private env.

## Kết quả đọc chain

Ở block 61339012, ví owner có khoảng 0,0483 test AVAX, attestor có khoảng 0,0005 test AVAX và relayer có 0 AVAX. Cả ba ví có 0 Circle test USDC, 0 LFJ faucet USDC và 0 WAVAX. Vai trò ba ví khớp các keys trong env.

Quoter LFJ tìm được route V1 trực tiếp cho Circle test USDC sang WAVAX. Pool là `0x8436b8c75ed2f015a80b8472526dd1a79bf54e38`. Địa chỉ input là `0x5425890298aed601595a70AB815c96711a31Bc65`. Địa chỉ output là `0xd00ae08403B9bbb9124bB305C09058E32C39A48c`. Router và quoter dùng registry LFJ V2.2 đã tích hợp.

Ở block 61339086, pool có 281371 base units Circle USDC, tương đương 0,281371 USDC, và khoảng 3,707316323652594812 WAVAX. Quy mô pool nhỏ. Amount của demo và giao dịch setup stress phải chọn từ quote/reserves hiện tại. Goal 200 USDC mặc định không phù hợp với pool này.

Một quote đã đọc cho 100000 base units input trả 969949005482347653 WAVAX base units. Đây là snapshot dùng cho nghiên cứu route. Builder phải quote lại ở block thực thi.

## Oracle và freshness cần chốt

Lượt đọc gần nhất nhận AVAX/USD = 700658630 USD-e8 với tuổi khoảng 234 giây và USDC/USD = 99984374 USD-e8 với tuổi khoảng 59347 giây. Feed heartbeat được reader cấu hình lần lượt 600 và 86400 giây. Cả hai trong heartbeat tại lúc quan sát.

Policy hiện tại có price freshness 60 giây ở portfolio. ProofPolicy và Solidity giới hạn maxOracleAge tối đa 3600 giây. USDC round đang khoảng 16,5 giờ sẽ bị từ chối bởi các giới hạn này. Chỉ gắn thêm API key hoặc đổi token address sẽ chưa giải quyết freshness.

Đề xuất cần owner xác nhận là dùng Chainlink reference prices cho Circle USDC và WAVAX testnet với giới hạn tuổi riêng cho từng feed. Quyết định này thay đổi giả định freshness của proof hiện tại. Thiết kế triển khai phải giữ original updatedAt, roundId, answeredInRound, pinned block/hash, feed identity và hash cấu hình freshness trong oracle evidence. Revalidation đọc lại các round và từ chối khi vượt giới hạn đã được owner chấp nhận. Không thay updatedAt bằng thời gian đọc.

Một phương án khác là cung cấp nguồn oracle có timestamp mới phù hợp giới hạn 60 giây hiện tại, cùng identity, cơ chế xác minh và credential cần thiết của nguồn đó.

## Các bước triển khai sau khi chốt

1. Thêm Circle-USDC route vào LFJ client, kiểm manifest/token/pool và giữ hỗ trợ route LFJ faucet hiện có.
2. Nối verified Chainlink evidence vào oracle provider, portfolio, proof và owner policy theo freshness đã chốt.
3. Kiểm fork của route Circle, baseline, stress, Phi preflight và chi phí cho lượng demo phù hợp reserves.
4. Cấp gas cho relayer từ owner và fund test tokens vào vault. Owner có thể lấy Circle test USDC từ faucet, hoặc dùng một phần test AVAX mua token qua route testnet sau khi kiểm quote.
5. Deploy vault/adapter V2 cho đúng route bằng owner, tạo session và lưu manifest/transaction hashes.
6. Chạy Groq → alignment → build → simulation → risk → proof → attestor → relayer → receipt trên public Fuji. Dashboard đọc actual balances, round data và chain counters.

Đề nghị chọn funding bằng Circle faucet vào ví owner để có đủ số dư kiểm cả baseline và stress. Nếu chọn swap test AVAX của owner để bootstrap thì cần chốt trần chi tiêu. Số dư relayer có thể cấp riêng từ owner trong cùng trần.

Nguồn tham khảo gồm [Circle test USDC trên Fuji](https://academy.avax.network/academy/avalanche-l1/native-token-bridge/01-erc20-to-native/02-create-l1), [LFJ registry](https://developers.lfj.gg/deployment-addresses/fuji) và [cấu trúc tích hợp hiện tại](FUJI_LFJ_V2_1.md).
