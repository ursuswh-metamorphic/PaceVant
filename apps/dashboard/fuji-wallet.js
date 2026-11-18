"use strict";
const $ = (id) => document.getElementById(id);
function setStatus(text) { $("status").textContent = text; }
function formatToken(raw, decimals) {
  const n = BigInt(raw), base = 10n ** BigInt(decimals), fraction = (n % base).toString().padStart(decimals, "0").replace(/0+$/, "");
  return (n / base).toLocaleString("en-US") + (fraction ? "." + fraction.slice(0, 8) : "");
}
function render(data) {
  $("result").hidden = false;
  $("explorer").href = data.explorer_url;
  $("block").textContent = "Block " + data.block_number + " · hash " + data.block_hash + " · " + new Date(data.block_timestamp * 1000).toISOString();
  const cards = $("assets"); cards.replaceChildren();
  for (const asset of data.assets) {
    const card = document.createElement("article"); card.className = "asset";
    const name = document.createElement("b"); name.textContent = asset.symbol;
    const value = document.createElement("strong"); value.textContent = formatToken(asset.balance_base_units, asset.decimals);
    const kind = document.createElement("small"); kind.textContent = asset.kind;
    card.append(name, value, kind); cards.appendChild(card);
  }
  const o = data.oracle;
  $("oracle").textContent = "AVAX / USD · " + o.provider + " · " + o.status +
    (o.price_usd_e8 ? " · $" + formatToken(o.price_usd_e8, 8) : "") +
    (o.updated_at ? " · updated " + new Date(o.updated_at * 1000).toISOString() : "") +
    " · trading authorization: disabled";
  const m = data.market;
  $("market").textContent = "AVAX / USD · " + m.provider + " · " + m.status +
    (m.price_usd_e8 ? " · $" + formatToken(m.price_usd_e8, 8) : "") +
    (m.updated_at ? " · updated " + new Date(m.updated_at * 1000).toISOString() : "") +
    " · trading authorization: disabled";
  $("raw").textContent = JSON.stringify(data, null, 2);
}
$("connect").addEventListener("click", async () => {
  const eth = window.ethereum;
  if (!eth?.request) { setStatus("Không tìm thấy injected wallet (Core/MetaMask). Bạn vẫn có thể nhập địa chỉ công khai."); return; }
  try {
    const chain = await eth.request({method:"eth_chainId"});
    if (Number.parseInt(chain, 16) !== 43113) { setStatus("Wallet chưa ở Avalanche Fuji 43113. Hãy đổi mạng trong extension; ứng dụng không tự chuyển."); return; }
    const accounts = await eth.request({method:"eth_requestAccounts"});
    if (accounts?.[0]) { $("wallet").value = accounts[0]; setStatus("Đã lấy địa chỉ công khai, chưa ký giao dịch."); }
  } catch { setStatus("Wallet không cấp quyền truy cập địa chỉ hoặc đã đóng hộp thoại."); }
});
$("refresh").addEventListener("click", async () => {
  const address = $("wallet").value.trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) { setStatus("Địa chỉ ví không hợp lệ."); return; }
  const token = $("token").value;
  if (!token) { setStatus("Cần operator token để gọi Fuji API đã bảo vệ."); return; }
  $("refresh").disabled = true;
  $("result").hidden = true;
  setStatus("Đang đọc Fuji RPC với các lệnh read-only...");
  try {
    const res = await fetch("/v1/fuji/wallet/" + encodeURIComponent(address), {
      headers: {"Authorization": "Bearer " + token}, cache:"no-store"
    });
    const body = await res.json();
    if (!res.ok) throw Error(body.error?.code || "FUJI_READ_FAILED");
    render(body);
    setStatus("Đọc trạng thái thật từ Avalanche Fuji thành công. Không có giao dịch được gửi.");
  } catch (error) { setStatus("Không đọc được: " + error.message + " (không dùng mock fallback)."); }
  finally { $("refresh").disabled = false; }
});
