import {api} from "./api/client.js";
import {byId,showError} from "./shared/dom.js";
import {state} from "./shared/state.js";
import {loadTreasury} from "./features/treasury/index.js";
import {display} from "./features/workflows/index.js";
import {workflowRequest} from "./features/intents/index.js";
import {refreshDemo, pendingRequest, newRequest, completed, forgetUnacceptedRequest} from "./features/demo/index.js";
import {runCheck} from "./features/demo/checks.js";

const workflowPath = (id) => (state.demoMode ? "/v1/demo/workflows/" : "/v1/workflows/") + id;
async function openDemoWorkflow(id) {
  try { const workflow = await api(workflowPath(id)); display(workflow, state.activeMandate); }
  catch (error) { showError(error); }
}
const updateDemo = () => refreshDemo(openDemoWorkflow);
function busyControls(busy) {
  for (const id of ["demo-activity", "live-case", "shield-challenge", "live-goal"]) byId(id).disabled = busy;
  byId("run").disabled = busy;
}
function updateCase() {
  const swap = byId("live-case").value === "swap";
  const help = {
    swap:"Thực hiện swap 0.000001 USDC qua đủ security pipeline. Token dùng từ vault, relayer trả gas thật và ghi nợ gas credit. Có thể mất vài phút; nếu policy không thỏa thì từ chối.",
    limit:"Thử yêu cầu lớn hơn hạn mức hiện tại. Kỳ vọng TRADE_SIZE_LIMIT trước khi tạo workflow hoặc gửi giao dịch; không tốn gas.",
    session:"Đọc policy/session và credit thực tế. Không sửa thời gian, không gia hạn hoặc nạp tiền tự động. Oracle, exposure và các gate khác vẫn cần kiểm khi swap.",
    contract:"Kiểm replay, calldata bị sửa và chữ ký sai bằng eth_call trên Fuji, dựa vào swap Demo User đã xác nhận. Đây là kiểm tại block lịch sử, không gửi 3 transaction lỗi.",
    injection:"Đưa challenge TOOL-role có nhãn test vào Task Shield dùng AI thật. Hiển thị kết quả thực, kể cả không chặn được hoặc provider lỗi. Không trộn challenge vào swap thật.",
    auth:"Gửi credential Demo User tới API quản trị và execution. Kỳ vọng từ chối truy cập; không đổi policy, không ký hoặc gửi giao dịch.",
  };
  byId("live-goal").readOnly = !swap;
  byId("live-goal-label").hidden = !swap;
  byId("challenge-label").hidden = byId("live-case").value !== "injection";
  byId("run").disabled = swap && (!!pendingRequest() || BigInt(state.demoAvailableWei ?? "0") <= 0n);
  byId("run").textContent = swap ? "Thực hiện swap nhỏ trên Fuji" : "Chạy kiểm tra · không gửi giao dịch";
  byId("live-case-help").textContent = help[byId("live-case").value];
  byId("live-check-panel").hidden = true;
}
byId("live-case").addEventListener("change", updateCase);
byId("demo-activity").addEventListener("change", () => {
  const normal = byId("demo-activity").value === "normal";
  for (const option of byId("live-case").options) option.hidden = normal ? !["swap", "session"].includes(option.value) : option.value === "swap";
  byId("live-case").value = normal ? "swap" : "injection";
  updateCase();
});

