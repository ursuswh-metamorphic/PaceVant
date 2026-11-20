import {byId,tone} from "../../shared/dom.js";
import {state,isReverse} from "../../shared/state.js";
import {units,symbol} from "../../shared/format.js";
import {showPortfolio,showRiskBudget} from "../treasury/index.js";

function detailRows(event) {
  if (event.stage === "WAITING_FOR_ORACLE") return {
    "Trạng thái": "Chờ round Chainlink thật còn đủ thời gian hợp lệ; chưa mở approval, chưa gửi giao dịch",
    "Freshness còn lại (giây)": event.remaining_feed_freshness_seconds,
    "Cần tối thiểu (giây)": event.required_freshness_seconds,
  };
  if (event.assessment_hash) return {
    "ITAG assessment": event.assessment_hash, "Temporal verdict": event.verdict,
    "Reason codes": event.reason_codes?.join(", "),
    "Timing (ms)": JSON.stringify(event.timing_ms),
  };
  if (event.proof) return {
    "Proof": event.proof.status, "Reason": event.proof.reason,
    "CHECK": event.proof.check_mode, "COMPILE": event.proof.compile_mode, "RISK BOUND": event.proof.risk_bound,
    "Certified risk debit (USD)": units(event.proof.risk_debit_usd_e8, 8),
    "Phi · signed lower bounds": event.proof.phi?.balance_bounds.map((b) => {
      const decimals = state.activeMandate?.registry?.assets.find((a) => a.address === b.asset)?.decimals;
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
    "Guard": event.alignment.shield_model_version,
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
    [symbol(state.displayedInputDecimals) + " input"]: units(event.receipt.actual_token_in_delta_base_units, state.displayedInputDecimals),
    [symbol(state.displayedOutputDecimals) + " output"]: units(event.receipt.actual_token_out_delta_base_units, state.displayedOutputDecimals),
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
  state.displayedInputDecimals = isReverse(events.find((e) => e.proposal)?.proposal) ? 18 : 6;
  state.displayedOutputDecimals = state.displayedInputDecimals === 6 ? 18 : 6;
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

export function display(workflow, mandate) {
  byId("workflow-id").textContent = workflow.workflow_id;
  const plan = workflow.timeline.findLast((event) => event.stage === "PLANNED");
  const provider = plan?.planner_provider ?? workflow.planner_provider;
  byId("planner-source").textContent = provider && provider !== "rules"
    ? (plan ? "Planner thực dùng: " : "Planner cấu hình: ") + provider + " · " + (plan?.planner_model ?? workflow.planner_model ?? "provider rotation")
    : "Planner: rules · offline";
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
  else showPortfolio(state.defaultPortfolio, mandate);
  byId("empty").hidden = true;
  byId("workflow-body").hidden = false;
  renderAttempt(groups, groups.length - 1);
  const committed = workflow.timeline.findLast((event) => event.receipt?.proof_session);
  if (committed) showRiskBudget(committed.receipt.proof_session, committed.post_execution_balances);
}
