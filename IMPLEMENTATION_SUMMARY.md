# PaceVant — frontend, judge demo và native deployment

Ngày 21/11/2026, Asia/Saigon. Source được triển khai trong repository; không có public contract migration/asset transfer mới trong task này.

## Đã triển khai

* **React 19 + TypeScript + Vite**, Tailwind v4, locally owned shadcn-style components dùng Radix primitives, Motion for React, Lucide và TanStack Query. Dependencies pin trong frontend package/lockfile. Build static vào `frontend/dist`, không Node production server.
* Ba tab Live Demo, Security & Policies, History: server-approved cards, real event pipeline, proposal, measured result, hash copy, expandable solver/Phi details và history drawer. Responsive, keyboard/focus/reduced motion; không fake KPI/chart/chain-of-thought.
* Anonymous judge API tách khỏi authenticated operator API: fixed presets, visitor cookie, job/key/history recovery, hash-pinned recorded evidence. Không expose Owner/admin/raw execution, không nhận public wallet signer keys.
* Một worker process group/heavy fork cùng lúc, durable SQLite quota/idempotency, visitor/IP/global limits, timeout/tree cleanup, interrupted-job recovery không resend, model-only environment, body/Origin checks và Strict/HttpOnly cookie.
* Shared `operations/fork_treasury.py` cho CLI verifier/judge worker. Setup chỉ trên loopback Anvil; business workflow vẫn là TreasuryWorkflows/MvpExecution: model, Shield/ITAG, trusted builder, Chainlink, EVM, risk/Z3, SDE, EIP-712/Phi, exact preflight, relay và actual receipt. Callback báo stage đang chạy; persisted events là evidence gate đã chạy, không timer giả.
* Native Ubuntu scripts/systemd/Nginx: dedicated non-root user, loopback backend, persistent data, memory/CPU/process bounds, log/journal, TLS instructions, health/restart/release rollback giữ DB. Không Docker.

## API mappings

| UI | Backend |
|---|---|
| Scenarios/quota/config | `GET /judge/config` |
| Source balances/policy/oracle | `GET /judge/source`, fresh cached read hoặc explicitly recorded snapshot |
| Run/Resume | `POST /judge/jobs` body chỉ `{scenario}`, stable Idempotency-Key; GET by key trước retry |
| Pipeline/results | `GET /judge/jobs/{id}`, actual callbacks/persisted workflow evidence |
| History | `GET /judge/history`, visitor-scoped job reads |
| Recorded fallback | `GET /judge/replays/{scenario}`, SHA-256 manifest check, không thực thi mới |

Pending/unknown/failed/missing proof không là passed. Public explorer chỉ cho REAL_FUJI_EXECUTION + verified public receipt; judge worker hiện chỉ có isolated fork capability.

## Kiểm chứng và giới hạn

Frontend build/client/browser checks ghi trong `docs/audit/judge-frontend-check.json`. Controller security tests kiểm exact schema, no admin/live-spend surfaces, Origin/body limits, visitor isolation, atomic concurrency, quotas, interrupted jobs và timeout cleanup. Full regression/Foundry/vectors kiểm core cũ; kết quả cuối nằm trong báo cáo test.

Judge API mới đã có real-provider payment CONFIRMED trên Fuji fork, bao gồm browser mất phản hồi POST rồi reload vẫn chỉ một job. Guard mới REJECTED tại builder với `LFJ_UNSUPPORTED_ROUTE`; replay của cả ba scenario đã được export từ evidence thật. Lần swap API mới đã qua PROOF VERIFIED và exact signed preflight nhưng dừng trước RELAY, trạng thái UNKNOWN / `SIGNED_REQUIRES_RECOVERY`, chưa có receipt; chưa xác định được exception gốc của lần chạy đó. Các lần chẩn đoán tiếp gặp `FRESH_CHAINLINK_SIGNING_WINDOW_UNAVAILABLE`. Không nới oracle window, tự resend hay gọi UNKNOWN là success. Đã thêm exception class an toàn vào recovery evidence cho lần phát sinh sau. Recorded swap thành công từ checkpoint full fork trước vẫn có thật, không phải acceptance live API mới. Chi tiết ở `docs/audit/judge-api-acceptance.json`.

Kiểm tra: full Python regression **608 passed / 10 skipped** tại checkpoint; focused cuối **14 passed**; frontend **10 passed**, TypeScript/Vite build và Chromium checks passed; Foundry **109 passed**, vectors V1/V2/MVP passed. Các focused counts có overlap, không cộng dồn. Bundle chính khoảng 169 KB gzip, Vite có cảnh báo chunk trên 500 KB minified; build không lỗi. Linux/Nginx và giới hạn nghiệm thu được ghi trong `docs/audit/judge-deployment-report.json`.

Linux QA dùng **Ubuntu 24.04 WSL**: Python 3.12/uv lock, non-root systemd service, Nginx static/proxy/admin block. Chưa SSH Ubuntu 22.04 VPS, chưa HTTPS domain thật, multi-day soak/reboot/tài nguyên VPS chưa nghiệm thu. Không cam kết mọi transaction luôn success khi dependency hoặc policy không cho phép.

## Hướng dẫn

[Judge guide](JUDGE_DEMO_GUIDE.md), [Native VPS deployment](VPS_DEPLOYMENT.md), [current system review](docs/PACEVANT_CURRENT_SYSTEM_REVIEW.md). Production còn cần SSH access, domain/DNS và model-only private env do user cung cấp riêng. Public MVP contract activation là Owner migration/signature riêng, không được bypass bởi frontend/demo mode.