async function connectTreasury() {
  state.activeMandate = await loadTreasury();
  byId("connect-form").hidden = true;
  byId("operator-login").hidden = true;
  byId("demo-select-form").hidden = true;
  const workflowId = new URLSearchParams(window.location.search).get("workflow");
  if (workflowId && /^[a-zA-Z0-9_-]{1,100}$/.test(workflowId)) {
    const workflow = await api(workflowPath(workflowId));
    display(workflow, state.activeMandate);
  }
}
api("/healthz").then((health) => {
  state.deploymentMode = health.mode;
  document.querySelector(".environment").textContent = health.mode;
  document.querySelector(".notice").textContent = health.mode === "MOCK"
    ? "MOCK: fixture V1, không chạy proof V2.1 hoặc giao dịch on-chain"
    : health.mode === "FUJI" ? "Avalanche Fuji · Chainlink thật · mô phỏng trên fork · chưa audit"
    : "Local · controlled oracle · chưa audit";
  if (health.mode === "MOCK") return connectTreasury();
  byId("connect-form").hidden = false;
  byId("operator-login").hidden = false;
  byId("scenarios").hidden = true;
  byId("live-goal-label").hidden = false;
  if (health.mode === "FUJI") byId("live-goal").value = "Buy WAVAX with 0.000001 USDC";
}).catch(showError);
api("/v1/demo/config").then(config => {
  byId("demo-select-form").hidden = !config.enabled;
}).catch(() => {});
byId("demo-select-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const session = await api("/v1/demo/select", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({account_id:byId("demo-account-select").value}),
    });
    state.demoToken = session.access_token;
    state.demoMode = true;
    state.operatorToken = "";
    await api("/v1/demo/account");
    await connectTreasury();
    await updateDemo();
    byId("live-case-label").hidden = false;
    byId("live-case-help").hidden = false;
    byId("demo-activity-label").hidden = false;
    byId("demo-supported").hidden = false;
    byId("demo-activity").dispatchEvent(new Event("change"));
    if (pendingRequest()) byId("demo-request-state").textContent = "Có yêu cầu trước đó. Chỉ kiểm tra lại, không gửi swap mới.";
  } catch (error) { state.demoToken = ""; state.demoMode = false; showError(error); }
});
byId("demo-refresh").addEventListener("click", () => updateDemo().catch(showError));
byId("demo-resume").addEventListener("click", async () => {
  const key = pendingRequest(); if (!key) return;
  try { const wf = await api("/v1/demo/requests/" + key); display(wf, state.activeMandate); completed(wf); await updateDemo(); }
  catch (error) {
    if (error.message === "DEMO_REQUEST_NOT_FOUND") forgetUnacceptedRequest();
    showError(error);
  }
});
byId("connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.operatorToken = byId("operator-token").value;
  state.demoMode = false;
  state.demoToken = "";
  byId("operator-token").value = "";
  try { await connectTreasury(); } catch (error) { state.operatorToken = ""; showError(error); }
});

byId("run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const scenario = new FormData(event.target).get("scenario");
  if (state.demoMode && byId("live-case").value !== "swap") {
    busyControls(true);
    byId("error").hidden = true;
    try { await runCheck(byId("live-case").value); }
    catch (error) { byId("live-check-summary").textContent = error.message; byId("live-check-result").textContent = "Chưa có kết quả đã xác minh."; showError(error); }
    finally { busyControls(false); }
    return;
  }
  busyControls(true);
  byId("error").hidden = true;
  byId("workflow-body").hidden = true;
  byId("empty").hidden = false;
  byId("empty-message").textContent = "Đang kiểm tra đề xuất...";
  byId("workflow-status").textContent = "Đang chạy";
  byId("workflow-status").className = "status idle";
  byId("workflow-id").textContent = "";
  try {
    const goal = state.deploymentMode === "MOCK" ? "Buy WAVAX with 500 USDC" : byId("live-goal").value;
    if (state.demoMode && pendingRequest()) throw new Error("DEMO_REQUEST_IN_PROGRESS_USE_CHECK_BUTTON");
    const payload = state.demoMode ? {goal} : await workflowRequest(state.activeMandate,
      state.deploymentMode === "MOCK" ? "Buy WAVAX with 500 USDC" : byId("live-goal").value,
      state.deploymentMode === "MOCK" ? scenario : null);
    const requestKey = state.demoMode ? newRequest() : null;
    let observing = false, watching = true;
    const watch = state.demoMode ? setInterval(async () => {
      if (observing) return;
      observing = true;
      try {
        const live = await api("/v1/demo/requests/" + requestKey);
        if (watching) display(live, state.activeMandate);
      } catch { /* A just-accepted request may not have a workflow yet. Retain its ID. */ }
      finally { observing = false; }
    }, 4000) : null;
    let result;
    try { result = await api(state.demoMode ? "/v1/demo/workflows" : "/v1/workflows/start", {
      method: "POST", headers: {"Content-Type": "application/json", ...(state.demoMode ? {"Idempotency-Key":requestKey} : {})},
      body: JSON.stringify(payload),
    }); } finally { watching = false; if (watch) clearInterval(watch); }
    const path = workflowPath(result.workflow_id);
    let workflow = await api(path);
    display(workflow, state.activeMandate);
    for (let poll = 0; poll < 30 && ["SUBMITTED", "SUBMITTING", "RECEIPT_MISMATCH"].includes(workflow.status); poll++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      workflow = await api(path);
      display(workflow, state.activeMandate);
    }
    if (state.demoMode) { completed(workflow); await updateDemo(); }
  } catch (error) {
    showError(error);
    byId("empty-message").textContent = "Chưa tải được kết quả. Kiểm tra kết nối API và tải lại workflow.";
    byId("workflow-status").textContent = "Lỗi";
    byId("workflow-status").className = "status stop";
  } finally {
    busyControls(false);
    byId("run").disabled = state.demoMode && !!pendingRequest();
  }
});
