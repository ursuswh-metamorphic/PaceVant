"use strict";

const byId = (id) => document.getElementById(id);
const warn = new Set(["REPLAN_REQUIRED", "ESCALATED", "EXPIRED", "UNCERTAIN", "SUBMITTING", "SUBMITTED"]);
const stop = new Set(["REJECTED", "REVERTED", "MISALIGNED", "RECEIPT_MISMATCH", "FAILED_TO_SUBMIT"]);
const tone = (stage) => stop.has(stage) ? "stop" : warn.has(stage) ? "warn" : "";
const integerFormat = new Intl.NumberFormat("en-US");
let mandateId;
let defaultPortfolio;

function units(value, places) {
  if (value == null) return "—";
  const amount = BigInt(value);
  const scale = 10n ** BigInt(places);
  const magnitude = amount < 0n ? -amount : amount;
  const whole = integerFormat.format(magnitude / scale);
  const fraction = (magnitude % scale).toString().padStart(places, "0").replace(/0+$/, "");
  return (amount < 0n ? "−" : "") + whole + (fraction ? "." + fraction : "");
}

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.code ?? "REQUEST_FAILED");
  return data;
}

function showError(error) {
  byId("error").textContent = error.message;
  byId("error").hidden = false;
}

function showPortfolio(portfolio, mandate, stage = "Danh mục mẫu") {
  if (!portfolio) return;
  const usdc = BigInt(portfolio.usdc_base_units) * BigInt(portfolio.price_usdc_usd_e8) * 10n ** 12n;
  const wavax = BigInt(portfolio.wavax_base_units) * BigInt(portfolio.price_wavax_usd_e8);
  const total = usdc + wavax;
  document.querySelector(".metric:nth-child(2) > span").textContent = stage;
  byId("portfolio-value").textContent = "$" + units(total / 10n ** 24n, 2);
  byId("portfolio-balances").textContent =
    units(portfolio.usdc_base_units, 6) + " USDC / " + units(portfolio.wavax_base_units, 18) + " WAVAX";
  byId("current-exposure").textContent = total ? units(wavax * 10000n / total, 2) + "% theo snapshot" : "—";
  byId("exposure-limit").textContent = units(mandate.max_avax_exposure_bps, 2) + "%";
}

async function loadTreasury() {
  const data = await api("/v1/treasury");
  const mandate = data.mandate;
  defaultPortfolio = data.portfolio;
  mandateId = mandate.mandate_id;
  byId("mandate").textContent = "Phiên bản " + mandate.version;
  byId("policy-status").textContent = data.issues[0] ?? mandate.status;
  byId("day-limit").textContent = units(mandate.max_usdc_spend_per_day_base_units, 6) + " / ngày";
  byId("trade-limit").textContent = units(mandate.max_usdc_per_swap_base_units, 6) + " / swap";
  showPortfolio(data.portfolio, mandate);
  byId("run").disabled = false;
  return mandate;
}

function detailRows(event) {
  if (event.proposal) return {
    "Intent": event.proposal.intent_id, "Swap": "USDC → WAVAX",
    "Lượng USDC": units(event.proposal.amount_in_base_units, 6),
    "Recipient": event.proposal.recipient,
    "Slippage tối đa": units(event.proposal.slippage_bps, 2) + "%",
  };
  if (event.alignment) return {
    "Verdict": event.alignment.verdict,
    "Reason codes": event.alignment.reason_codes.join(", "),
    "Hash market feed": event.alignment.evidence_refs.join(", "),
  };
  if (event.build) return {
    "Build ID": event.build.build_id, "Calldata hash": event.build.calldata_hash,
    "Min WAVAX": units(event.build.min_amount_out_base_units, 18), "Nonce": event.build.nonce,
  };
  if (event.simulation) return {
    "Nguồn": event.simulation.source, "Provenance": event.provenance,
    "Baseline": event.simulation.baseline.execution_status,
    "Stress nhẹ": event.simulation.stress_tests.find((s) => s.scenario_id === "reserve_shift_mild")?.status,
    "Stress bất lợi": event.simulation.stress_tests.find((s) => s.scenario_id === "reserve_shift_adverse")?.status,
    "Evidence root": event.simulation.evidence_root,
  };
  if (event.risk) return {
    "Kết quả risk": event.risk.result,
    "Tỷ trọng WAVAX dự phóng": event.risk.projected_wavax_exposure_bps == null
      ? "—" : units(event.risk.projected_wavax_exposure_bps, 2) + "%",
    "Trần WAVAX": units(event.risk.max_wavax_exposure_bps, 2) + "%",
    "Vi phạm": event.risk.violations.join(", "),
    "Snapshot": event.risk.snapshot_id,
  };
  if (event.decision) return {
    "Verdict": event.decision.verdict, "Reason codes": event.decision.reason_codes.join(", "),
    "USDC đề xuất lại": event.suggested_amount_base_units
      ? units(event.suggested_amount_base_units, 6) : null,
    "Decision ID": event.decision.decision_id,
  };
  if (event.typed_data_hash) return {
    "PDR": "Đã ký bằng khóa mock", "Typed data hash": event.typed_data_hash,
    "Nonce": event.nonce, "Hết hạn": new Date(event.expires_at * 1000).toISOString(),
  };
  if (event.receipt) return {
    "Receipt": event.receipt.status, "Tx hash mô phỏng": event.receipt.tx_hash,
    "USDC": units(event.receipt.actual_token_in_delta_base_units, 6),
    "WAVAX": "+" + units(event.receipt.actual_token_out_delta_base_units, 18),
    "Gas": event.receipt.gas_used, "Revert reason": event.receipt.revert_reason,
    "USDC sau swap": event.post_execution_balances
      ? units(event.post_execution_balances.usdc_base_units, 6) : null,
    "WAVAX sau swap": event.post_execution_balances
      ? units(event.post_execution_balances.wavax_base_units, 18) : null,
  };
  return {"Tx hash mô phỏng": event.tx_hash, "Reason codes": event.reason_codes?.join(", ")};
}

