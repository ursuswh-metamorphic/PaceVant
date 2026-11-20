import {api} from "../../api/client.js";
import {byId} from "../../shared/dom.js";
import {state} from "../../shared/state.js";
import {units} from "../../shared/format.js";

export async function runCheck(kind) {
  const result = byId("live-check-result");
  byId("live-check-panel").hidden = false;
  byId("live-check-summary").textContent = "Đang kiểm tra thực tế, không gửi giao dịch…";
  result.textContent = "Đang lấy kết quả thực tế; không broadcast giao dịch…";
  let report;
  if (kind === "limit") {
    const goal = "Buy WAVAX with " + units(BigInt(state.activeMandate.max_usdc_per_swap_base_units) + 1n, 6) + " USDC";
    try {
      await api("/v1/demo/workflows", {method:"POST", headers:{"Content-Type":"application/json", "Idempotency-Key":crypto.randomUUID()}, body:JSON.stringify({goal})});
      throw new Error("EXPECTED_LIMIT_REJECTION_NOT_OBSERVED");
    } catch (error) {
      if (error.message !== "TRADE_SIZE_LIMIT") throw error;
      report = {source:"ACTUAL_API_VALIDATION", goal, observed_error:error.message, all_passed:true, broadcast:false};
    }
  } else if (kind === "session") {
    report = await api("/v1/demo/readiness");
  } else if (kind === "injection") {
    report = await api("/v1/demo/shield-check", {method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({challenge:byId("shield-challenge").value})});
  } else if (kind === "auth") {
    const checks = [];
    for (const path of ["/v1/treasury", "/execution/v1/chain/context"]) {
      try {
        await api(path, {headers:{Authorization:"Bearer " + state.demoToken}});
        checks.push({path, status:"FAIL", detail:"Unexpected access"});
      } catch (error) {
        checks.push({path, status:["AUTH_REQUIRED", "UNAUTHORIZED"].includes(error.message) ? "PASS" : "INCONCLUSIVE", observed_error:error.message});
      }
    }
    report = {source:"ACTUAL_API_AUTH_CHECK", broadcast:false, checks, all_passed:checks.every(c => c.status === "PASS")};
  } else {
    if (!state.demoConfirmedWorkflow) throw new Error("Cần một swap Demo User đã xác nhận để kiểm contract. Chưa có dữ liệu thì không dựng kết quả giả.");
    report = await api("/v1/demo/workflows/" + state.demoConfirmedWorkflow + "/security-checks");
  }
  result.textContent = JSON.stringify(report, null, 2);
  byId("live-check-summary").textContent = kind === "limit" ? "Đã từ chối yêu cầu vượt hạn mức: TRADE_SIZE_LIMIT. Không tạo giao dịch, không trừ gas."
    : kind === "session" ? "Đọc trực tiếp block " + report.block_number + ": " + (report.reason_codes.length ? report.reason_codes.join(", ") : "Policy/session và gas credit chưa có lỗi trong phạm vi kiểm tra. Vẫn phải kiểm toàn bộ gate khi swap.")
    : kind === "injection" ? "AI " + report.report.model + " trả " + report.report.status + ". " + (report.all_passed ? "Đã phát hiện lệnh đổi recipient từ tool. " : "Chưa xác nhận chặn được challenge này. ") + "Không gửi swap."
    : kind === "auth" ? "Kiểm quyền Demo User: " + report.checks.map(c => c.path + " → " + c.status).join(" · ") + ". Không gửi giao dịch."
    : report.checks.map(c => c.expected_error + ": " + c.status).join(" · ") + ". eth_call trên Fuji, không trừ gas.";
}
