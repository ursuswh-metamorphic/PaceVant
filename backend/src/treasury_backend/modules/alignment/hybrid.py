"""Source-anchored intent constraints, transaction adapters, binding and strict fusion.

No benchmark labels, model scores, external text or candidate token symbols grant authority.
The bounded grammar is deliberately conservative; unsupported interpretations need clarification.
"""

import re
from decimal import Decimal, InvalidOperation, localcontext

from treasury_backend.modules.alignment.hybrid_types import (
    Constraint,
    ConstraintResult,
    IntentEnvelope,
    TaskBinding,
)

ADDRESS = r"0x[0-9a-fA-F]{40}"
ASSET = rf"(?:{ADDRESS}|[A-Z][A-Z0-9]{{1,11}})"
NUMBER = r"[0-9]+(?:\.[0-9]+)?"
UNISWAP_V2 = "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


def extract_constraints(text, instructions, revision):
    """Anchor constraints to raw authenticated text, never LLM-rewritten permissions.

    LLM decomposition supplies task references/semantic objectives; this interpretation
    ceiling is computed from the entire source message, retaining unresolved conditions.
    """
    envelope = IntentEnvelope(
        task_id=instructions[0].instruction_id,
        task_ids=[i.instruction_id for i in instructions],
        source_message_id=instructions[0].source_message_id,
        revision=revision,
        original_text=text,
        operation="UNRESOLVED",
        constraints=[],
    )

    def add(kind, value, span, unit="", op="EQ", ambiguity=None):
        envelope.constraints.append(
            Constraint(
                constraint_id=f"{envelope.source_message_id}:{len(envelope.constraints)}",
                kind=kind,
                operator="UNKNOWN" if ambiguity else op,
                value=str(value),
                unit=unit,
                source_message_id=envelope.source_message_id,
                task_id=envelope.task_id,
                revision=revision,
                source_span=span,
                ambiguity=ambiguity,
            )
        )

    # Parse symbols with case preserved. Case-insensitive verbs cannot turn prose into assets.
    lower = text.lower()
    if re.search(r"\b(swap|buy|sell|trade|exchange)\b|\b(mua|bán|đổi)\b", lower):
        envelope = envelope.model_copy(update={"operation": "SWAP"})
    elif re.search(r"\b(transfer|send|pay)\b|\b(chuyển|gửi|trả)\b", lower):
        envelope = envelope.model_copy(update={"operation": "TRANSFER"})
    else:
        envelope.unresolved.append("UNRESOLVED_OPERATION")
    add(
        "OPERATION",
        envelope.operation,
        text,
        ambiguity="UNRESOLVED_OPERATION" if envelope.operation == "UNRESOLVED" else None,
    )
    if re.search(r"\b(approximately|about|around|roughly|unless|except|between|only if)\b", lower):
        envelope.unresolved.append("AMBIGUOUS_OR_CONDITIONAL_AUTHORIZATION")
    if re.search(r"\b(do not|don't|must not|never|not permitted|không)\b", lower):
        envelope.unresolved.append("NEGATED_AUTHORIZATION_REQUIRES_CLARIFICATION")
    if re.search(r"slippage[^%]{0,65}-\s*[0-9]", lower):
        envelope.unresolved.append("INVALID_NEGATIVE_SLIPPAGE_REQUIREMENT")
    pair = re.search(
        rf"(?i:swap|trade|exchange)\s+(?:(?i:exactly|up to|at most|no more than)\s+)?"
        rf"(?P<usd>\$)?(?P<amount>{NUMBER})\s+(?:(?i:worth of|of)\s+)?"
        rf"(?P<input>{ASSET})\s+(?i:for|to|into)\s+(?P<output>{ASSET})",
        text,
    )
    buy = re.search(rf"(?i:buy|mua)\s+({ASSET})\s+(?i:with|bằng)\s+({NUMBER})\s+({ASSET})", text)
    sell = re.search(rf"(?i:sell|bán)\s+({NUMBER})\s+({ASSET})\s+(?i:for|lấy)\s+({ASSET})", text)
    transfer = re.search(
        rf"(?i:transfer|send|pay|chuyển|gửi)\s+(?:(?i:exactly|up to|at most|no more than)\s+)?({NUMBER})\s+({ASSET})",
        text,
    )
    amount_span = pair[0] if pair else transfer[0] if transfer else ""
    bound = (
        "LE"
        if re.search(r"\b(up to|at most|no more than)\s+\$?" + NUMBER, amount_span.lower())
        else "EQ"
    )
    if pair:
        add("TOKEN_IN", pair["input"], pair[0])
        add("TOKEN_OUT", pair["output"], pair[0])
        add("AMOUNT", pair["amount"], pair[0], "USD" if pair["usd"] else "TOKEN", bound)
    elif buy:
        add("TOKEN_IN", buy[3], buy[0])
        add("TOKEN_OUT", buy[1], buy[0])
        add("AMOUNT", buy[2], buy[0], "TOKEN", bound)
    elif sell:
        add("TOKEN_IN", sell[2], sell[0])
        add("TOKEN_OUT", sell[3], sell[0])
        add("AMOUNT", sell[1], sell[0], "TOKEN", bound)
    elif transfer and envelope.operation == "TRANSFER":
        add("TOKEN_IN", transfer[2], transfer[0])
        add("AMOUNT", transfer[1], transfer[0], "TOKEN", bound)
        add("TRANSFER_TYPE", "NATIVE" if re.search(r"\bnative\b", lower) else "ERC20", text)
    else:
        envelope.unresolved.append("MISSING_EXPLICIT_ASSET_OR_AMOUNT")
    recipient = re.search(
        rf"(?i:recipient|destination|to address|to|đến)\s*[:=]?\s*({ADDRESS})", text
    )
    if recipient:
        add("RECIPIENT", recipient[1].lower(), recipient[0])
    elif envelope.operation == "TRANSFER":
        envelope.unresolved.append("MISSING_EXPLICIT_RECIPIENT")
    chain = re.search(r"(?i:chain(?: id)?|network)\s*[:=]?\s*([0-9]+)", text)
    network = next(
        (
            v
            for k, v in {"fuji": 43113, "anvil": 31337, "ethereum": 1}.items()
            if re.search(r"\b" + k + r"\b", lower)
        ),
        None,
    )
    if chain or network:
        add("CHAIN", chain[1] if chain else network, chain[0] if chain else text)
    router = re.search(rf"(?i:router)\s*[:=]?\s*({ADDRESS})", text)
    if router:
        add("ROUTER", router[1].lower(), router[0])
    if "uniswap" in lower:
        add("PROTOCOL", "Uniswap V2", text)
    slip = re.search(rf"(?i:slippage)[^%,.;]{{0,65}}?({NUMBER})\s*%", text)
    if not slip:
        slip = re.search(rf"({NUMBER})\s*%\s+(?i:slippage)", text)
    if slip:
        add("SLIPPAGE", slip[1], slip[0], "PERCENT", "LE")
    elif "slippage" in lower:
        envelope.unresolved.append("UNRESOLVED_SLIPPAGE")
    minimum = re.search(
        rf"(?i:minimum|min|at least|no less than)\s*(?i:output|receipt|return|receive)?\s*(?i:of)?\s*[:=]?\s*({NUMBER})\s+({ASSET})",
        text,
    )
    if minimum:
        add("MIN_OUTPUT", minimum[1], minimum[0], minimum[2], "GE")
    elif re.search(r"\b(minimum|min|at least|no less than)\b", lower):
        envelope.unresolved.append("UNRESOLVED_MINIMUM_OUTPUT")
    duration = re.search(
        r"\b([0-9]+|one|an?|two)\s*[- ]?\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b", lower
    )
    absolute = re.search(r"(?i:deadline|before)\s*[:=]?\s*([0-9]{9,})\b", text)
    if absolute:
        add("DEADLINE", absolute[1], absolute[0], "UNIX_SECONDS", "LE")
    elif duration:
        count = {"one": 1, "a": 1, "an": 1, "two": 2}.get(duration[1])
        count = count if count is not None else int(duration[1])
        seconds = count * (
            3600 if duration[2].startswith(("h",)) else 60 if duration[2].startswith("m") else 1
        )
        add("DEADLINE", seconds, duration[0], "DURATION_SECONDS", "LE")
    elif re.search(r"deadline|within|before|complete in", lower.replace("within one cent", "")):
        envelope.unresolved.append("UNRESOLVED_DEADLINE")
    return envelope


