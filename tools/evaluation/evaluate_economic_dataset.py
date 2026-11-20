"""Evaluate the frozen corpus against actual risk and Z3 proof functions. No LLM/RPC."""

import hashlib
import json
import statistics
import subprocess
import time
from pathlib import Path

from treasury_backend.modules.risk.operations import assess_operation
from treasury_contracts.crypto import content_hash
from treasury_contracts.proof_v3 import prove_operation
from treasury_contracts.v3 import ZERO, OperationIntent

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "fixtures/evaluation/economic-risk-v1"
OUT = ROOT / "docs/evaluation/economic-risk-v1"
U, W, V, P = ("0x" + n * 40 for n in ("1", "2", "3", "4"))


def adapt(x):
    """Transport flat observations into the real risk/proof API; no gold is read."""
    payment = x["operation"] == "payment"
    now = 1800000000
    intent = OperationIntent(
        operation="TOKEN_PAYMENT" if payment else "TOKEN_SWAP",
        chain_id=43113,
        treasury=V,
        session_id="0x" + "a" * 64,
        token_in=U,
        token_out=U if payment else W,
        recipient=P if payment else V,
        amount=str(x["amount"]),
        min_output=str(x["minimum"]),
        deadline=now + x["ttl"],
        objective="Synthetic economic specification evaluation",
        slippage_bps=40,
    )
    build = {
        "intent": intent.model_dump(mode="json"),
        "operation": {"intentHash": intent.hash},
        "min_output": str(x["minimum"]),
    }
    before = [str(x["cash"]), str(x["wavax"]), "0", "0"]
    effects = dict(
        source="LOCAL_FORK_EVM" if x["verified"] else "UNVERIFIED",
        environment="SYNTHETIC_EVALUATION",
        execution_status="SUCCESS",
        build_hash=content_hash(build),
        before=before,
        deltas=[str(-x["amount"]), str(0 if payment else x["output"]), str(-x["extra_debit"]), "0"],
        received=str(x["received"] if payment else 0),
        gas_used=100000,
        allowances=[str(x["allowance"]), "0"],
        source_block_hash="0x" + "b" * 64,
    )
    prices = [[str(lo), str(hi)] for lo, hi in x["prices"]]
    policy = dict(
        tolerance_bps=x["tolerance"],
        max_relative_loss_bps=x["loss_bps"],
        fixed_loss_usd_e8=x["fixed_loss"],
        max_oracle_age=300,
    )
    context = dict(
        mvp=True,
        usdc=U,
        wavax=W,
        shares=ZERO,
        balances=before,
        block_hash=effects["source_block_hash"],
        timestamp=now - x["age"],
        oracle_valid_until=now + 300 - x["age"],
        oracle={"source": "SYNTHETIC_SPEC_REFERENCE"},
        proof_policy=policy,
        share_unit="1",
        share_rate="1000000",
        share_rate_low="1000000",
        share_rate_high="1000000",
        price_intervals=[prices[0], prices[1], prices[0], prices[1]],
        risk_remaining=str(x["session_risk"]),
        global_risk_remaining=str(x["global_risk"]),
        spend_remaining=str(x["session_spend"]),
        daily_spend_remaining=str(x["daily_spend"]),
        max_operation_usd_e8=str(x["trade_limit"]),
        payment_spend_remaining_usdc=str(x["session_payment"]),
        daily_payment_remaining_usdc=str(x["daily_payment"]),
        max_payment_usdc=str(x["payment_limit"]),
        swap_spend_remaining=str(x["swap_session"]),
        daily_swap_remaining=str(x["swap_daily"]),
        max_wavax_exposure_bps=x["exposure_bps"],
        max_gas_price_wei="1",
        max_tx_fee_wei="1000000",
        gas_spent_or_reserved_wei="0",
        max_daily_execution_cost_usd_e8="1000000000000000000",
    )
    return intent, build, effects, context, now


def predict(x):
    try:
        intent, build, effects, context, now = adapt(x)
        risk = assess_operation(intent, build, effects, context, now)
        if risk["result"] != "PASS":
            return "REJECT", ",".join(risk["reason_codes"])
        proof = prove_operation(intent, build, effects, context)
        return ("APPROVE" if proof["status"] == "VERIFIED" else "REJECT"), proof["status"]
    except ValueError as error:
        return "REJECT", str(error)
    # Unexpected exceptions are errors, not credited as correct rejections.


