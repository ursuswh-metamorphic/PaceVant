"""Trusted builders derive all targets and function selectors from the fixed registry."""

import time
from fractions import Fraction

from web3 import Web3

from treasury_contracts.crypto import content_hash
from treasury_contracts.v3 import KINDS, ZERO, ZERO_HASH, Operation, call_hash


def build_operation(chain, store, intent, context, *, on_check=None):
    m, c = chain.manifest, context
    if c.get("mvp"):
        if intent.operation not in {"TOKEN_SWAP", "TOKEN_PAYMENT"}:
            raise ValueError("MVP_UNSUPPORTED_OPERATION")
        if intent.operation == "TOKEN_PAYMENT" and (intent.token_in != m.usdc or intent.token_out != m.usdc):
            raise ValueError("MVP_CIRCLE_USDC_PAYMENT_REQUIRED")
    if (intent.chain_id, intent.treasury, intent.session_id) != (m.chain_id, m.treasury, c["session_id"]):
        raise ValueError("CHAIN_OR_TREASURY_MISMATCH")
    now = max(int(time.time()), c["timestamp"])
    if c.get("mvp") and intent.deadline>c["oracle_valid_until"]:
        raise ValueError("ORACLE_WINDOW_UNAVAILABLE")
    if not now < intent.deadline <= min(c["timestamp"] + c["max_ttl"], c["policy_expires_at"], c["session_expires_at"]):
        raise ValueError("EXPIRED_APPROVAL")
    if intent.slippage_bps > c["max_slippage_bps"]:
        raise ValueError("SLIPPAGE_LIMIT")
    mask = c["authority"]["operation_mask"]
    if not mask & (1 << (KINDS[intent.operation] - 1)) or intent.rebalance and not mask & 16:
        raise ValueError("OPERATION_NOT_AUTHORIZED")
    if on_check:
        on_check("BUILDER_SCOPE", "PASS", expected={"chain_id": m.chain_id, "treasury": m.treasury, "session_id": c["session_id"], "max_slippage_bps": c["max_slippage_bps"]},
                 observed={"chain_id": intent.chain_id, "treasury": intent.treasury, "session_id": intent.session_id, "operation_mask": mask, "slippage_bps": intent.slippage_bps, "deadline": intent.deadline})
    n, amount = c["block_number"], int(intent.amount)
    def read(name, *args):
        return getattr(chain.vault.functions, name)(*args).call(block_identifier=n)
    registry = [m.usdc, m.wavax, m.shares, ZERO]
    if intent.token_in not in registry or intent.token_out not in registry:
        raise ValueError("TOKEN_NOT_ALLOWED")
    if amount > int(c["balances"][registry.index(intent.token_in)]):
        raise ValueError("INSUFFICIENT_BALANCE")
    route = None
    if intent.operation == "TOKEN_SWAP":
        if {intent.token_in, intent.token_out} != {m.usdc, m.wavax} or intent.recipient != m.treasury:
            raise ValueError("ROUTE_NOT_ALLOWED")
        target = m.adapter
        if not read("allowedRouters", Web3.to_checksum_address(target)):
            raise ValueError("ADAPTER_NOT_ALLOWED")
        cap = read("maxPerSwap") if intent.token_in == m.usdc else int(c["proof_policy"]["max_wavax_per_swap"])
        if amount > cap:
            raise ValueError("TRADE_SIZE_LIMIT")
        quote = chain.adapter.functions.quote(Web3.to_checksum_address(intent.token_in),
                                               Web3.to_checksum_address(intent.token_out), amount).call(block_identifier=n)
        if m.environment in {"LOCAL_FORK", "ANVIL_FORK", "REAL_FUJI_EXECUTION"}:
            from treasury_backend.modules.execution.dex.lfj import LFJClient
            dex=LFJClient(chain.w3,m.usdc)
            route = dex.v1_route(n)
            verified=dex.verified_quote(amount,n,route,reverse=intent.token_in==m.wavax)
            if int(verified["amount_out_base_units"])!=quote or verified["block_hash"]!=c["block_hash"]:
                raise ValueError("LFJ_QUOTER_MISMATCH")
            route={**route,"verified_quoter":{k:v for k,v in verified.items() if k!="route"}}
            if chain.adapter.functions.pair().call(block_identifier=n).lower() != route["pair"].lower():
                raise ValueError("LFJ_ROUTE_MISMATCH")
            r0, r1 = map(int, route["reserves"])
            ri, ro = (r0, r1) if route["token0"].lower() == intent.token_in else (r1, r0)
            independent = amount * 997 * ro // (ri * 1000 + amount * 997)
            if quote != independent:
                raise ValueError("LFJ_QUOTE_MISMATCH")
            if amount * 997 * 10000 > m.max_price_impact_bps * (ri * 1000 + amount * 997):
                raise ValueError("PRICE_IMPACT_LIMIT")
            if on_check:
                on_check("LFJ_QUOTE", "PASS", expected={"quote": str(independent), "max_price_impact_bps": m.max_price_impact_bps},
                         observed={"quote": str(quote), "price_impact_bps": round(amount*997*10000/(ri*1000+amount*997), 6), "pair": route["pair"], "source_block": n})
        units = [10**6, 10**18]
        i, j = registry.index(intent.token_in), registry.index(intent.token_out)
        fair = Fraction(amount * int(c["nominal_prices"][i]) * units[j], units[i] * int(c["nominal_prices"][j]))
        # Independent oracle deviation gate; economic-loss proof is an additional gate.
        max_loss = c["proof_policy"]["max_relative_loss_bps"]
        if quote * 10000 < fair * (10000 - max_loss):
            raise ValueError("ORACLE_PRICE_DEVIATION")
        if on_check:
            protected = fair * (10000 - max_loss) / 10000
            on_check("INDEPENDENT_ORACLE_QUOTE", "PASS", expected={"min_output": str((protected.numerator+protected.denominator-1)//protected.denominator), "max_relative_loss_bps": max_loss},
                     observed={"quote": str(quote), "oracle_valid_until": c.get("oracle_valid_until"), "source_block": n})
    elif intent.operation == "TOKEN_PAYMENT":
        if intent.token_in not in {m.usdc, m.wavax, ZERO} or intent.token_out != intent.token_in:
            raise ValueError("TOKEN_NOT_ALLOWED")
        recipient = Web3.to_checksum_address(intent.recipient)
        if intent.recipient in {ZERO, m.treasury} or chain.w3.eth.get_code(recipient, n):
            raise ValueError("PAYEE_NOT_ALLOWED")
        per_tx, per_day = read("payees", Web3.to_checksum_address(intent.token_in), recipient)
        if not per_tx or amount > per_tx:
            raise ValueError("PAYEE_NOT_ALLOWED")
        from eth_abi import encode
        key = Web3.keccak(encode(["uint256", "address", "address"], [c["timestamp"] // 86400, intent.token_in, intent.recipient]))
        payee_daily_spent = read("payeeDailySpent", key)
        if payee_daily_spent + amount > per_day:
            raise ValueError("PAYEE_DAILY_LIMIT")
        if on_check:
            on_check("PAYMENT_ALLOWLIST", "PASS", expected={"per_payment": str(per_tx), "per_day": str(per_day)},
                     observed={"recipient": intent.recipient, "amount": str(amount), "daily_spent": str(payee_daily_spent)})
        quote, target = amount, intent.recipient if intent.token_in == ZERO else intent.token_in
    else:
        deposit = intent.operation == "VAULT_DEPOSIT"
        if ((intent.token_in, intent.token_out) != ((m.usdc, m.shares) if deposit else (m.shares, m.usdc))
                or intent.recipient != m.treasury):
            raise ValueError("VAULT_IDENTITY_MISMATCH")
        target = m.shares
        cap = read("maxVaultAssets" if deposit else "maxVaultShares")
        maximum = (chain.shares.functions.maxDeposit(chain.vault.address) if deposit else
                   chain.shares.functions.maxRedeem(chain.vault.address)).call(block_identifier=n)
        if amount > min(cap, maximum):
            raise ValueError("VAULT_PAUSED_OR_ILLIQUID")
        quote = (chain.shares.functions.previewDeposit(amount) if deposit else
                 chain.shares.functions.previewRedeem(amount)).call(block_identifier=n)
    for token in (intent.token_in, intent.token_out):
        if token in {m.usdc, m.wavax} and not read("allowedTokens", Web3.to_checksum_address(token)):
            raise ValueError("TOKEN_NOT_ALLOWED")
    minimum = max(int(intent.min_output), quote if intent.operation == "TOKEN_PAYMENT" else
                  quote * (10000 - intent.slippage_bps) // 10000)
    if minimum <= 0 or minimum > quote:
        raise ValueError("INVALID_MINIMUM_OUTPUT")
    nonce = store.nonce(f"v3:{m.chain_id}:{m.treasury}")
    while read("usedNonce", int(nonce)):
        nonce = store.nonce(f"v3:{m.chain_id}:{m.treasury}")
    args = {"kind": KINDS[intent.operation], "rebalance": intent.rebalance, "policyHash": c["policy_hash"],
            "sessionId": intent.session_id, "intentHash": intent.hash, "evidenceRoot": ZERO_HASH,
            "proofContextHash": ZERO_HASH, "constraintsHash": ZERO_HASH, "calldataHash": ZERO_HASH,
            "target": target, "tokenIn": intent.token_in, "tokenOut": intent.token_out, "recipient": intent.recipient,
            "amount": intent.amount, "minOutput": str(minimum), "spendDebitUsdE8": "1", "riskDebitUsdE8": "0",
            "nonce": nonce, "deadline": str(intent.deadline)}
    operation = Operation.model_validate(args)
    call_target, value, data = chain.vault.functions.operationCall(operation.abi_tuple).call(block_identifier=n)
    calldata = Web3.to_hex(data)
    result = {"intent": intent.model_dump(mode="json"), "operation": args | {"calldataHash": call_hash(call_target, value, calldata)},
              "call": {"target": call_target.lower(), "value": str(value), "data": calldata},
              "min_output": str(minimum), "quote": str(quote), "route": route, "context_hash": content_hash(c)}
    result["build_id"] = "v3_" + content_hash(result)[2:]
    store.put("v3-build", result["build_id"], result)
    store.put("v3-context", result["build_id"], c)
    return result
