export const FINAL = new Set(["CONFIRMED", "REVERTED", "REJECTED", "EXPIRED_UNSIGNED"]);
const STORAGE_KEY = "pacevant.mvp.pending.v1";

export class PendingRequest {
  constructor(storage) { this.storage = storage; this.busy = false; }
  current() {
    const raw = this.storage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (!value.key || !["/mvp/workflows", "/mvp/rebalance"].includes(value.path) || !value.body) {
      throw new Error("Invalid saved request; inspect history before clearing browser data");
    }
    return value;
  }
  save(value) { this.storage.setItem(STORAGE_KEY, JSON.stringify(value)); }
  begin(path, body) {
    if (this.current()) throw new Error("Resume the saved request before submitting another operation");
    if (typeof globalThis.crypto?.randomUUID !== "function") throw new Error("Open the demo over HTTPS before submitting a transaction");
    const value = {key:crypto.randomUUID(), path, body:structuredClone(body), created_at:Date.now()};
    this.save(value); // Persist before fetch; a storage failure must prevent the send.
    return value;
  }
  accept(value, result) {
    if (FINAL.has(result.status) || result.executed === false) this.storage.removeItem(STORAGE_KEY);
    else { value.workflow_id = result.workflow_id; this.save(value); }
    return result;
  }
  async resume(api, {readOnly = false} = {}) {
    if (this.busy) return null;
    const value = this.current();
    if (!value) return null;
    this.busy = true;
    try {
      let record;
      try {
        record = await api(value.workflow_id ? "/mvp/workflows/" + encodeURIComponent(value.workflow_id)
          : "/mvp/requests/" + encodeURIComponent(value.key));
      } catch (error) {
        if (error.code !== "MVP_REQUEST_NOT_FOUND" || readOnly) throw error;
        try {
          record = await api(value.path, {method:"POST", headers:{"Content-Type":"application/json", "Idempotency-Key":value.key},
            body:JSON.stringify(value.body)});
        } catch (sendError) {
          // Typed schema rejection means this exact body was not accepted. Auth,
          // conflict, timeout and server errors retain the original request.
          if ([400, 422].includes(sendError.status) && sendError.code === "INVALID_REQUEST") {
            this.storage.removeItem(STORAGE_KEY);
          }
          throw sendError;
        }
      }
      return this.accept(value, record);
    } finally { this.busy = false; }
  }
}
