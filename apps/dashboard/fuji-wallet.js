"use strict";

const byId = (id) => document.getElementById(id);
let lastSnapshot;
const labels = {
  WITHIN_HEARTBEAT: "Trong heartbeat",
  FRESH: "Mới",
  STALE: "Đã cũ",
  UNVERIFIED: "Chưa có cập nhật hợp lệ",
  UNAVAILABLE: "Không đọc được",
};
function setStatus(text, error = false) {
  byId("status").textContent = text;
  byId("status").className = error ? "error" : "";
}
function formatToken(raw, decimals) {
  if (raw == null) return "—";
  const n = BigInt(raw);
  const base = 10n ** BigInt(decimals);
  const fraction = (n % base).toString().padStart(decimals, "0");
  if (n > 0n && n < base && fraction.slice(0, 8) === "00000000") return "< 0.00000001";
  const visible = fraction.slice(0, 8).replace(/0+$/, "");
  return (n / base).toLocaleString("en-US") + (visible ? "." + visible : "");
}
function age(seconds) {
  if (seconds == null) return "Chưa có timestamp";
  if (seconds < 0) return "Timestamp ở tương lai";
  if (seconds < 60) return seconds + " giây";
  if (seconds < 3600) return Math.floor(seconds / 60) + " phút";
  if (seconds < 86400) return Math.floor(seconds / 3600) + " giờ";
  return Math.floor(seconds / 86400) + " ngày";
}
function link(element, url) {
  element.href = url;
  element.target = "_blank";
  element.rel = "noopener noreferrer";
}
function node(tag, content, className) {
  const result = document.createElement(tag);
  if (content != null) result.textContent = content;
  if (className) result.className = className;
  return result;
}
function rows(target, entries) {
  const list = document.createElement("dl");
  for (const [label, value] of entries) {
    if (value == null) continue;
    list.append(node("dt", label), node("dd", String(value)));
  }
  target.replaceChildren(list);
}
function renderOracle(oracle) {
  const card = node("article", null, "oracle");
  const head = node("div", null, "oracle-top");
  const badge = node("span", labels[oracle.status] ?? oracle.status, "badge");
  if (oracle.status === "STALE") badge.classList.add("warn");
  if (["UNAVAILABLE", "UNVERIFIED"].includes(oracle.status)) badge.classList.add("error");
  head.append(node("h3", oracle.provider + " · " + oracle.pair), badge);
  card.append(head, node("strong", oracle.price_usd_e8 ? "$" + formatToken(oracle.price_usd_e8, 8) : "—"));
  card.append(node("p", "Tuổi dữ liệu · " + age(oracle.age_seconds)));
  if (oracle.freshness_limit_seconds) {
    card.append(node("p", (oracle.provider === "PYTH" ? "Ngưỡng hiển thị · " : "Heartbeat · ") + age(oracle.freshness_limit_seconds)));
  }
  if (oracle.updated_at) card.append(node("p", new Date(oracle.updated_at * 1000).toISOString()));
  if (oracle.round_id) card.append(node("p", "Round · " + oracle.round_id));
  if (oracle.reason_code) card.append(node("p", oracle.reason_code));
  if (oracle.confidence_bps != null) card.append(node("p", "Confidence interval · " + oracle.confidence_bps + " bps"));
  if (oracle.explorer_url) {
    const explorer = node("a", "Đối chiếu feed trên explorer ↗");
    link(explorer, oracle.explorer_url);
    card.append(explorer);
  }
  if (oracle.source_url) {
    const registry = node("a", "Nguồn địa chỉ feed ↗");
    link(registry, oracle.source_url);
    card.append(node("br"), registry);
  }
  return card;
}
function render(data) {
  lastSnapshot = data;
  byId("result").hidden = false;
  byId("block-link").textContent = data.block_number.toLocaleString("en-US");
  link(byId("block-link"), "https://explorer-test.avax.network/c-chain/block/" + data.block_number);
  byId("block-time").textContent = new Date(data.block_timestamp * 1000).toISOString();
  byId("snapshot-status").textContent = "Số dư ví · " + data.snapshot_status + (data.cached ? " · cache ≤ 5s" : " · RPC");
  link(byId("explorer"), data.explorer_url);
  byId("assets").replaceChildren(...data.assets.map((asset) => {
    const card = node("article", null, "asset");
    card.append(node("b", asset.symbol), node("strong", formatToken(asset.balance_base_units, asset.decimals)));
    card.append(node("small", asset.reason_code ?? asset.kind));
    if (asset.contract) card.append(node("small", asset.contract));
    return card;
  }));
  byId("oracles").replaceChildren(...data.oracles.map(renderOracle));
  const market = data.market;
  byId("market").textContent = "CoinGecko · " + market.status +
    (market.price_usd_e8 ? " · $" + formatToken(market.price_usd_e8, 8) + " · " + age(market.age_seconds) : "") +
    " · tham khảo off-chain";
  const vault = data.vault;
  byId("vault-panel").hidden = vault.status === "NOT_CONFIGURED";
  if (!byId("vault-panel").hidden) {
    link(byId("vault-link"), vault.explorer_url);
    rows(byId("vault-content"), [
      ["Trạng thái", vault.status], ["Lý do", vault.reason_code],
      ["Owner", vault.owner], ["Attestor", vault.attestor], ["Policy hash", vault.policy_hash],
      ["Policy version", vault.policy_version], ["Policy active", vault.policy_active],
      ["Policy hết hạn", vault.policy_expires_at ? new Date(vault.policy_expires_at * 1000).toISOString() : null],
      ["Paused", vault.paused], ["Ngày UTC", vault.utc_day],
      ["Trần mỗi swap", vault.max_per_swap_base_units ? formatToken(vault.max_per_swap_base_units, 6) + " USDC" : null],
      ["Đã chi trong ngày", vault.daily_spent_usdc_base_units ? formatToken(vault.daily_spent_usdc_base_units, 6) + " USDC" : null],
      ["Ngân sách còn lại", vault.remaining_daily_usdc_base_units ? formatToken(vault.remaining_daily_usdc_base_units, 6) + " USDC" : null],
      ...(vault.assets ?? []).flatMap((asset) => [
        ["Token " + asset.symbol, asset.contract],
        ["Số dư " + asset.symbol, formatToken(asset.balance_base_units, asset.decimals)],
      ]),
      ["Runtime bytecode hash", vault.bytecode_hash],
      ["Đối chiếu deployment", vault.deployment_authenticity],
    ]);
  }
  const receipt = data.receipt;
  byId("receipt-panel").hidden = receipt.status === "NOT_REQUESTED";
  if (!byId("receipt-panel").hidden) {
    link(byId("receipt-link"), receipt.explorer_url);
    rows(byId("receipt-content"), [
      ["Trạng thái", receipt.status], ["Vault recipient khớp", receipt.vault_match],
      ["Block", receipt.block_number], ["Gas dùng", receipt.gas_used],
      ["Phí AVAX", formatToken(receipt.gas_cost_wei, 18)],
      ["SwapExecuted", receipt.swap_events ? JSON.stringify(receipt.swap_events) : null],
    ]);
  }
  byId("raw").textContent = JSON.stringify(data, null, 2);
}
byId("connect").addEventListener("click", async () => {
  const wallet = window.ethereum;
  if (!wallet?.request) {
    setStatus("Trình duyệt chưa có Core / MetaMask. Bạn có thể nhập địa chỉ công khai.");
    return;
  }
  try {
    const chain = await wallet.request({method: "eth_chainId"});
    if (Number.parseInt(chain, 16) !== 43113) {
      setStatus("Chọn Avalanche Fuji 43113 trong ví rồi kết nối lại.", true);
      return;
    }
    const accounts = await wallet.request({method: "eth_requestAccounts"});
    if (accounts?.[0]) {
      byId("wallet").value = accounts[0];
      setStatus("Đã lấy địa chỉ ví công khai.");
    }
  } catch {
    setStatus("Yêu cầu kết nối ví đã đóng.", true);
  }
});
byId("query-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const address = byId("wallet").value.trim();
  const vault = byId("vault-address").value.trim();
  const tx = byId("tx-hash").value.trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(address) || (vault && !/^0x[0-9a-fA-F]{40}$/.test(vault))) {
    setStatus("Địa chỉ ví hoặc Vault chưa hợp lệ.", true);
    return;
  }
  if (tx && !/^0x[0-9a-f]{64}$/.test(tx)) {
    setStatus("Transaction hash cần 64 ký tự hex thường sau 0x.", true);
    return;
  }
  const params = new URLSearchParams();
  if (vault) params.set("vault", vault);
  if (tx) params.set("tx_hash", tx);
  byId("refresh").disabled = true;
  byId("result").hidden = true;
  setStatus("Đang đọc và đối chiếu block Fuji…");
  try {
    const response = await fetch("/v1/fuji/wallet/" + address + "?" + params, {
      headers: {"Authorization": "Bearer " + byId("token").value},
      cache: "no-store", signal: AbortSignal.timeout(25000),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.code ?? "FUJI_READ_FAILED");
    render(data);
    setStatus("Đã đối chiếu snapshot Fuji. Giá và trạng thái từng nguồn hiển thị bên dưới.");
  } catch (error) {
    setStatus("Lượt đọc chưa hoàn tất · " + error.message, true);
  } finally {
    byId("refresh").disabled = false;
  }
});
byId("download").addEventListener("click", () => {
  if (!lastSnapshot) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(lastSnapshot, null, 2)], {type: "application/json"}));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "pacevant-fuji-block-" + lastSnapshot.block_number + ".json";
  anchor.click();
  URL.revokeObjectURL(url);
});
