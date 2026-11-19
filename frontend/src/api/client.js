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
  const response = await fetch(apiBase() + path, {...options, redirect:"error", headers:{...options?.headers, ...(state.operatorToken ? {Authorization:"Bearer " + state.operatorToken} : {})}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.code ?? "REQUEST_FAILED");
  return data;
}
