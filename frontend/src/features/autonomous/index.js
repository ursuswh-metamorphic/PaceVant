import {api} from "../../api/client.js";
import {state} from "../../shared/state.js";

const $ = id => document.getElementById(id);
let context = null, preparedAdmin = null, capability = null, pending = null;
const stringify = data => JSON.stringify(data, null, 2);
const json = (body, key) => ({method:"POST", headers:{"Content-Type":"application/json", ...(key ? {"Idempotency-Key":key} : {})}, body:JSON.stringify(body)});
const session = () => $("session").value.trim();
const money = value => "$" + units(BigInt(value), 8, 2);
function units(value, decimals, precision = 6) {
  const negative = value < 0n; if (negative) value = -value;
  const scale = 10n ** BigInt(decimals), fraction = (value % scale).toString().padStart(decimals, "0").slice(0, precision).replace(/0+$/, "");
  return (negative ? "−" : "") + (value / scale).toString() + (fraction ? "." + fraction : "");
}
function amount(text, decimals) {
  if (!/^(0|[1-9][0-9]*)(\.[0-9]+)?$/.test(text)) throw new Error("Enter an exact positive decimal amount");
  const [whole, fraction = ""] = text.split(".");
  if (fraction.length > decimals) throw new Error("Too many decimal places for this asset");
  const value = BigInt(whole) * 10n ** BigInt(decimals) + BigInt(fraction.padEnd(decimals, "0") || "0");
  if (value <= 0n) throw new Error("Amount must be positive");
  return value.toString();
}
function error(exc) { $("error").textContent = exc.message; $("error").hidden = false; }
async function action(fn) { $("error").hidden = true; try { return await fn(); } catch (exc) { error(exc); } }
for (const button of document.querySelectorAll("[data-tab]")) button.addEventListener("click", () => {
  for (const tab of document.querySelectorAll("[data-tab]")) { tab.setAttribute("aria-selected", String(tab === button)); $(tab.dataset.tab).hidden = tab !== button; }
});
function symbol(address) { return address === context.usdc ? "USDC" : address === context.wavax ? "WAVAX" : address === context.shares ? "vault shares" : "AVAX"; }
async function refresh() {
  const data = await api("/v3/treasury/" + encodeURIComponent(session()));
  context = data.context;
  const balances = context.balances.map(BigInt), [pu,pw] = context.nominal_prices.map(BigInt);
  const shareUnit = BigInt(context.share_unit), shareDecimals = shareUnit.toString().length - 1;
  const values = [balances[0] * pu / 1000000n, balances[1] * pw / 10n**18n,
    balances[2] * BigInt(context.share_rate_low) * pu / shareUnit / 1000000n, balances[3] * pw / 10n**18n];
  $("portfolio").textContent = money(values.reduce((a,b) => a+b, 0n));
  const total = values[0]+values[1], wBps = total ? values[1]*10000n/total : 0n;
  $("allocation").textContent = units(10000n-wBps,2,2) + "% / " + units(wBps,2,2) + "%";
  $("targets").textContent = `Liquid targets: ${data.targets.target_usdc_bps/100}% USDC / ${data.targets.target_wavax_bps/100}% WAVAX`;
  $("spend").textContent = money(context.spend_remaining);
  $("risk").textContent = "Risk remaining: " + money(context.risk_remaining) + " · Day spend: " + money(context.daily_spend_remaining);
  $("agent").textContent = context.paused ? "Owner paused" : !context.session_active ? "Session revoked" : data.autonomy.enabled ? "Autonomous" : "Manual";
  $("scope").textContent = `${context.authority.actions}/${context.authority.max_actions} actions · ${context.authority.cooldown}s cooldown`;
  $("assets").replaceChildren();
  for (const [index,name] of ["USDC","WAVAX","ERC-4626 shares","Native AVAX"].entries()) {
    const row = document.createElement("tr");
    for (const value of [name, units(balances[index],[6,18,shareDecimals,18][index]),money(values[index])]) { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }
    $("assets").append(row);
  }
  $("vault-position").textContent = `Underlying represented at observed conversion: ${units(balances[2]*BigInt(context.share_rate)/shareUnit,6)} USDC. Reference valuation uses the owner’s conservative lower rate.`;
  $("policy").textContent = stringify({policy_hash:context.policy_hash, version:context.policy_version, paused:context.paused, policy_active:context.policy_active, session_active:context.session_active, session_expires_at:context.session_expires_at, authority:context.authority, proof_policy:context.proof_policy, max_wavax_exposure_bps:context.max_wavax_exposure_bps, oracle:context.oracle});
  $("allowlists").textContent = stringify({tokens:context.token_allowlist, adapter:context.adapter, adapter_allowed:context.adapter_allowed, vault:context.shares, payees:context.recipient_allowlist});
  const previous = $("payee").value; $("payee").replaceChildren();
  for (const [index,payee] of context.recipient_allowlist.entries()) { const option = document.createElement("option"); option.value = String(index); option.textContent = `${symbol(payee.token)} · ${payee.recipient}`; $("payee").append(option); }
  if (previous) $("payee").value = previous;
  $("history").replaceChildren();
  for (const record of data.history) { const li = document.createElement("li"), button = document.createElement("button"); button.textContent = `${record.intent.operation} · ${record.status}`; button.addEventListener("click", () => action(async () => renderWorkflow(await api("/v3/workflows/" + record.workflow_id)))); li.append(button); $("history").append(li); }
  updateOperation();
}
function updateOperation() {
  const kind = $("kind").value;
  $("route-label").hidden = kind !== "TOKEN_SWAP"; $("payee-label").hidden = kind !== "TOKEN_PAYMENT";
  let unit = kind === "VAULT_WITHDRAW" ? "vault shares" : kind === "TOKEN_SWAP" && $("route").value === "reverse" ? "WAVAX" : "USDC";
  if (context && kind === "TOKEN_PAYMENT") { const payee = context.recipient_allowlist[Number($("payee").value)]; if (payee) unit = symbol(payee.token); }
  $("amount-unit").textContent = unit;
  $("slippage").disabled = kind === "TOKEN_PAYMENT";
}
for (const id of ["kind","route","payee"]) $(id).addEventListener("change", updateOperation);
function renderWorkflow(record) {
  $("workflow-state").textContent = `${record.status} · ${record.reason_code ?? record.workflow_id}`;
  $("timeline").replaceChildren(); $("evidence").replaceChildren();
  for (const entry of record.timeline ?? []) {
    const li = document.createElement("li"); li.textContent = entry.stage; $("timeline").append(li);
    const details = document.createElement("details"), summary = document.createElement("summary"), pre = document.createElement("pre");
    summary.textContent = entry.stage; pre.textContent = stringify(entry.evidence); details.append(summary,pre); $("evidence").append(details);
  }
  if (record.outcome?.tx_hash) { const li = document.createElement("li"); li.textContent = `${record.outcome.environment ?? "LOCAL EVM"} receipt: ${record.outcome.tx_hash}`; $("timeline").append(li); }
}
$("connect").addEventListener("submit", event => { event.preventDefault(); state.operatorToken = $("credential").value; $("credential").value = ""; action(refresh); });
$("refresh").addEventListener("click", () => action(refresh));
$("operation").addEventListener("submit", event => { event.preventDefault(); action(async () => {
  if (!context) throw new Error("Connect an owner-authorized treasury first");
  let input=context.usdc, output=context.wavax, recipient=context.treasury;
  const operation=$("kind").value;
  if (operation === "TOKEN_SWAP" && $("route").value === "reverse") [input,output]=[output,input];
  if (operation === "VAULT_DEPOSIT") output=context.shares;
  if (operation === "VAULT_WITHDRAW") [input,output]=[context.shares,context.usdc];
  if (operation === "TOKEN_PAYMENT") { const payee=context.recipient_allowlist[Number($("payee").value)]; if (!payee) throw new Error("No owner-approved payee"); input=output=payee.token; recipient=payee.recipient; }
  const decimals=input === context.usdc ? 6 : input === context.shares ? context.share_unit.length-1 : 18;
  const payload={operation,chain_id:context.chain_id,treasury:context.treasury,session_id:session(),token_in:input,token_out:output,recipient,amount:amount($("amount").value.trim(),decimals),slippage_bps:Number($("slippage").value),deadline:Math.min(context.timestamp+context.max_ttl,context.session_expires_at,context.policy_expires_at),objective:$("objective").value};
  const fingerprint=stringify(payload);
  if (!pending || pending.fingerprint !== fingerprint) pending={key:crypto.randomUUID(),fingerprint};
  $("execute").disabled=true;
  try { const record=await api("/v3/workflows",json(payload,pending.key)); renderWorkflow(record); if (["CONFIRMED","REJECTED","REVERTED","EXPIRED_UNSIGNED"].includes(record.status)) pending=null; await refresh(); }
  finally { $("execute").disabled=false; }
}); });
for (const [id,execute] of [["preview",false],["rebalance",true]]) $(id).addEventListener("click", () => action(async () => { const result=await api("/v3/rebalance",json({session_id:session(),execute,objective:$("objective").value},crypto.randomUUID())); $("rebalance-result").textContent=stringify(result.proposal ?? {status:result.status,reason:result.reason}); if (result.workflow_id) renderWorkflow(result); await refresh(); }));
for (const [id,enabled] of [["enable-auto",true],["disable-auto",false]]) $(id).addEventListener("click", () => action(async () => { await api("/v3/autonomy",json({enabled,session_id:session()})); await refresh(); }));
$("prepare-admin").addEventListener("click", () => action(async () => { const result=await api("/v3/admin/prepare",json({action:$("admin-action").value,session_id:session()})); preparedAdmin=result.owner_transaction; $("admin-result").textContent=stringify(result); $("send-admin").disabled=false; }));
$("send-admin").addEventListener("click", () => action(async () => { if (!preparedAdmin || !window.ethereum) throw new Error("An owner wallet extension is required to sign this prepared transaction"); const accounts=await window.ethereum.request({method:"eth_requestAccounts"}); const chain=await window.ethereum.request({method:"eth_chainId"}); if (accounts[0]?.toLowerCase() !== preparedAdmin.from.toLowerCase() || chain.toLowerCase() !== preparedAdmin.chainId.toLowerCase()) throw new Error("Connect the exact owner address on the configured local chain"); const hash=await window.ethereum.request({method:"eth_sendTransaction",params:[preparedAdmin]}); $("admin-result").textContent="Owner wallet submitted: "+hash; preparedAdmin=null; $("send-admin").disabled=true; }));
const attacks=[["prompt-injection","Unauthorized injected proposal"],["tampered-calldata","Tampered calldata"],["state-drift","State drift after proof"],["severe-slippage","Severe slippage / MEV"],["cumulative-loss","Repeated small losses"],["invalid-payee","Invalid recipient"],["excessive-allowance","Excessive allowance"],["kill-switch","Pause and revoked session"]];
for (const [id,label] of attacks) { const button=document.createElement("button"); button.textContent=label; button.addEventListener("click",()=>action(async()=>{ button.disabled=true; try { $("attack-result").textContent=stringify(await api("/v3/attack-lab/"+id,json({}))); } finally {button.disabled=false;} })); $("attack-cases").append(button); }
action(async()=>{ capability=await api("/v3/capabilities"); $("environment").textContent=capability.environment ?? "V3 NOT ACTIVATED"; $("availability").textContent=capability.enabled ? `${capability.environment} · Isolated EVM execution. ${capability.vault_label}. Existing public Fuji execution uses the original dashboard.` : capability.reason; if (capability.default_session_id) $("session").value=capability.default_session_id; if (!capability.enabled) for (const button of document.querySelectorAll("button")) if (!button.dataset.tab) button.disabled=true; });
