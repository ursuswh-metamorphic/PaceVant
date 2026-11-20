export function approvalDeadline(context, now = Math.floor(Date.now() / 1000)) {
  const bounds = [context.timestamp + context.max_ttl, context.oracle_valid_until,
    context.session_expires_at, context.policy_expires_at];
  if (!bounds.every(Number.isSafeInteger)) throw new Error("Refresh the verified treasury context");
  const deadline = Math.min(...bounds);
  if (deadline <= now) throw new Error("Oracle or authorization window expired; refresh before submitting");
  return deadline;
}
