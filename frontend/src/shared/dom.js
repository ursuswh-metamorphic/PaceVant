export const byId = (id) => document.getElementById(id);
const warn = new Set(["REPLAN_REQUIRED", "ESCALATED", "EXPIRED", "UNCERTAIN", "SUBMITTING", "SUBMITTED", "PROOF_INCONCLUSIVE"]);
const stop = new Set(["REJECTED", "REVERTED", "MISALIGNED", "RECEIPT_MISMATCH", "FAILED_TO_SUBMIT", "PROOF_REJECTED"]);
export const tone = (stage) => stop.has(stage) ? "stop" : warn.has(stage) ? "warn" : "";

export function showError(error) {
  const messages = {
    ORACLE_WINDOW_UNAVAILABLE:"Chưa có round Chainlink còn đủ thời gian cho toàn bộ pipeline. Đợi round mới rồi thử một yêu cầu mới nếu yêu cầu cũ đã kết thúc.",
    STALE_REQUIRES_REEVALUATION:"State hoặc thời hạn đã thay đổi. Hệ thống dừng để bảo vệ tài sản; kiểm tra yêu cầu đã gửi trước khi thử lại.",
    TOKEN_EXPOSURE_LIMIT:"Vault không còn đủ USDC để giữ trần WAVAX. Cần operator bổ sung vốn đúng token; hệ thống không tự nới policy.",
    DEMO_REQUEST_REVIEW_REQUIRED:"Yêu cầu cần kiểm tra trạng thái. Dùng nút kiểm tra yêu cầu đã gửi; không gửi thêm swap để chữa timeout.",
    GAS_CREDIT_INSUFFICIENT:"Hết gas credit khả dụng hoặc ngân sách đang giữ cho giao dịch chưa rõ. Kiểm tra history; chọn account lại không nạp thêm credit.",
    TRADE_SIZE_LIMIT:"Số tiền vượt hạn mức swap hoặc số dư có thể sử dụng.",
    DEMO_ACCESS_REQUIRED:"Phiên demo đã hết hạn hoặc không hợp lệ. Tải lại trang và chọn Demo User; credit và giao dịch cũ vẫn được giữ.",
    EXECUTION_PLANE_UNAVAILABLE:"RPC/execution hiện chưa trả đủ dữ liệu. Không có kết quả thành công giả; kiểm tra workflow và receipt trước khi thử lại.",
  };
  byId("error").textContent = messages[error.message] ? messages[error.message] + " [" + error.message + "]" : error.message;
  byId("error").hidden = false;
}
