# Merge main vào develop — 21/11/2026

Nguồn main: `176f63fa913744577383f4d152d32e6308a02624`; develop trước merge: `8444ccd5e401660346c17c4d8ccf2c19d4037022`.

Đã lấy Hybrid Task Shield, structured constraints/source binding, ITAG evidence catalog/citation validation, local ERC-20 transfer, nonce journal và benchmark/evaluation tooling của main. Giữ React entrypoint, ba tab judge, economic/system gas guards và native VPS deployment của develop. Local transfer không được public judge API expose.

Adapter nội bộ mới nối exact OperationIntent của TreasuryWorkflows vào Hybrid Shield; kiểm operation/token/amount/recipient/chain/deadline/minOut/slippage/sender. Candidate/model không cấp quyền. Giữ semantic uncertainty fail-closed. Fixture LOCAL được cập nhật schema mới, không bật trong production.

Transfer V2 bổ sung vào base PolicyVault ban đầu làm MVP vượt EIP-170. Đã disable ba V2 transfer entrypoint trong V3/MVP bằng override, giữ chúng ở V2 LOCAL. Runtime bytes: PolicyVault 19453, V3 21237, MVP 21777, dưới 24576. Không nới code-size limit. Benchmark AI đóng băng được kiểm hash theo đúng source main đã đo, không gán số đo cũ cho adapter mới.

Kiểm tra liên quan: 59 workflow/hybrid tests pass; 45 final integration/security/API tests pass, 1 skip; MVP Foundry suite pass bao gồm test entrypoint bypass/code size; React build + 10 tests pass; Ruff và secrets scan pass. Lượt rộng hơn ban đầu có 430 pass nhưng lỗi merge contract size/frozen-source assertion; các lỗi được sửa và kiểm lại bằng nhóm tập trung. Không chạy lại paid model benchmark, không public transaction, không deploy VPS trong task merge/dataset này.