function renderDetail(event, button) {
  for (const candidate of byId("timeline").querySelectorAll("button")) {
    candidate.setAttribute("aria-pressed", String(candidate === button));
  }
  const heading = document.createElement("h3");
  heading.textContent = event.stage;
  const rows = document.createElement("dl");
  for (const [name, value] of Object.entries(detailRows(event))) {
    if (value == null || value === "") continue;
    const key = document.createElement("dt");
    const content = document.createElement("dd");
    key.textContent = name;
    content.textContent = value;
    rows.append(key, content);
  }
  const raw = document.createElement("details");
  const label = document.createElement("summary");
  label.textContent = "Xem bản ghi JSON";
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(event, null, 2);
  raw.append(label, pre);
  byId("details").replaceChildren(heading, rows, raw);
}

function renderAttempt(groups, index) {
  for (const [i, button] of Array.from(byId("attempts").children).entries()) {
    button.setAttribute("aria-pressed", String(i === index));
  }
  const list = byId("timeline");
  list.replaceChildren();
  const events = groups[index];
  const entries = events.map((event) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const dot = document.createElement("span");
    dot.className = "dot " + tone(event.stage);
    button.append(dot, document.createTextNode(event.stage));
    button.addEventListener("click", () => renderDetail(event, button));
    item.append(button);
    list.append(item);
    return button;
  });
  if (events.length) renderDetail(events.at(-1), entries.at(-1));
}

function display(workflow, mandate) {
  byId("workflow-id").textContent = workflow.workflow_id;
  byId("workflow-status").textContent = workflow.status;
  byId("workflow-status").className = "status " + tone(workflow.status);
  const groups = [];
  for (const event of workflow.timeline) {
    if (event.stage === "PROPOSED" || groups.length === 0) groups.push([]);
    groups.at(-1).push(event);
  }
  if (!groups.length) return;
  byId("attempts").replaceChildren();
  groups.forEach((attempt, index) => {
    const button = document.createElement("button");
    const amount = attempt[0].proposal?.amount_in_base_units;
    button.textContent = "Lần " + (index + 1) + (amount ? " · " + units(amount, 6) + " USDC" : "");
    button.addEventListener("click", () => renderAttempt(groups, index));
    byId("attempts").append(button);
  });
  const lastEvaluation = workflow.timeline.findLast((event) => event.portfolio);
  if (lastEvaluation) showPortfolio(lastEvaluation.portfolio, mandate, "Snapshot kiểm tra");
  else showPortfolio(defaultPortfolio, mandate);
  byId("empty").hidden = true;
  byId("workflow-body").hidden = false;
  renderAttempt(groups, groups.length - 1);
}

let activeMandate;
loadTreasury().then((mandate) => { activeMandate = mandate; }).catch(showError);

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
    const result = await api("/v1/workflows/start", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({mandate_id: mandateId, goal: "Buy WAVAX with 500 USDC", scenario}),
    });
    display(await api("/v1/workflows/" + result.workflow_id), activeMandate);
  } catch (error) {
    showError(error);
    byId("empty-message").textContent = "Chưa tải được kết quả. Có thể chạy lại kịch bản mock.";
    byId("workflow-status").textContent = "Lỗi";
    byId("workflow-status").className = "status stop";
  } finally {
    byId("run").disabled = false;
  }
});