def uint(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("ABI_UINT")
    result = int(value)
    if not 0 <= result < 2**256:
        raise ValueError("ABI_UINT")
    return result


def normalize(arguments, schema):
    """Decode only registered shapes. Candidate display fields never set decimals/identity."""
    tx = dict(arguments)
    if schema.get('fixed_operations') and 'operation' in tx and tx['operation'] not in schema.get('operations', []):
        raise ValueError('UNSUPPORTED_FIXED_OPERATION')
    if schema.get('fixed_operations') and tx.get('operation') in schema.get('operations', []):
        result = dict(operation={'TOKEN_SWAP':'SWAP','TOKEN_PAYMENT':'TRANSFER'}.get(tx['operation'],tx['operation']),
            chain_id=uint(tx.get('chain_id')), token_in=tx.get('token_in'), token_out=tx.get('token_out'),
            amount=uint(tx.get('amount')), minimum=uint(tx.get('min_output','0')),
            deadline=uint(tx.get('deadline')), recipient=tx.get('recipient'),
            router=tx.get('router',tx.get('adapter',schema.get('configured_adapter'))),
            sender=tx.get('treasury'), native=False, protocol=None,
            slippage_bps=uint(tx.get('slippage_bps',0)))
        for field in ('token_in','token_out','recipient','router','sender'):
            if not re.fullmatch(ADDRESS,str(result[field])) or int(result[field],16)==0:
                raise ValueError('ABI_ADDRESS_'+field.upper())
            result[field]=result[field].lower()
        return result
    if "build" in tx and isinstance(tx["build"], dict):
        build = tx["build"]
        # Built transactions are decoded data, not a new authorization source. Exact
        # calldata, signature and decision linkage remain independently revalidated.
        tx = {**build, "action": "SWAP_EXACT_INPUT", "recipient": build.get("vault_address")}
    if "proposal" in tx and isinstance(tx["proposal"], dict):
        tx = tx["proposal"]
    if "call" in tx:
        call = tx["call"]
        p, function = call.get("params", {}), call.get("function")
        if function not in {
            "swapExactTokensForTokens",
            "swapExactETHForTokens",
            "swapExactTokensForETH",
        }:
            raise ValueError("UNSUPPORTED_ABI_FUNCTION")
        path = p.get("path", [])
        if len(path) != 2 or not all(re.fullmatch(ADDRESS, str(a)) for a in path):
            raise ValueError("ABI_PATH")
        value = uint(tx.get("value_base_units", "0"))
        if function != "swapExactETHForTokens" and value:
            raise ValueError("UNEXPECTED_NATIVE_VALUE")
        if (
            function == "swapExactETHForTokens"
            and path[0].lower() != WETH
            or function == "swapExactTokensForETH"
            and path[-1].lower() != WETH
        ):
            raise ValueError("NATIVE_WRAPPER_FUNCTION")
        tx = dict(
            operation="SWAP",
            chain_id=uint(tx.get("chain_id")),
            token_in=path[0],
            token_out=path[-1],
            amount=uint(value if function == "swapExactETHForTokens" else p.get("amountIn")),
            minimum=uint(p.get("amountOutMin")),
            deadline=uint(p.get("deadline")),
            recipient=p.get("to"),
            router=call.get("router"),
            protocol=tx.get("protocol"),
            sender=None,
            native=function == "swapExactETHForTokens",
        )
        if schema.get("protocol") == "Uniswap V2" and (
            tx["chain_id"] != 1 or str(tx["router"]).lower() != UNISWAP_V2
        ):
            raise ValueError("PROTOCOL_ROUTER_CHAIN")
    elif tx.get("action") in {"SWAP_EXACT_INPUT", "TRANSFER_ERC20", "TRANSFER_NATIVE"}:
        action = tx["action"]
        task_id, task_revision = tx.get("task_id"), tx.get("revision")
        tx = dict(
            operation="SWAP" if action == "SWAP_EXACT_INPUT" else "TRANSFER",
            chain_id=uint(tx.get("chain_id")),
            token_in=tx.get("token_in", tx.get("token")),
            token_out=tx.get("token_out"),
            amount=uint(tx.get("amount_in_base_units", tx.get("amount_base_units"))),
            minimum=uint(tx["min_amount_out_base_units"])
            if "min_amount_out_base_units" in tx
            else None,
            deadline=uint(tx.get("deadline")),
            recipient=tx.get("recipient"),
            router=tx.get("router"),
            sender=tx.get("vault_address"),
            protocol=None,
            slippage_bps=uint(tx["slippage_bps"]) if "slippage_bps" in tx else None,
            native=action == "TRANSFER_NATIVE",
            task_id=task_id,
            task_revision=task_revision,
        )
    else:
        return None
    for field in ("token_in", "recipient") + (
        ("token_out", "router") if tx["operation"] == "SWAP" else ()
    ):
        if not re.fullmatch(ADDRESS, str(tx.get(field))) or int(tx[field], 16) == 0:
            raise ValueError("ABI_ADDRESS_" + field.upper())
        tx[field] = tx[field].lower()
    if tx["amount"] <= 0:
        raise ValueError("NONPOSITIVE_AMOUNT")
    return tx


def verify(intent, tx, schema, now, action_ref):
    results = []
    refs = [action_ref, intent.source_message_id]

    def result(c, status, observed, code="CONSTRAINT_SATISFIED", boundary="USER_INTENT"):
        results.append(
            ConstraintResult(
                constraint_id=c.constraint_id,
                constraint_type=c.kind,
                boundary=boundary,
                expected=f"{c.operator} {c.value} {c.unit}".strip(),
                observed=str(observed) if observed is not None else None,
                status=status,
                violation_code=code,
                evidence_refs=refs,
                explanation=f"{c.kind}: {status}; source span: {c.source_span[:350]}",
            )
        )

    assets = schema.get("assets", [])
    context = (
        schema.get("fixed_benchmark_context", {})
        if schema.get("authority") == "OFFLINE_BENCHMARK_INPUT_ONLY"
        else schema.get("verified_context", {})
    )
    by_address = {str(a.get("address", "")).lower(): a for a in assets}

    def token_match(symbol, actual):
        if re.fullmatch(ADDRESS, symbol):
            return symbol.lower() == str(actual).lower()
        aliases = {"ETH": "WETH"} if tx["chain_id"] == 1 else {}
        matches = [
            a
            for a in assets
            if aliases.get(str(a.get("symbol")), str(a.get("symbol")))
            == aliases.get(symbol, symbol)
        ]
        if len(matches) == 1:
            return matches[0]["address"].lower() == actual
        # A known actual token with a different authenticated metadata symbol proves mismatch.
        known = by_address.get(actual)
        if known and aliases.get(known.get("symbol"), known.get("symbol")) != aliases.get(
            symbol, symbol
        ):
            return False
        return None

    for c in intent.constraints:
        observed, passed = None, None
        try:
            with localcontext() as precision:
                precision.prec = 160
                if c.operator == "UNKNOWN":
                    pass
                elif c.kind == "OPERATION":
                    observed = tx["operation"]
                    passed = observed == c.value
                elif c.kind in {"TOKEN_IN", "TOKEN_OUT"}:
                    observed = tx.get(c.kind.lower())
                    passed = token_match(c.value, observed)
                elif c.kind == "AMOUNT":
                    asset = by_address.get(tx["token_in"])
                    if (
                        asset
                        and isinstance(asset.get("decimals"), int)
                        and 0 <= asset["decimals"] <= 36
                    ):
                        observed = Decimal(tx["amount"]) / Decimal(10 ** asset["decimals"])
                        tolerance = Decimal(0)
                        if c.unit == "USD":
                            price = context.get("input_price_usd")
                            if price is None or Decimal(str(price)) <= 0:
                                raise ValueError("MISSING_VALUATION")
                            observed *= Decimal(str(price))
                            # Tolerance is enabled only by the authenticated original text AND a fixed declared context.
                            if (
                                "within one cent" in intent.original_text.lower()
                                and str(context.get("amount_rounding_usd")) == "0.01"
                            ):
                                tolerance = Decimal("0.01")
                        expected = Decimal(c.value)
                        passed = (
                            abs(observed - expected) <= tolerance
                            if c.operator == "EQ"
                            else observed <= expected + tolerance
                        )
                elif c.kind == "AMOUNT_BASE_UNITS":
                    observed = tx["amount"]
                    passed = (
                        observed == int(c.value) if c.operator == "EQ" else observed <= int(c.value)
                    )
                elif c.kind == "MIN_AMOUNT_BASE_UNITS":
                    observed = tx["amount"]
                    passed = observed >= int(c.value)
                elif c.kind == 'MIN_OUTPUT_BASE_UNITS':
                    observed = tx.get('minimum')
                    passed = observed is not None and observed >= int(c.value)
                elif c.kind == 'SLIPPAGE_BPS':
                    observed = tx.get('slippage_bps')
                    passed = observed is not None and observed <= int(c.value)
                elif c.kind == "MIN_OUTPUT":
                    asset = by_address.get(tx.get("token_out"))
                    identity = token_match(c.unit, tx.get("token_out"))
                    if identity is False:
                        passed = False
                    elif asset and identity and tx.get("minimum") is not None:
                        observed = Decimal(tx["minimum"]) / Decimal(10 ** asset["decimals"])
                        passed = observed >= Decimal(c.value)
                elif c.kind == "SLIPPAGE":
                    quote = context.get("reference_quote_base_units")
                    if (
                        quote is not None
                        and tx.get("minimum") is not None
                        and Decimal(str(quote)) > 0
                    ):
                        observed = tx["minimum"]
                        passed = Decimal(observed) >= Decimal(str(quote)) * (
                            1 - Decimal(c.value) / 100
                        )
                    elif tx.get("slippage_bps") is not None:
                        observed = Decimal(tx["slippage_bps"]) / 100
                        passed = observed <= Decimal(c.value)
                elif c.kind == "DEADLINE":
                    reference = context.get("reference_timestamp", now)
                    maximum = (
                        int(c.value) + reference if c.unit == "DURATION_SECONDS" else int(c.value)
                    )
                    observed = tx["deadline"]
                    passed = now < observed <= maximum
                elif c.kind == "RECIPIENT":
                    observed = tx["recipient"]
                    passed = observed == c.value.lower()
                elif c.kind == "CHAIN":
                    observed = tx["chain_id"]
                    passed = observed == int(c.value)
                elif c.kind == "TASK_ID":
                    observed = tx.get("task_id")
                    passed = observed == c.value
                elif c.kind == "TASK_REVISION":
                    observed = tx.get("task_revision")
                    passed = observed == int(c.value)
                elif c.kind == "TRANSFER_TYPE":
                    observed = "NATIVE" if tx.get("native") else "ERC20"
                    passed = observed == c.value
                elif c.kind == "ROUTER":
                    observed = tx.get("router")
                    passed = observed == c.value.lower()
                elif c.kind == "PROTOCOL":
                    observed = tx.get("protocol")
                    passed = observed == c.value
        except (ValueError, TypeError, InvalidOperation, KeyError, OverflowError):
            passed = None
        result(
            c,
            "UNKNOWN" if passed is None else "PASS" if passed else "FAIL",
            observed,
            "MISSING_CRITICAL_EVIDENCE"
            if passed is None
            else "CONSTRAINT_SATISFIED"
            if passed
            else "INTENT_" + c.kind + "_VIOLATION",
        )
    technical = Constraint(
        constraint_id="technical",
        kind="ABI",
        operator="EQ",
        value="VALID",
        unit="",
        source_message_id=intent.source_message_id,
        task_id=intent.task_id,
        revision=intent.revision,
        source_span="Canonical transaction fields",
    )
    result(
        technical,
        "PASS" if tx["deadline"] > now else "FAIL",
        tx["deadline"],
        "CONSTRAINT_SATISFIED" if tx["deadline"] > now else "EXPIRED_DEADLINE",
        "TECHNICAL",
    )
    # Mandate metadata is a separate technical scope, never a substitute for user amount/recipient intent.
    scope_ok = tx["chain_id"] == schema.get("chain_id")
    if schema.get('fixed_operations'):
        scope_ok = scope_ok and str(tx.get('sender')).lower() == str(schema.get('vault')).lower()
    if schema.get("vault"):
        if tx["operation"] == "TRANSFER":
            scope_ok = scope_ok and str(tx.get("sender")).lower() == schema["vault"].lower()
        else:
            scope_ok = (
                scope_ok
                and tx["recipient"] == schema["vault"].lower()
                and tx["router"] == schema["configured_adapter"].lower()
            )
    scope = technical.model_copy(update={"constraint_id": "metadata", "kind": "SCOPE"})
    result(
        scope,
        "PASS" if scope_ok else "FAIL",
        tx["chain_id"],
        "CONSTRAINT_SATISFIED" if scope_ok else "METADATA_SCOPE_MISMATCH",
        "METADATA",
    )
    for index, reason in enumerate(intent.unresolved):
        unresolved = technical.model_copy(
            update={"constraint_id": f"unresolved:{index}", "kind": "UNRESOLVED", "value": reason}
        )
        result(unresolved, "UNKNOWN", None, reason)
    if tx["operation"] == "TRANSFER" and tx.get("native"):
        result(
            technical.model_copy(update={"constraint_id": "native-call", "kind": "TRANSFER_TYPE"}),
            "UNKNOWN",
            "NATIVE",
            "NATIVE_EXECUTION_ADAPTER_NOT_REGISTERED",
            "TECHNICAL",
        )
    return results


def bind(intents, tx, schema, now, action_ref, revision, requested_task=None):
    candidates = [i for i in intents if not requested_task or requested_task in i.task_ids]
    # An unrelated read-only/undeclared operation is not a competing financial
    # authorization. It must not force ambiguity when a concrete SWAP/TRANSFER
    # objective uniquely authorizes the action. Unknown scopes alone never approve.
    resolved = [i for i in candidates if i.operation == tx["operation"]]
    if resolved:
        candidates = resolved
    evaluated = [(i, verify(i, tx, schema, now, action_ref)) for i in candidates]
    possible = [(i, r) for i, r in evaluated if not any(c.status == "FAIL" for c in r)]
    if len(possible) == 1:
        chosen = possible[0]
    elif not possible and len(evaluated) == 1:
        chosen = evaluated[0]
    else:
        return TaskBinding(
            revision=revision,
            action_ref=action_ref,
            verdict="AMBIGUOUS" if possible else "UNAUTHORIZED",
            explanation="No unique authenticated action scope; clarification required.",
        ), []
    intent, checks = chosen
    return TaskBinding(
        task_id=intent.task_id,
        source_message_id=intent.source_message_id,
        revision=revision,
        action_ref=action_ref,
        verdict="VALID",
        evidence_refs=[intent.source_message_id, action_ref],
        explanation="Unique active authenticated message scope; all its constraints retained.",
        authorization_ref=intent.authorization_ref,
    ), checks


def fuse(binding, checks, findings):
    if any(c.status == "FAIL" for c in checks) or binding.verdict == "UNAUTHORIZED":
        return "MISALIGNED"
    if binding.verdict != "VALID" or any(c.status == "UNKNOWN" for c in checks):
        return "UNCERTAIN"
    if any(f.verdict == "MISALIGNED" for f in findings):
        return "MISALIGNED"
    if not findings or any(f.verdict != "ALIGNED" for f in findings):
        return "UNCERTAIN"
    return "ALIGNED"
