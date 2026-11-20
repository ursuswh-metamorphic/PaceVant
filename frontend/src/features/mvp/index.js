import {api} from "../../api/client.js";
import {state} from "../../shared/state.js";
import {approvalDeadline} from "./terms.js";
import {PendingRequest} from "./requests.js";

const $ = id => document.getElementById(id);
const requests = new PendingRequest(window.sessionStorage);
const pretty = value => JSON.stringify(value, null, 2);
const post = body => ({method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
const session = () => $("session").value.trim();
const call = (path, options = {}) => api(path, {...options, signal:AbortSignal.timeout(options.method === "POST" ? 60000 : 45000)});
let context = null, readiness = null, prepared = null, refreshing = false, timer = null, failures = 0;

function units(value, decimals, precision = 6) {
  let number = BigInt(value), negative = number < 0n;
  if (negative) number = -number;
  const scale = 10n ** BigInt(decimals);
  const tail = (number % scale).toString().padStart(decimals, "0").slice(0, precision).replace(/0+$/, "");
  return (negative ? "−" : "") + (number / scale).toString() + (tail ? "." + tail : "");
}
function amount(text, decimals) {
  if (!/^(0|[1-9][0-9]*)(\.[0-9]+)?$/.test(text)) throw new Error("Enter an exact decimal amount");
  const [whole, fraction = ""] = text.split(".");
  if (fraction.length > decimals) throw new Error("Too many decimal places");
  const value = BigInt(whole) * 10n ** BigInt(decimals) + BigInt(fraction.padEnd(decimals, "0") || "0");
  if (value <= 0n) throw new Error("Amount must be positive");
  return value.toString();
}
async function action(fn) {
  $("error").hidden = true;
  try { return await fn(); }
  catch (error) {
    $("error").textContent = error.name === "TimeoutError" ? "Response delayed. Your saved request is retained; use Resume, never create another payment." : error.message;
    $("error").hidden = false;
  } finally { updateControls(); }
}
function tab(id) {
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.setAttribute("aria-selected", String(button.dataset.tab === id));
    $(button.dataset.tab).hidden = button.dataset.tab !== id;
  }
}
for (const button of document.querySelectorAll("[data-tab]")) button.addEventListener("click", () => tab(button.dataset.tab));
function selectedAvailability() {
  return readiness?.operations?.find(op => op.operation === $("kind").value &&
    (op.operation === "USDC_PAYMENT" || op.direction === ($("route").value === "reverse" ? "WAVAX_TO_USDC" : "USDC_TO_WAVAX")));
}
function updateControls() {
  let saved;
  try { saved = requests.current(); }
  catch { saved = {body:{operation:"unreadable"}}; $("error").hidden = false;
    $("error").textContent = "Saved request is unreadable. Inspect treasury history before clearing tab data."; }
  const blocked = !context || !selectedAvailability()?.ready;
  $("execute").disabled = Boolean(saved) || blocked;
  $("resume-request").disabled = !state.operatorToken || requests.busy;
  $("request-recovery").hidden = !saved;
  $("request-description").textContent = saved ? `Saved ${saved.body.operation ?? "rebalance"} request · ${saved.workflow_id ?? "awaiting acknowledgement"}. Resume uses the same authorization and request key.` : "";
  for (const input of $("operation").querySelectorAll("input,select,textarea")) input.disabled = Boolean(saved);
  $("slippage").disabled = Boolean(saved) || $("kind").value === "USDC_PAYMENT";
  for (const id of ["rebalance", "enable-auto", "demo-payment", "demo-swap"]) {
    $(id).disabled = !context || Boolean(saved) || !readiness?.ready;
  }
  if (context && !(context.authority.operation_mask & 16)) {
    $("rebalance").disabled = true;
    $("enable-auto").disabled = true;
  }
  $("operation-readiness").textContent = selectedAvailability()?.ready ? "Ready for security evaluation. This is not an approval." :
    (selectedAvailability()?.reasons?.join(" · ") || "Connect and wait for verified readiness");
}
function updateForm() {
  const payment = $("kind").value === "USDC_PAYMENT";
  $("route-label").hidden = payment;
  $("payee-label").hidden = !payment;
  $("amount-unit").textContent = !payment && $("route").value === "reverse" ? "WAVAX" : "USDC";
  updateControls();
}
$("kind").addEventListener("change", () => { $("amount").value = $("kind").value === "USDC_PAYMENT" ? "0.01" : "0.000001"; updateForm(); });
$("route").addEventListener("change", () => { $("amount").value = $("route").value === "reverse" ? "0.001" : "0.000001"; updateForm(); });
function balances(data) {
  if (data.balances) {
    $("usdc").textContent = units(data.balances[0], 6);
    $("wavax").textContent = units(data.balances[1], 18);
  }
  if (data.relayer_avax_wei !== undefined) $("relayer").textContent = units(data.relayer_avax_wei, 18);
}
function environmentLabels(environment) {
  const local = environment === "LOCAL_TEST", fork = environment === "ANVIL_FORK";
  document.querySelector(".intro .notice").textContent = local ? "LOCAL TEST · ISOLATED EVM" : fork ? "ANVIL FORK · FUJI SOURCE" : "AVALANCHE FUJI TESTNET";
  $("usdc").nextElementSibling.textContent = local ? "Local test token · not public Circle USDC" : fork ? "Copied Circle USDC state · Anvil fork" : "Exact Circle identity on Fuji";
}
function history(records) {
  $("history").replaceChildren();
  for (const record of records ?? []) {
    const item = document.createElement("li"), button = document.createElement("button");
    button.textContent = `${record.intent?.operation ?? record.operation} · ${record.status}`;
    button.disabled = !record.workflow_id || !state.operatorToken;
    if (record.workflow_id) button.addEventListener("click", () => action(async () => render(await call("/mvp/workflows/" + record.workflow_id))));
    item.append(button); $("history").append(item);
  }
}
function render(record) {
  $("workflow-state").textContent = `${record.status} · ${record.reason_code ?? record.workflow_id}`;
  $("timeline").replaceChildren(); $("evidence").replaceChildren();
  for (const event of record.timeline ?? []) {
    const item = document.createElement("li"), details = document.createElement("details"), summary = document.createElement("summary"), pre = document.createElement("pre");
    item.textContent = event.stage; $("timeline").append(item);
    summary.textContent = event.stage; pre.textContent = pretty(event.evidence); details.append(summary, pre); $("evidence").append(details);
  }
  if (record.outcome) {
    const item = document.createElement("li");
    item.textContent = `${record.outcome.environment ?? "UNVERIFIED"} · ${record.outcome.status} · ${record.outcome.tx_hash ?? "No broadcast"}`;
    if (record.outcome.public_chain_receipt && /^0x[0-9a-f]{64}$/.test(record.outcome.tx_hash)) {
      const link = document.createElement("a"); link.href = "https://testnet.snowtrace.io/tx/" + record.outcome.tx_hash;
      link.textContent = " View Fuji transaction"; link.target = "_blank"; link.rel = "noopener noreferrer"; item.append(link);
    }
    $("timeline").append(item);
  }
}
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const [available, data] = await Promise.all([call("/mvp/readiness"), call(state.operatorToken ? "/mvp/treasury/" + encodeURIComponent(session()) : "/mvp/status")]);
    readiness = available;
    $("readiness-summary").textContent = available.ready ? "Ready for a bounded demo" : "Waiting for safe execution conditions";
    $("readiness-checks").replaceChildren();
    for (const check of available.checks ?? []) if (!check.ready) {
      const item = document.createElement("li"); item.textContent = `${check.code}: ${check.action}`; $("readiness-checks").append(item);
    }
    if (!state.operatorToken) { balances(data); $("environment").textContent = data.source; environmentLabels(data.source); history(data.history); return; }
    context = data.context; balances(context); $("environment").textContent = context.environment; environmentLabels(context.environment);
    $("slippage").max = String(context.max_slippage_bps);
    $("slippage").value = String(Math.min(Number($("slippage").value), context.max_slippage_bps));
    $("agent").textContent = context.paused ? "Owner paused" : !context.session_active ? "Session revoked" : data.autonomy.enabled ? "Autonomous" : "Manual";
    $("scope").textContent = `${context.authority.actions}/${context.authority.max_actions} actions · expires ${new Date(context.session_expires_at * 1000).toLocaleString("vi-VN", {timeZone:"Asia/Ho_Chi_Minh", hour12:false})} (UTC+7)`;
    if (context.nominal_prices) {
      const usdc = BigInt(context.balances[0]) * BigInt(context.nominal_prices[0]) / 1000000n;
      const wavax = BigInt(context.balances[1]) * BigInt(context.nominal_prices[1]) / 10n ** 18n;
      $("allocation").textContent = (usdc + wavax ? units(wavax * 10000n / (usdc + wavax), 2, 2) : "0") + "% WAVAX · target " + data.targets.target_wavax_bps / 100 + "%";
    } else $("allocation").textContent = "Balances verified; fresh oracle reference unavailable";
    $("budgets").textContent = pretty({swap_spend_remaining_usd_e8:context.swap_spend_remaining,
      payment_spend_remaining_usdc:context.payment_spend_remaining_usdc, daily_swap_remaining_usd_e8:context.daily_swap_remaining,
      daily_payment_remaining_usdc:context.daily_payment_remaining_usdc, economic_risk_remaining_usd_e8:context.risk_remaining});
    $("policy").textContent = pretty({policy_hash:context.policy_hash, policy_version:context.policy_version, paused:context.paused,
      session_active:context.session_active, session_expires_at:context.session_expires_at, authority:context.authority, proof_policy:context.proof_policy});
    $("allowlists").textContent = pretty({tokens:context.token_allowlist, adapter:context.adapter, adapter_allowed:context.adapter_allowed, payees:context.recipient_allowlist});
    $("gas-expenses").textContent = pretty(data.system_gas_expenses);
    const selected = $("payee").value; $("payee").replaceChildren();
    for (const payee of context.recipient_allowlist) {
      const option = document.createElement("option"); option.value = payee.recipient; option.textContent = payee.recipient; $("payee").append(option);
    }
    if (context.recipient_allowlist.some(p => p.recipient === selected)) $("payee").value = selected;
    history(data.history);
  } finally { refreshing = false; updateControls(); }
}
async function resume(readOnly = false) {
  const record = await requests.resume(call, {readOnly});
  if (record) { render(record); if (!requests.current()) await refresh(); }
  updateControls();
}
$("connect").addEventListener("submit", event => { event.preventDefault(); context = null; readiness = null;
  state.operatorToken = $("credential").value; updateControls();
  $("credential").value = ""; action(async () => { await refresh(); if (requests.current()) await resume(true); }); });
