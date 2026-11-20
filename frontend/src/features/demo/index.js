import {api} from "../../api/client.js";
import {byId} from "../../shared/dom.js";
import {state} from "../../shared/state.js";

export function avax(wei) {
  if (wei == null) return "Chưa xác minh";
  const value = BigInt(wei), sign = value < 0n ? "-" : "", n = value < 0n ? -value : value;
  return sign + (n / 10n ** 18n) + "." + (n % 10n ** 18n).toString().padStart(18, "0").replace(/0+$/, "").padEnd(1, "0") + " AVAX";
}

const pendingKey = "pacevant-demo-request"; // Safe request ID only; never a credential.
export const pendingRequest = () => sessionStorage.getItem(pendingKey);
export function forgetUnacceptedRequest() {
  sessionStorage.removeItem(pendingKey);
  byId("demo-resume").hidden = true;
  byId("run").disabled = false;
}
export function newRequest() {
  const key = crypto.randomUUID();
  sessionStorage.setItem(pendingKey, key);
  byId("demo-resume").hidden = false;
  return key;
}
export function completed(workflow) {
  const terminal = ["CONFIRMED", "REVERTED", "REJECTED", "ESCALATED", "FAILED_TO_SUBMIT", "EXPIRED", "REPLAN_REQUIRED"];
  if (terminal.includes(workflow.status)) {
    sessionStorage.removeItem(pendingKey);
    byId("demo-resume").hidden = true;
    byId("run").disabled = false;
  }
  byId("demo-request-state").textContent = "Yêu cầu: " + workflow.workflow_id + " · " + workflow.status;
}
export async function refreshDemo(onOpen) {
  const account = await api("/v1/demo/account");
  byId("demo-budget").hidden = false;
  byId("demo-wallet").textContent = "Ví Demo User: " + account.wallet_address + " · Fuji " + account.chain_id;
  byId("demo-wallet-balance").textContent = "AVAX thực trong ví: " + avax(account.wallet_avax_balance_wei) + " (không dùng làm gas credit)";
  byId("demo-credit").textContent = "Gas credit khả dụng: " + avax(account.available_wei) +
    " · Đang giữ chỗ: " + avax(account.reserved_wei) + " · Đã trừ: " + avax(account.spent_wei);
  const paid = account.transactions.find(tx => tx.state === "SETTLED");
  state.demoConfirmedWorkflow = account.transactions.find(tx => tx.state === "SETTLED" && tx.receipt_status === "SUCCESS")?.workflow_id;
  byId("demo-last-fee").textContent = paid ? "Phí gần nhất: " + avax(paid.actual_cost_wei) +
    " = " + paid.gas_used + " gas × " + paid.effective_gas_price_wei + " wei/gas · " + paid.receipt_status : "Chưa có phí giao dịch đã xác minh. Pending không tính là phí 0.";
  const transactions = byId("demo-transactions"); transactions.replaceChildren();
  for (const tx of account.transactions) {
    const item = document.createElement("li"), link = document.createElement("a"), button = document.createElement("button");
    link.textContent = tx.tx_hash; link.href = "https://testnet.snowtrace.io/tx/" + tx.tx_hash; link.target = "_blank"; link.rel = "noopener noreferrer";
    item.append(link, document.createTextNode(" · " + tx.state + " · " + (tx.receipt_status ?? "PENDING") + " · " + (tx.state === "SETTLED" ? avax(tx.actual_cost_wei) : "giữ chỗ " + avax(tx.max_cost_wei)) + " "));
    button.type = "button"; button.textContent = "Xem workflow"; button.addEventListener("click", () => onOpen(tx.workflow_id)); item.append(button); transactions.append(item);
  }
  if (!account.transactions.length) transactions.textContent = "Chưa có giao dịch demo được broadcast.";
  const requests = byId("demo-requests"); requests.replaceChildren();
  for (const request of account.requests) {
    const item = document.createElement("li"), button = document.createElement("button");
    item.append(document.createTextNode(request.workflow_id + " · " + request.state + " "));
    button.type = "button"; button.textContent = "Xem kết quả";
    button.addEventListener("click", () => onOpen(request.workflow_id)); item.append(button); requests.append(item);
  }
  const history = byId("demo-ledger"); history.replaceChildren();
  for (const entry of account.ledger) {
    const item = document.createElement("li");
    item.textContent = new Date(entry.at * 1000).toLocaleString("vi-VN") + " · " + entry.kind + " · " + avax(entry.delta_wei) +
      (entry.tx_hash ? " · " + entry.tx_hash : "") + (entry.body.reserved_wei ? " · giữ chỗ " + avax(entry.body.reserved_wei) : "");
    history.append(item);
  }
  // After reload the identifier is safe to retain; resumption is GET-only.
  byId("demo-resume").hidden = !pendingRequest();
  state.demoAvailableWei = account.available_wei;
  if (byId("live-case").value === "swap" && (pendingRequest() || BigInt(account.available_wei) <= 0n)) byId("run").disabled = true;
}
