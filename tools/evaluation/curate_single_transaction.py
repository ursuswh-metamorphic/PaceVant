"""Independent source curation and reference rules. Does not import evaluated security modules."""

import argparse
import collections
import csv
import hashlib
import json
import random
import re
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

COMMIT = "37bd0f345efb166e3cebc6839e75481e57ce3c90"
DATASET = "https://github.com/duanyiyao/intent-tx-18k"
ROUTER = "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
QUOTAS = {
    "ACCEPT": 100,
    "TOKEN_AMOUNT_DIRECTION": 70,
    "MIN_OUTPUT_DEADLINE_SLIPPAGE": 60,
    "RECIPIENT": 30,
    "TECHNICAL": 40,
}
D = Decimal


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def source_id(row):
    return row.get("sample_id", row.get("test_id"))


def nodes(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [value.get("node_id", value.get("label", "UNKNOWN"))]
    if isinstance(value, list):
        return [n for v in value for n in nodes(v)]
    raise ValueError("Unknown source failure-node shape")


def parse_intent(text):
    if not text.rstrip().endswith((".", "!", "?")):
        raise ValueError("incomplete_or_truncated_intent")
    if re.search(
        r"around|about|roughly|approx|hoping|MEV|broadcast|privat|some slippage|as soon", text, re.I
    ):
        raise ValueError("ambiguous_amount_or_external_execution_condition")
    pair = re.search(
        r"\$([\d,]+(?:\.\d+)?)\s+(?:(?:worth\s+)?of\s+)?([A-Z][A-Z0-9]{0,12})\b.*?\b(?:for|into|to)\s+(?:some\s+)?([A-Z][A-Z0-9]{0,12})\b",
        text,
    )
    slip = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    duration = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?(hours?|hrs?|hr|minutes?|mins?)\b", text, re.I)
    if duration:
        seconds = int(
            D(duration[1]) * (3600 if duration[2].lower().startswith(("h", "hr")) else 60)
        )
    elif re.search(r"\b(?:an|one|next|within the|within an) hour\b", text, re.I):
        seconds = 3600
    else:
        raise ValueError("unresolved_deadline")
    if not pair or not slip:
        raise ValueError("unresolved_token_pair_or_slippage")
    minimum = re.search(
        r"(?:minimum(?:\s+(?:return|receipt|receive|of|received))*|at least|no less than)\s*([\d,]+(?:\.\d+)?)\s+([A-Z][A-Z0-9]{0,12})\b",
        text,
    )
    # A dangling minimum qualifier cannot be silently dropped.
    if re.search(r"minimum|at least|no less than", text, re.I) and not minimum:
        raise ValueError("unresolved_minimum_output")
    return {
        "usd": pair[1].replace(",", ""),
        "input_symbol": pair[2],
        "output_symbol": pair[3],
        "slippage_percent": slip[1],
        "duration_seconds": seconds,
        "minimum_output": minimum[1].replace(",", "") if minimum else None,
        "minimum_symbol": minimum[2] if minimum else None,
    }


def reference(case):
    """Ground truth uses only parsed intent, exact call and declared benchmark context."""
    intent, tx, ctx = (
        case["intent_constraints"],
        case["curated_transaction"],
        case["required_context"],
    )
    p = tx["call"]["params"]
    errors = []
    uint_fields = ["amountOutMin", "deadline"] + (
        [] if tx["call"]["function"] == "swapExactETHForTokens" else ["amountIn"]
    )
    if any(
        not re.fullmatch(r"[0-9]+", str(p.get(k, ""))) or not 0 <= int(p[k]) < 2**256
        for k in uint_fields
    ):
        errors.append(("TECHNICAL", "ABI_INTEGER_RANGE_OR_TYPE"))
    if tx.get("style") != tx["call"]["function"]:
        errors.append(("TECHNICAL", "FUNCTION_DECLARATION_MISMATCH"))
    path = p.get("path", [])
    function = tx["call"]["function"]
    actual_in = ctx["input_asset"]
    actual_out = ctx["output_asset"]
    if len(path) != 2 or [str(a).lower() for a in path] != [
        actual_in["address"].lower(),
        actual_out["address"].lower(),
    ]:
        errors.append(("TOKEN_AMOUNT_DIRECTION", "PATH_DECLARATION_MISMATCH"))
    if (
        ctx["requested_input_address"].lower() != actual_in["address"].lower()
        or ctx["requested_output_address"].lower() != actual_out["address"].lower()
    ):
        errors.append(("TOKEN_AMOUNT_DIRECTION", "INTENT_TOKEN_MISMATCH"))
    amount = int(
        tx["value_base_units"] if function == "swapExactETHForTokens" else p.get("amountIn", "0")
    )
    if amount <= 0 or abs(
        D(amount) / D(10 ** actual_in["decimals"]) * D(ctx["input_price_usd"]) - D(intent["usd"])
    ) > D("0.01"):
        errors.append(("TOKEN_AMOUNT_DIRECTION", "INTENT_AMOUNT_MISMATCH"))
    output = int(p.get("amountOutMin", "0"))
    if intent["minimum_output"] is not None:
        if intent["minimum_symbol"] != intent["output_symbol"] or D(output) / D(
            10 ** actual_out["decimals"]
        ) < D(intent["minimum_output"]):
            errors.append(("MIN_OUTPUT_DEADLINE_SLIPPAGE", "MINIMUM_OUTPUT_BELOW_INTENT"))
    threshold = D(ctx["reference_quote_base_units"]) * (1 - D(intent["slippage_percent"]) / 100)
    if output <= 0 or D(output) < threshold:
        errors.append(("MIN_OUTPUT_DEADLINE_SLIPPAGE", "SLIPPAGE_BOUND"))
    deadline = int(p.get("deadline", 0))
    if (
        not ctx["reference_timestamp"]
        < deadline
        <= ctx["reference_timestamp"] + intent["duration_seconds"]
    ):
        errors.append(("MIN_OUTPUT_DEADLINE_SLIPPAGE", "DEADLINE_BOUND"))
    recipient = p.get("to")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", str(recipient)) or int(recipient, 16) == 0:
        errors.append(("RECIPIENT", "INVALID_RECIPIENT"))
    if (
        tx["chain_id"] != 1
        or tx["call"]["router"].lower() != ROUTER
        or function
        not in {"swapExactTokensForTokens", "swapExactETHForTokens", "swapExactTokensForETH"}
    ):
        errors.append(("TECHNICAL", "PROTOCOL_FUNCTION_ROUTER"))
    if (
        function == "swapExactETHForTokens"
        and actual_in["address"].lower() != WETH
        or function == "swapExactTokensForETH"
        and actual_out["address"].lower() != WETH
    ):
        errors.append(("TECHNICAL", "NATIVE_WRAPPER_INCOMPATIBLE"))
    return errors


def curate(row, registry):
    tx = row["proposed_tx"]
    parsed = parse_intent(row["human_intent"])
    ins, outs = tx["tokens"]["input"], tx["tokens"]["output"]
    if ins.get("synthetic") or outs.get("synthetic"):
        raise ValueError("synthetic_or_unresolved_token")
    for asset in (ins, outs):
        if (
            not re.fullmatch(r"0x[0-9a-fA-F]{40}", asset["address"])
            or not 0 <= asset["decimals"] <= 18
        ):
            raise ValueError("invalid_token_identity")
    if parsed["input_symbol"] not in registry or parsed["output_symbol"] not in registry:
        raise ValueError("ambiguous_requested_token_identity")
    prices = {k.upper(): str(v) for k, v in row["metadata"]["prices_usd"].items()}
    if ins["symbol"].upper() not in prices or outs["symbol"].upper() not in prices:
        raise ValueError("missing_source_price_observation")
    price_in, price_out = D(prices[ins["symbol"].upper()]), D(prices[outs["symbol"].upper()])
    if min(price_in, price_out) <= 0:
        raise ValueError("invalid_source_price_observation")
    normalized = json.loads(json.dumps(tx))
    normalized["style"] = normalized["call"]["function"]
    amount = (
        int(D(str(tx["amountIn_human"])) * D(10 ** ins["decimals"]))
        if tx["call"]["function"] == "swapExactETHForTokens"
        else int(tx["call"]["params"].get("amountIn", "0"))
    )
    normalized["value_base_units"] = str(
        amount if tx["call"]["function"] == "swapExactETHForTokens" else 0
    )
    quote = int(
        (
            D(amount) / D(10 ** ins["decimals"]) * price_in / price_out * D(10 ** outs["decimals"])
        ).to_integral_value(rounding=ROUND_DOWN)
    )
    ctx = {
        "input_asset": ins,
        "output_asset": outs,
        "requested_input_address": registry[parsed["input_symbol"]],
        "requested_output_address": registry[parsed["output_symbol"]],
        "input_price_usd": str(price_in),
        "output_price_usd": str(price_out),
        "reference_timestamp": int(row["metadata"]["generated_at"]),
        "reference_quote_base_units": str(quote),
        "quote_provenance": "SYNTHETIC_STATIC_PRICE_RATIO_FIXTURE",
        "quote_definition": "floor(actual input units * supplied input USD price / supplied output USD price). No fees or impact. This benchmark reference is not an observed AMM execution quote.",
        "amount_rounding_usd": "0.01",
        "price_provenance": "Unverified source metadata, fixed as benchmark inputs",
        "history": [],
        "execution_supported": False,
    }
    # Explicit context adaptation is applied before computing labels, identically for every row.
    intent = (
        row["human_intent"]
        + " For this offline benchmark, use the supplied fixed reference prices and "
        "static reference quote for USD sizing and slippage; USD sizing is compared within one cent. "
        "The supplied reference_timestamp is the time basis for this request."
    )
    case = {
        "source_dataset": DATASET,
        "source_sample_id": source_id(row),
        "original_sample": row,
        "curated_intent": intent,
        "intent_constraints": parsed,
        "curated_transaction": normalized,
        "operation_type": "SWAP",
        "protocol": "Uniswap V2",
        "required_context": ctx,
        "audit_status": "MODIFY",
        "modifications": [
            "Add explicitly synthetic static reference quote and one-cent USD display comparison",
            "Normalize native call value from source amountIn_human when needed",
            "Normalize redundant style descriptor to the actual call function; retain the original descriptor in original_sample",
            "Preserve exact call parameters and source label",
        ],
        "modification_rationale": "Source lacks executable pool quote. A uniform declared fixture supplies an objective slippage reference without using source labels or predictions.",
        "provenance_type": "SOURCE_TRANSACTION_WITH_ADAPTED_SYNTHETIC_CONTEXT",
        "validation_status": "DETERMINISTIC_REFERENCE_VALIDATED",
        "original_label": row["label"],
        "execution_eligibility": "UNSUPPORTED_EXECUTION",
        "review_status": "RULE_VERIFIED_NOT_INDEPENDENT_HUMAN",
        "source_group": row["metadata"]["tx_hash"],
    }
    errors = reference(case)
    case.update(
        expected_decision="REJECT" if errors else "ACCEPT",
        expected_violation_type=errors[0][0] if errors else "NONE",
        expected_failure_reason=errors[0][1]
        if errors
        else "All modeled alignment constraints satisfied",
        all_reference_violations=[{"type": a, "reason": b} for a, b in errors],
        technical_validity="INVALID"
        if any(a in {"TECHNICAL", "RECIPIENT"} for a, b in errors)
        else "STATIC_FIELDS_VALID",
        semantic_alignment="MISALIGNED"
        if any(a not in {"TECHNICAL", "RECIPIENT"} for a, b in errors)
        else "NO_MODELED_DEVIATION",
    )
    return case


def descriptor(case):
    return {
        "id": case["source_sample_id"],
        "group": case["source_group"],
        "category": case["expected_violation_type"]
        if case["expected_decision"] == "REJECT"
        else "ACCEPT",
        "meaning": digest(
            [
                case["intent_constraints"],
                case["required_context"]["input_asset"]["address"],
                case["required_context"]["output_asset"]["address"],
                case["curated_transaction"]["amountIn_human"],
            ]
        ),
    }


def select_descriptors(descriptors, seed):
    pool = sorted(descriptors, key=lambda r: r["id"])
    random.Random(seed).shuffle(pool)
    chosen = []
    groups = set()
    meanings = set()
    counts = collections.Counter()
    for family, target in QUOTAS.items():
        for item in pool:
            if (
                item["category"] != family
                or counts[family] >= target
                or item["group"] in groups
                or item["meaning"] in meanings
            ):
                continue
            chosen.append(item)
            groups.add(item["group"])
            meanings.add(item["meaning"])
            counts[family] += 1
    for item in pool:
        if len(chosen) >= 300:
            break
        if item["group"] in groups or item["meaning"] in meanings:
            continue
        chosen.append(item)
        groups.add(item["group"])
        meanings.add(item["meaning"])
        counts[item["category"]] += 1
    return chosen, counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seed", type=int, default=20261121)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = {}
    stats = {}
    checksums = {}
    for f in sorted(args.dataset_dir.glob("*.json")):
        rows = json.loads(f.read_bytes())
        source[f.name] = rows
        stats[f.name] = {
            "count": len(rows),
            "operations": dict(
                collections.Counter(r["proposed_tx"].get("operation") for r in rows)
            ),
            "labels": dict(collections.Counter(r["label"] for r in rows)),
            "failure_families": dict(
                collections.Counter(
                    str(nodes(r.get("reason", {}).get("failed_validation_node"))) for r in rows
                )
            ),
        }
        checksums[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    swaps = source["eg_uniswap_samples.json"]
    identities = collections.defaultdict(set)
    for r in swaps:
        for symbol, token in r["metadata"]["resolved_tokens"].items():
            if not token.get("synthetic"):
                identities[symbol.upper()].add(token["address"].lower())
    registry = {k: next(iter(v)) for k, v in identities.items() if len(v) == 1}
    registry["WETH"] = WETH
    registry["ETH"] = WETH
    eligible = []
    audit = []
    reasons = collections.Counter()
    for filename, rows in source.items():
        for row in rows:
            sid = source_id(row)
            if filename != "eg_uniswap_samples.json":
                reason = "Non-router transaction: lending or off-chain settlement order"
                audit.append(dict(source_id=sid, status="EXCLUDE", reason=reason, selected=False))
                continue
            try:
                case = curate(row, registry)
                eligible.append(case)
                audit.append(
                    dict(
                        source_id=sid,
                        status="MODIFY",
                        reason=case["modification_rationale"],
                        selected=False,
                    )
                )
            except (ValueError, KeyError, TypeError, ArithmeticError) as error:
                reason = str(error)
                reasons[reason] += 1
                audit.append(dict(source_id=sid, status="EXCLUDE", reason=reason, selected=False))
    candidate_pool = [descriptor(c) for c in eligible]
    selections, counts = select_descriptors(candidate_pool, args.seed)
    by_id = {c["source_sample_id"]: c for c in eligible}
    chosen = [by_id[d["id"]] for d in selections]
    selected_ids = {c["source_sample_id"] for c in chosen}
    for i, c in enumerate(chosen):
        c["benchmark_id"] = f"single_tx_{i + 1:03d}"
        c["split"] = (
            "development" if int(digest(c["source_group"])[:8], 16) % 5 == 0 else "held_out"
        )
    raw_by_id = {source_id(r): (name, r) for name, rows in source.items() for r in rows}
    selected_by_id = {c["source_sample_id"]: c for c in chosen}
    for row in audit:
        row["selected"] = row["source_id"] in selected_ids
        filename, original = raw_by_id[row["source_id"]]
        row["source_file"] = "dataset/" + filename
        row["original_label"] = original["label"]
        selected = selected_by_id.get(row["source_id"])
        row["curated_label"] = selected["expected_decision"] if selected else ""
        row["curated_reason"] = selected["expected_failure_reason"] if selected else ""
    with (args.output / "benchmark_300_curated.jsonl").open("x", encoding="utf8") as out:
        for c in chosen:
            out.write(json.dumps(c, ensure_ascii=True, separators=(",", ":")) + "\n")
    with (args.output / "benchmark_300_audit.csv").open("x", encoding="utf8", newline="") as out:
        writer = csv.DictWriter(
            out,
            fieldnames=[
                "source_id",
                "status",
                "reason",
                "selected",
                "source_file",
                "original_label",
                "curated_label",
                "curated_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(audit)
    provenance = {
        "dataset": DATASET,
        "commit": COMMIT,
        "license": "MIT",
        "seed": args.seed,
        "source_checksums_sha256": checksums,
        "git_blob_sha256_lf": {
            name: hashlib.sha256(
                (args.dataset_dir / name).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            for name in checksums
        },
        "curated_raw_sha256": hashlib.sha256(
            (args.output / "benchmark_300_curated.jsonl").read_bytes()
        ).hexdigest(),
        "curated_lf_sha256": hashlib.sha256(
            (args.output / "benchmark_300_curated.jsonl").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "statistics": stats,
        "previous_selection": "No previous 300-sample manifest or selected corpus existed in this checkout",
        "target_quotas": QUOTAS,
        "actual_quotas": dict(counts),
        "count": len(chosen),
        "shortfall": 300 - len(chosen),
        "eligible_before_group_dedup": len(eligible),
        "eligible_candidate_pool": candidate_pool,
        "exclusion_reasons": dict(reasons),
        "selected": [
            {
                "id": c["source_sample_id"],
                "source_file": "dataset/eg_uniswap_samples.json",
                "modification_history": {
                    "context": "Added uniformly generated static-price-ratio quote, source-time basis and one-cent USD sizing rule",
                    "style_before": c["original_sample"]["proposed_tx"]["style"],
                    "style_after": c["curated_transaction"]["style"],
                    "native_value_after": c["curated_transaction"]["value_base_units"],
                    "label_before": c["original_label"],
                    "label_after": c["expected_decision"],
                    "label_rationale": c["expected_failure_reason"],
                },
                "original_sample_sha256": digest(c["original_sample"]),
                "benchmark_id": c["benchmark_id"],
                "group": c["source_group"],
                "original_label": c["original_label"],
                "curated_label": c["expected_decision"],
                "split": c["split"],
                "label_changed": c["original_label"]
                != ("PASS" if c["expected_decision"] == "ACCEPT" else "REJECT"),
            }
            for c in chosen
        ],
    }
    (args.output / "benchmark_300_provenance.json").write_text(
        json.dumps(provenance, indent=1) + "\n"
    )
    print(
        json.dumps(
            {
                k: provenance[k]
                for k in (
                    "count",
                    "shortfall",
                    "actual_quotas",
                    "eligible_before_group_dedup",
                    "exclusion_reasons",
                )
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
