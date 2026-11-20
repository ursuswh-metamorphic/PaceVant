"""Read-only operational readiness. This is never a security approval or a gas send."""

import re


def reason(error):
    code = getattr(error, "code", str(error) if isinstance(error, ValueError) else "RPC_UNAVAILABLE")
    return code if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", code) else "RPC_UNAVAILABLE"


def inspect(workflows):
    execution = workflows.execution
    m = execution.manifest
    c = execution.display_context(m.default_session_id)
    now = max(workflows.clock(), c["timestamp"])
    checks = []

    def check(name, ok, action):
        checks.append({"code": name, "ready": bool(ok), "action": action})

    check("VAULT_PAUSED", not c["paused"], "Owner must review and unpause the vault")
    check("POLICY_EXPIRED_OR_REVOKED", c["policy_active"] and now < c["policy_expires_at"], "Owner must renew the policy")
    check("SESSION_UNAVAILABLE", c["session_active"] and c["session_starts_at"] <= now < c["session_expires_at"], "Owner must create and authorize a new session")
    check("OWNER_PROOF_POLICY_NOT_APPROVED", c["environment"] == "LOCAL_TEST" or c["proof_policy"]["owner_approved"],
          "Owner must approve the economic policy")
    check("REGISTRY_NOT_ALLOWED", c["adapter_allowed"] and all(c["token_allowlist"].values()), "Owner must review token and adapter allowlists")
    check("ACTION_LIMIT", c["authority"]["actions"] < c["authority"]["max_actions"], "Owner must review session capacity")
    check("ORACLE_REFRESH_REQUIRED", c["oracle_valid_until"] - now >= 90, "Wait for a fresh verified Chainlink round; policy is unchanged")
    check("PENDING_RECONCILIATION", not workflows.store.pending(), "Resume the existing request; do not submit another payment")
    check("RELAYER_GAS_LOW", int(c["relayer_avax_wei"]) >= min(10**15, int(c["max_tx_fee_wei"])), "Fund the existing Relayer AVAX wallet")
    check("GAS_DAILY_LIMIT", int(c["gas_spent_or_reserved_wei"]) < execution.chain.settings.max_daily_gas_expense_wei,
          "Wait for the UTC daily reset or review unresolved reservations")
    base = [x["code"] for x in checks if not x["ready"]]
    operations = []
    for direction, amount, reverse in (("USDC_TO_WAVAX", 1, False), ("WAVAX_TO_USDC", 10**15, True)):
        blocked = list(base)
        if not c["authority"]["operation_mask"] & 1:
            blocked.append("SWAP_NOT_AUTHORIZED")
        if int(c["balances"][1 if reverse else 0]) < amount:
            blocked.append("INSUFFICIENT_TREASURY_BALANCE")
        if int(c["swap_spend_remaining"]) <= 0 or int(c["daily_swap_remaining"]) <= 0:
            blocked.append("SWAP_SPENDING_LIMIT")
        quote = None
        if c["nominal_prices"]:
            try:
                quote = execution.preview_swap(amount, c, reverse=reverse)
            except Exception as error:
                blocked.append(reason(error))
        operations.append({"operation": "SWAP_EXACT_IN", "direction": direction, "amount": str(amount),
                           "ready": not blocked, "reasons": blocked, "quote": quote})
    blocked = list(base)
    amount = 10000  # 0.01 USDC: useful for repeated judged demos without draining treasury.
    payees = [p for p in c["recipient_allowlist"] if min(int(p["per_payment"]), int(p["per_session"]) - int(p["session_spent"]),
                int(p["per_day"]) - int(p["daily_spent"])) >= amount]
    if not c["authority"]["operation_mask"] & 2:
        blocked.append("PAYMENT_NOT_AUTHORIZED")
    if not payees:
        blocked.append("PAYEE_LIMIT_OR_UNAVAILABLE")
    if min(int(c["max_payment_usdc"]), int(c["payment_spend_remaining_usdc"]),
           int(c["daily_payment_remaining_usdc"]), int(c["balances"][0])) < amount:
        blocked.append("PAYMENT_SPENDING_OR_BALANCE_LIMIT")
    operations.append({"operation": "USDC_PAYMENT", "amount": str(amount), "ready": not blocked,
                       "reasons": blocked, "recipient": payees[0]["recipient"] if payees else None})
    return {"ready": any(o["ready"] for o in operations), "environment": c["environment"],
            "observed_at": now, "block_number": c["block_number"], "valid_until": min(
                c["oracle_valid_until"], c["session_expires_at"], c["policy_expires_at"]),
            "session_expires_at": c["session_expires_at"], "policy_expires_at": c["policy_expires_at"],
            "checks": checks, "operations": operations, "recheck_seconds": 20,
            "scope": "Readiness only; each submission still runs the complete security pipeline"}
