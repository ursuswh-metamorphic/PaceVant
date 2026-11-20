# SMT artifacts — Demo User Fuji swap

> **DOC STATUS: CURRENT_EVIDENCE_REFERENCE** — exact query bytes cho workflow `workflow_00370cd7f0c3479aacf9c9faced7940f`, không phải live readiness claim.

Query filenames là Keccak content hashes từ [chain evidence](../web-demo-fuji-chain-evidence.json). Expected statuses theo thứ tự query_hashes: SAT, UNSAT, SAT, UNSAT, UNSAT. Kiểm feasibility và ba bounded obligations, không phải full Solidity verification.

```powershell
uv run --locked python tools/evaluation/verify_fuji_queries.py --report docs/audit/web-demo-fuji-chain-evidence.json --queries docs/audit/web-demo-live-proof
```

Lệnh không đọc env/wallet và không gọi mạng. Không sửa query cũ để khớp source mới; source commitment và assumptions thuộc lượt đã thực thi. Xem [review](../WEB_DEMO_LIVE_REVIEW.md) và [current design](../../AI_Treasury_Security_System_Design_v2.1.md).