def metrics(rows):
    tp = sum(r["gold"] == "REJECT" and r["prediction"] == "REJECT" for r in rows)
    tn = sum(r["gold"] == "APPROVE" and r["prediction"] == "APPROVE" for r in rows)
    fp = sum(r["gold"] == "APPROVE" and r["prediction"] == "REJECT" for r in rows)
    fn = sum(r["gold"] == "REJECT" and r["prediction"] == "APPROVE" for r in rows)
    errors = sum(r["prediction"] == "ERROR" for r in rows)
    def div(a, b):
        return a / b if b else None
    f1_reject = div(2 * tp, 2 * tp + fp + fn + errors)
    f1_approve = div(2 * tn, 2 * tn + fp + fn + errors)
    return dict(
        n=len(rows),
        accuracy=div(tp + tn, len(rows)),
        precision=div(tp, tp + fp),
        recall=div(tp, tp + fn + errors),
        f1=f1_reject,
        macro_f1=(f1_reject + f1_approve) / 2
        if f1_reject is not None and f1_approve is not None
        else None,
        confusion_matrix=dict(
            true_reject=tp, true_approve=tn, false_rejection=fp, false_approval=fn, errors=errors
        ),
        false_approval_rate=div(fn, fn + tp),
        false_rejection_rate=div(fp, fp + tn),
        latency_ms=dict(
            median=statistics.median(r["latency_ms"] for r in rows),
            p95=sorted(r["latency_ms"] for r in rows)[int(0.95 * (len(rows) - 1))],
        ),
    )


def main():
    manifest = json.loads((FOLDER / "manifest.json").read_text())
    raw = (FOLDER / "dataset.jsonl").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"], "Dataset changed after freeze"
    rows = list(map(json.loads, raw.decode().splitlines()))
    results = []
    assert len({r["id"] for r in rows}) == len(rows)
    assert not (
        {r["group_id"] for r in rows if r["split"] == "development"}
        & {r["group_id"] for r in rows if r["split"] == "test"}
    )
    for row in rows:
        start = time.perf_counter()
        try:
            prediction, reason = predict(row["input"])
        except Exception as error:
            prediction, reason = "ERROR", type(error).__name__
        results.append(
            {k: row[k] for k in ("id", "family", "split", "gold")}
            | dict(
                prediction=prediction,
                reason=reason,
                latency_ms=round((time.perf_counter() - start) * 1000, 3),
            )
        )
    test = [r for r in results if r["split"] == "test"]
    report = dict(
        dataset_sha256=manifest["sha256"],
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        .decode()
        .strip(),
        scope="Synthetic offline economic admissibility: actual assess_operation + prove_operation; no RPC, simulation, signing or receipt acceptance",
        positive_class="REJECT",
        overall=metrics(results),
        development=metrics([r for r in results if r["split"] == "development"]),
        test=metrics(test),
        per_family={
            f: metrics([r for r in test if r["family"] == f]) for f in manifest["families"]
        },
        source_sha256={
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in [
                "backend/src/treasury_backend/modules/risk/operations.py",
                "packages/contracts-api/treasury_contracts/proof_v3.py",
                "tools/evaluation/economic_oracle.py",
                "tools/evaluation/build_economic_dataset.py",
                "tools/evaluation/evaluate_economic_dataset.py",
            ]
        },
        limitations=[
            "Synthetic specification conformance, not real-world predictive accuracy",
            "Same author/team; no independent human annotation",
            "Only USDC-input swap and USDC payment; no reverse swap or other protocols",
            "Assumes trusted measured effects and bounded price intervals; does not evaluate oracle integrity",
            "No tuning or claim about held-out real-world data",
        ],
    )
    report["baselines"] = {
        name: metrics([{**r, "prediction": value} for r in test])
        for name, value in [("always_approve", "APPROVE"), ("always_reject", "REJECT")]
    }
    n = len(test)
    p = report["test"]["accuracy"]
    z = 1.96
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    radius = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    report["test_accuracy_wilson95"] = [center - radius, center + radius]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "predictions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in results), encoding="utf-8", newline="\n"
    )
    (OUT / "metrics.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (OUT / "errors.json").write_text(
        json.dumps([r for r in results if r["prediction"] != r["gold"]], indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"test": report["test"], "all": report["overall"]}))


if __name__ == "__main__":
    main()
