import {api} from "./api/client.js";
import {byId,showError} from "./shared/dom.js";
import {state} from "./shared/state.js";
import {loadTreasury} from "./features/treasury/index.js";
import {display} from "./features/workflows/index.js";
import {workflowRequest} from "./features/intents/index.js";
import {refreshDemo, pendingRequest, newRequest, completed, forgetUnacceptedRequest} from "./features/demo/index.js";

const workflowPath = (id) => (state.demoMode ? "/v1/demo/workflows/" : "/v1/workflows/") + id;
async function openDemoWorkflow(id) {
  try { const workflow = await api(workflowPath(id)); display(workflow, state.activeMandate); }
  catch (error) { showError(error); }
}
const updateDemo = () => refreshDemo(openDemoWorkflow);

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
  state.demoToken = byId("demo-access-code").value;
  byId("demo-access-code").value = "";
  state.demoMode = true;
  try {
    await api("/v1/demo/account");
    await connectTreasury();
    await updateDemo();
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
  byId("run").disabled = true;
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
    const result = await api(state.demoMode ? "/v1/demo/workflows" : "/v1/workflows/start", {
      method: "POST", headers: {"Content-Type": "application/json", ...(state.demoMode ? {"Idempotency-Key":newRequest()} : {})},
      body: JSON.stringify(payload),
    });
    const path = workflowPath(result.workflow_id);
    let workflow = await api(path);
    display(workflow, state.activeMandate);
    for (let poll = 0; poll < 30 && ["SUBMITTED", "SUBMITTING"].includes(workflow.status); poll++) {
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
    byId("run").disabled = state.demoMode && !!pendingRequest();
  }
});
