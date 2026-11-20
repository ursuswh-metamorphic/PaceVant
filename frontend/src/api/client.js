import {state} from "../shared/state.js";

function apiBase() {
  const base = (window.TREASURY_CONFIG?.apiBaseUrl ?? "").replace(/\/$/, "");
  if (!base) return "";
  const parsed = new URL(base, window.location.origin);
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("INVALID_API_BASE_URL");
  }
  return base;
}

export async function api(path, options) {
  const credential = path.startsWith("/v1/demo/") ? state.demoToken : state.operatorToken;
  const response = await fetch(apiBase() + path, {...options, redirect:"error", headers:{...options?.headers, ...(credential ? {Authorization:"Bearer " + credential} : {})}});
  let data;
  try { data = await response.json(); }
  catch { const error = new Error("SERVER_RESPONSE_UNAVAILABLE"); error.code = "SERVER_RESPONSE_UNAVAILABLE"; error.status = response.status; throw error; }
  if (!response.ok) {
    const error = new Error(data.error?.code ?? "REQUEST_FAILED");
    error.code = data.error?.code ?? "REQUEST_FAILED";
    error.status = response.status;
    throw error;
  }
  return data;
}
