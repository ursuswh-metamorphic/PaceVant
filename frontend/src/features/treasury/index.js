import {api} from "../../api/client.js";
import {byId} from "../../shared/dom.js";
import {state} from "../../shared/state.js";
import {units} from "../../shared/format.js";

export function showRiskBudget(s, balances) {
  byId("proof-budgets").textContent = s ? "Certified Risk Consumption: $" + units(s.used_usd_e8, 8) +
    " / $" + units(s.limit_usd_e8, 8) + " · Global UTC day: $" + units(s.global_used_usd_e8, 8) +
    " / $" + units(s.global_limit_usd_e8, 8) + " · USDC input spent: " + units(balances?.daily_spent_usdc_base_units, 6) +
    " USDC. Đây là rủi ro dự phòng, tách biệt với lỗ thực tế và gas." : "Session unavailable — NO SIGN";
}

export function showPortfolio(portfolio, mandate, stage = "Danh mục mẫu") {
  if (!portfolio) return;
  const usdc = BigInt(portfolio.usdc_base_units) * BigInt(portfolio.price_usdc_usd_e8) * 10n ** 12n;
  const wavax = BigInt(portfolio.wavax_base_units) * BigInt(portfolio.price_wavax_usd_e8);
  const total = usdc + wavax;
  document.querySelector(".metric:nth-child(2) > span").textContent = stage;
  const cents = total / 10n ** 24n;
  byId("portfolio-value").textContent = total > 0n && cents === 0n ? "< $0.01" : "$" + units(cents, 2);
  byId("portfolio-balances").textContent =
    units(portfolio.usdc_base_units, 6) + " USDC / " + units(portfolio.wavax_base_units, 18) + " WAVAX";
  byId("current-exposure").textContent = total ? units(wavax * 10000n / total, 2) + "% theo snapshot" : "—";
  byId("exposure-limit").textContent = units(mandate.max_avax_exposure_bps, 2) + "%";
}

export async function loadTreasury() {
  const data = await api(state.demoMode ? "/v1/demo/treasury" : "/v1/treasury");
  const mandate = data.mandate;
  state.deploymentMode = data.mode;
  byId("proof-summary").hidden = !mandate.proof_policy;
  if (mandate.proof_policy) {
    const p = mandate.proof_policy, s = data.proof_session;
    byId("proof-policy").textContent = p.authorization + " · Policy " + mandate.policy_hash +
      " · Loss policy: " + units(p.max_relative_loss_bps, 2) + "% + $" + units(p.fixed_loss_usd_e8, 8) +
      " · Oracle band: " + units(p.oracle_band_bps, 2) + "% · Tolerance: " + units(p.tolerance_bps, 2) + "%" +
      " · Session " + mandate.session_id + " · Reverse cap: " + (BigInt(p.max_wavax_per_swap) ? units(p.max_wavax_per_swap, 18) + " WAVAX" : "DISABLED");
    showRiskBudget(s, data.chain_balances);
  }
  state.defaultPortfolio = data.portfolio;
  if (data.mode === "FUJI" && data.portfolio?.price_source === "CHAINLINK_FUJI_CIRCLE_USDC_AVAX_V1") {
    document.querySelector(".notice").textContent = "FUJI · giá Chainlink tham chiếu · giao dịch testnet";
  }
  state.mandateId = mandate.mandate_id;
  byId("mandate").textContent = "Phiên bản " + mandate.version;
  byId("policy-status").textContent = data.issues[0] ?? mandate.status;
  byId("day-limit").textContent = units(mandate.max_usdc_spend_per_day_base_units, 6) + " / ngày";
  byId("trade-limit").textContent = units(mandate.max_usdc_per_swap_base_units, 6) + " / swap";
  showPortfolio(data.portfolio, mandate, data.mode === "MOCK" ? "Danh mục mẫu" : "Danh mục on-chain");
  byId("run").disabled = false;
  return mandate;
}
