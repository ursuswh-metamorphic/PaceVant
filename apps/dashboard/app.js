"use strict";

const byId = (id) => document.getElementById(id);
const warn = new Set(["REPLAN_REQUIRED", "ESCALATED", "EXPIRED", "UNCERTAIN", "SUBMITTING", "SUBMITTED", "PROOF_INCONCLUSIVE"]);
const stop = new Set(["REJECTED", "REVERTED", "MISALIGNED", "RECEIPT_MISMATCH", "FAILED_TO_SUBMIT", "PROOF_REJECTED"]);
const tone = (stage) => stop.has(stage) ? "stop" : warn.has(stage) ? "warn" : "";
const integerFormat = new Intl.NumberFormat("en-US");
let mandateId;
let defaultPortfolio;
let deploymentMode = "MOCK";
let operatorToken = "";
let displayedInputDecimals = 6, displayedOutputDecimals = 18;
const isReverse = (p) => p?.token_in?.toLowerCase() === activeMandate?.token_out?.toLowerCase();
const symbol = (decimals) => decimals === 6 ? "USDC" : "WAVAX";

function showRiskBudget(s, balances) {
  byId("proof-budgets").textContent = s ? "Certified Risk Consumption: $" + units(s.used_usd_e8, 8) +
    " / $" + units(s.limit_usd_e8, 8) + " · Global UTC day: $" + units(s.global_used_usd_e8, 8) +
    " / $" + units(s.global_limit_usd_e8, 8) + " · USDC input spent: " + units(balances?.daily_spent_usdc_base_units, 6) +
    " USDC. Đây là rủi ro dự phòng, tách biệt với lỗ thực tế và gas." : "Session unavailable — NO SIGN";
}

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
  const response = await fetch(path, {...options, headers:{...options?.headers, ...(operatorToken ? {Authorization:"Bearer " + operatorToken} : {})}});
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
  deploymentMode = data.mode;
  byId("proof-summary").hidden = !mandate.proof_policy;
  if (mandate.proof_policy) {
    const p = mandate.proof_policy, s = data.proof_session;
    byId("proof-policy").textContent = p.authorization + " · Policy " + mandate.policy_hash +
      " · Loss policy: " + units(p.max_relative_loss_bps, 2) + "% + $" + units(p.fixed_loss_usd_e8, 8) +
      " · Oracle band: " + units(p.oracle_band_bps, 2) + "% · Tolerance: " + units(p.tolerance_bps, 2) + "%" +
      " · Session " + mandate.session_id + " · Reverse cap: " + (BigInt(p.max_wavax_per_swap) ? units(p.max_wavax_per_swap, 18) + " WAVAX" : "DISABLED");
    showRiskBudget(s, data.chain_balances);
  }
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
  if (event.proof) return {
    "Proof": event.proof.status, "Reason": event.proof.reason,
    "CHECK": event.proof.check_mode, "COMPILE": event.proof.compile_mode, "RISK BOUND": event.proof.risk_bound,
    "Certified risk debit (USD)": units(event.proof.risk_debit_usd_e8, 8),
    "Phi · signed lower bounds": event.proof.phi?.balance_bounds.map((b) => {
      const decimals = activeMandate?.registry?.assets.find((a) => a.address === b.asset)?.decimals;
      return b.asset + ": " + (decimals == null ? b.min_delta : units(b.min_delta, decimals) + " " + symbol(decimals));
    }).join("; "),
    "Residual allowance": event.proof.phi ? "0 for both tracked tokens" : null,
    "Solver / encoder": event.proof.solver_version + " / " + event.proof.encoder_version,
    "Fallback tau=0": String(event.proof.fallback_tau_zero),
    "Counterexample prices (usdE8)": event.proof.witness ? JSON.stringify(event.proof.witness) : null,
  };
  if (event.proposal) return {
    "Intent": event.proposal.intent_id, "Swap": isReverse(event.proposal) ? "WAVAX → USDC" : "USDC → WAVAX",
    "Amount in": units(event.proposal.amount_in_base_units, isReverse(event.proposal) ? 18 : 6),
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
    "Min output": units(event.build.min_amount_out_base_units, isReverse(event.build) ? 6 : 18), "Nonce": event.build.nonce,
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
    "PDR": "EIP-712 attestation", "Typed data hash": event.typed_data_hash,
    "Nonce": event.nonce, "Hết hạn": new Date(event.expires_at * 1000).toISOString(),
  };
  if (event.receipt) return {
    "Receipt": event.receipt.status, "Tx hash": event.receipt.tx_hash,
    [symbol(displayedInputDecimals) + " input"]: units(event.receipt.actual_token_in_delta_base_units, displayedInputDecimals),
    [symbol(displayedOutputDecimals) + " output"]: units(event.receipt.actual_token_out_delta_base_units, displayedOutputDecimals),
    "Gas": event.receipt.gas_used, "Revert reason": event.receipt.revert_reason,
    "USDC sau swap": event.post_execution_balances
      ? units(event.post_execution_balances.usdc_base_units, 6) : null,
    "WAVAX sau swap": event.post_execution_balances
      ? units(event.post_execution_balances.wavax_base_units, 18) : null,
  };
  return {"Tx hash": event.tx_hash, "Reason codes": event.reason_codes?.join(", ")};
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
  displayedInputDecimals = isReverse(events.find((e) => e.proposal)?.proposal) ? 18 : 6;
  displayedOutputDecimals = displayedInputDecimals === 6 ? 18 : 6;
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
    const decimals = isReverse(attempt[0].proposal) ? 18 : 6;
    button.textContent = "Lần " + (index + 1) + (amount ? " · " + units(amount, decimals) + " " + symbol(decimals) : "");
    button.addEventListener("click", () => renderAttempt(groups, index));
    byId("attempts").append(button);
  });
  const lastEvaluation = workflow.timeline.findLast((event) => event.portfolio);
  if (lastEvaluation) showPortfolio(lastEvaluation.portfolio, mandate, "Snapshot kiểm tra");
  else showPortfolio(defaultPortfolio, mandate);
  byId("empty").hidden = true;
  byId("workflow-body").hidden = false;
  renderAttempt(groups, groups.length - 1);
  const committed = workflow.timeline.findLast((event) => event.receipt?.proof_session);
  if (committed) showRiskBudget(committed.receipt.proof_session, committed.post_execution_balances);
}