$("refresh").addEventListener("click", () => action(refresh));
$("resume-request").addEventListener("click", () => action(() => resume()));
$("operation").addEventListener("submit", event => { event.preventDefault(); action(async () => {
  if (!context || requests.current()) throw new Error("Connect or resume the saved request first");
  await refresh();
  if (!selectedAvailability()?.ready) throw new Error(selectedAvailability()?.reasons?.join(" · ") || "Execution is not ready");
  const payment = $("kind").value === "USDC_PAYMENT", reverse = !payment && $("route").value === "reverse";
  const input = reverse ? context.wavax : context.usdc, output = payment ? context.usdc : reverse ? context.usdc : context.wavax;
  const recipient = payment ? $("payee").value : context.treasury;
  if (payment && !recipient) throw new Error("No owner-approved USDC recipient");
  const rawAmount = amount($("amount").value.trim(), reverse ? 18 : 6);
  if (BigInt(rawAmount) > BigInt(context.balances[reverse ? 1 : 0])) throw new Error("Insufficient treasury balance");
  if (payment) {
    const payee = context.recipient_allowlist.find(value => value.recipient === recipient);
    if (!payee || [context.max_payment_usdc, context.payment_spend_remaining_usdc, context.daily_payment_remaining_usdc,
      payee.per_payment, (BigInt(payee.per_session) - BigInt(payee.session_spent)).toString(),
      (BigInt(payee.per_day) - BigInt(payee.daily_spent)).toString()].some(cap => BigInt(rawAmount) > BigInt(cap))) {
      throw new Error("Payment exceeds the verified recipient/session/day limit");
    }
  }
  requests.begin("/mvp/workflows", {operation:$("kind").value, chain_id:context.chain_id, treasury:context.treasury,
    session_id:session(), token_in:input, token_out:output, recipient, amount:rawAmount,
    slippage_bps:payment ? 0 : Number($("slippage").value), deadline:approvalDeadline(context), objective:$("objective").value});
  updateControls(); await resume();
}); });
for (const [id, kind, value, goal] of [["demo-payment", "USDC_PAYMENT", "0.01", "Pay exactly 0.01 Circle USDC to the owner-approved system EOA"],
  ["demo-swap", "SWAP_EXACT_IN", "0.000001", "Swap exactly 0.000001 Circle USDC for WAVAX to the treasury"]]) {
  $(id).addEventListener("click", () => { $("kind").value = kind; $("route").value = "forward";
    $("amount").value = value; $("objective").value = goal; updateForm(); tab("console"); });
}
for (const [id, execute] of [["preview", false], ["rebalance", true]]) $(id).addEventListener("click", () => action(async () => {
  const body = {session_id:session(), execute, objective:$("objective").value};
  if (execute) { requests.begin("/mvp/rebalance", body); updateControls(); await resume(); }
  else { const result = await call("/mvp/rebalance", post(body)); $("rebalance-result").textContent = pretty(result); }
}));
for (const [id, enabled] of [["enable-auto", true], ["disable-auto", false]]) $(id).addEventListener("click", () => action(async () => {
  await call("/mvp/autonomy", post({enabled, session_id:session()})); await refresh();
}));
$("prepare-admin").addEventListener("click", () => action(async () => {
  const result = await call("/mvp/admin/prepare", post({action:$("admin-action").value, session_id:session()}));
  prepared = result.owner_transaction; $("admin-result").textContent = pretty(result); $("send-admin").disabled = false;
}));
$("send-admin").addEventListener("click", () => action(async () => {
  if (!prepared || !window.ethereum) throw new Error("Owner wallet required; preparing does not broadcast");
  const accounts = await window.ethereum.request({method:"eth_requestAccounts"}), chain = await window.ethereum.request({method:"eth_chainId"});
  if (accounts[0]?.toLowerCase() !== prepared.from.toLowerCase() || chain.toLowerCase() !== prepared.chainId.toLowerCase()) throw new Error("Exact Owner address and chain required");
  const tx = await window.ethereum.request({method:"eth_sendTransaction", params:[prepared]});
  $("admin-result").textContent = "Owner submitted: " + tx; prepared = null; $("send-admin").disabled = true;
}));
for (const [id, label] of [["invalid-payee", "Unauthorized payment"], ["prompt-injection", "Injected proposal"], ["state-drift", "State drift / slippage"],
  ["daily-cap", "Daily payment cap"], ["tampered-calldata", "Tampering and replay"], ["kill-switch", "Revoked session"]]) {
  const button = document.createElement("button"); button.textContent = label;
  button.addEventListener("click", () => action(async () => { button.disabled = true;
    try { $("attack-result").textContent = pretty(await call("/mvp/attack-lab/" + id, post({}))); } finally { button.disabled = false; }
  })); $("attack-cases").append(button);
}
async function tick() {
  if (document.hidden) return schedule();
  try {
    if (!session()) {
      const capabilities = await call("/mvp/capabilities");
      if (capabilities.default_session_id) $("session").value = capabilities.default_session_id;
    }
    if (state.operatorToken && requests.current()) await resume(true);
    else await refresh();
    failures = 0;
  } catch (error) {
    failures++;
    $("readiness-summary").textContent = "Connection interrupted; retrying safely. Saved requests remain intact.";
    if (error.code !== "MVP_REQUEST_NOT_FOUND") { readiness = null; updateControls(); }
  } finally { schedule(); }
}
function schedule() {
  clearTimeout(timer);
  let pending = false;
  try { pending = Boolean(requests.current()); } catch { failures++; }
  timer = setTimeout(tick, Math.min(60000, (pending ? 5000 : 20000) * 2 ** Math.min(failures, 3)));
}
action(async () => {
  const capabilities = await call("/mvp/capabilities");
  $("availability").textContent = (capabilities.reason ?? `${capabilities.environment} · Two operations. Each submission passes the security pipeline.`) +
    (capabilities.semantic_evaluation_scope?.startsWith("SCRIPTED") ? " LOCAL TEST: scripted semantics; real local EVM and Z3." : "");
  if (capabilities.default_session_id) $("session").value = capabilities.default_session_id;
  await refresh(); updateForm();
}).finally(schedule);
window.addEventListener("pagehide", () => clearTimeout(timer));
