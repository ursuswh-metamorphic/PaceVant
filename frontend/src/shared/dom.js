export const byId = (id) => document.getElementById(id);
const warn = new Set(["REPLAN_REQUIRED", "ESCALATED", "EXPIRED", "UNCERTAIN", "SUBMITTING", "SUBMITTED", "PROOF_INCONCLUSIVE"]);
const stop = new Set(["REJECTED", "REVERTED", "MISALIGNED", "RECEIPT_MISMATCH", "FAILED_TO_SUBMIT", "PROOF_REJECTED"]);
export const tone = (stage) => stop.has(stage) ? "stop" : warn.has(stage) ? "warn" : "";

export function showError(error) {
  byId("error").textContent = error.message;
  byId("error").hidden = false;
}