let activeMandate;
async function connectTreasury() {
  activeMandate = await loadTreasury();
  byId("connect-form").hidden = true;
}
api("/healthz").then((health) => {
  deploymentMode = health.mode;
  document.querySelector(".environment").textContent = health.mode;
  document.querySelector(".notice").textContent = health.mode === "MOCK" ? "Dữ liệu và receipt mô phỏng" : "Testnet / local · controlled oracle · chưa audit";
  if (health.mode === "MOCK") return connectTreasury();
  byId("connect-form").hidden = false;
  byId("scenarios").hidden = true;
  byId("live-goal-label").hidden = false;
}).catch(showError);
byId("connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  operatorToken = byId("operator-token").value;
  byId("operator-token").value = "";
  try { await connectTreasury(); } catch (error) { operatorToken = ""; showError(error); }
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
    const result = await api("/v1/workflows/start", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({mandate_id: mandateId, goal: deploymentMode === "MOCK" ? "Buy WAVAX with 500 USDC" : byId("live-goal").value,
        ...(deploymentMode === "MOCK" ? {scenario} : {})}),
    });
    const workflowPath = "/v1/workflows/" + result.workflow_id;
    let workflow = await api(workflowPath);
    display(workflow, activeMandate);
    for (let poll = 0; poll < 30 && ["SUBMITTED", "SUBMITTING"].includes(workflow.status); poll++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      workflow = await api(workflowPath);
      display(workflow, activeMandate);
    }
  } catch (error) {
    showError(error);
    byId("empty-message").textContent = "Chưa tải được kết quả. Có thể chạy lại kịch bản mock.";
    byId("workflow-status").textContent = "Lỗi";
    byId("workflow-status").className = "status stop";
  } finally {
    byId("run").disabled = false;
  }
});
