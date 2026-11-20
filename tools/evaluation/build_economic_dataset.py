"""Freeze a synthetic, implementation-independent economic specification corpus."""

import hashlib
import json
import random
from pathlib import Path

from economic_oracle import label

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = [
    "ordinary_swap",
    "ordinary_payment",
    "loss_boundary",
    "compiled_floor",
    "session_risk",
    "global_risk",
    "swap_spend",
    "payment_caps",
    "receipt_shortfall",
    "exposure",
    "stale_evidence",
    "allowance",
    "unverified_effects",
    "disabled_asset_debit",
    "invalid_price_band",
    "mixed_market",
]


def main():
    rng = random.Random(20261121)
    rows = []
    for family in FAMILIES:
        for index in range(50):
            amount = rng.randint(1, 250) * 10**6 + rng.randint(0, 999999)
            price = rng.choice([2, 7, 20, 80, 150]) * 10**8
            fair = amount * 10**12 * 10**8 // price
            x = dict(
                operation="swap",
                amount=amount,
                cash=amount * rng.randint(20, 200),
                wavax=0,
                output=fair,
                received=amount,
                minimum=fair * 9990 // 10000,
                prices=[[10**8, 10**8], [price, price]],
                loss_bps=300,
                fixed_loss=0,
                tolerance=0,
                session_risk=10**15,
                global_risk=10**15,
                trade_limit=10**15,
                session_spend=10**15,
                daily_spend=10**15,
                swap_session=10**15,
                swap_daily=10**15,
                payment_limit=10**12,
                session_payment=10**12,
                daily_payment=10**12,
                exposure_bps=5000,
                age=10,
                ttl=60,
                verified=True,
                allowance=0,
                extra_debit=0,
            )
            offset = rng.choice([-1, 0, 1])
            if family == "ordinary_payment":
                x.update(operation="payment", minimum=amount, output=0)
            elif family == "loss_boundary":
                x["output"] = fair * 9700 // 10000 + offset
                x["minimum"] = x["output"]
            elif family == "compiled_floor":
                x.update(minimum=0, tolerance=rng.choice([0, 299, 300, 301, 1000]))
            elif family in ("session_risk", "global_risk"):
                x.update(output=fair * 9900 // 10000, minimum=fair * 9900 // 10000)
                loss = (amount * 100 * 10**18 - x["output"] * price + 10**18 - 1) // 10**18
                x[family] = max(0, loss + offset)
            elif family == "swap_spend":
                x[
                    rng.choice(
                        [
                            "trade_limit",
                            "session_spend",
                            "daily_spend",
                            "swap_session",
                            "swap_daily",
                        ]
                    )
                ] = amount * 100 + offset
            elif family == "payment_caps":
                x.update(operation="payment", minimum=amount, output=0)
                x[rng.choice(["payment_limit", "session_payment", "daily_payment"])] = (
                    amount + offset
                )
            elif family == "receipt_shortfall":
                x.update(
                    operation="payment",
                    minimum=amount,
                    received=amount + rng.choice([-1, 0, 1]),
                    output=0,
                )
            elif family == "exposure":
                x.update(cash=amount * 2, exposure_bps=rng.choice([4999, 5000, 5001]))
            elif family == "stale_evidence":
                x["age"] = rng.choice([239, 240, 241, 299, 300, 301, 900])
            elif family == "allowance":
                x["allowance"] = rng.choice([0, 1, 10**18])
            elif family == "unverified_effects":
                x["verified"] = index % 3 == 0
            elif family == "disabled_asset_debit":
                x["extra_debit"] = rng.choice([0, 1, 10**6])
            elif family == "invalid_price_band":
                x["prices"][0] = rng.choice([[0, 10**8], [10**8, 10**8 - 1], [10**8, 10**8]])
            elif family == "mixed_market":
                band = rng.choice([0, 50, 100, 200])
                x["prices"] = [
                    [10**8 * (10000 - band) // 10000, 10**8 * (10000 + band) // 10000],
                    [price * (10000 - band) // 10000, price * (10000 + band) // 10000],
                ]
                x["output"] = fair * rng.randint(9400, 10500) // 10000
                x["minimum"] = x["output"] * rng.randint(9900, 10000) // 10000
                x["loss_bps"] = rng.choice([100, 300, 500])
                x["fixed_loss"] = rng.choice([0, 10**6])
            rows.append(
                dict(
                    id=f"econ-{family}-{index:03}",
                    family=family,
                    group_id=f"{family}-{index}",
                    split="development" if index < 10 else "test",
                    input=x,
                    gold=label(x),
                    provenance="SYNTHETIC_SPECIFICATION_NOT_REAL_TRANSACTION",
                )
            )
    folder = ROOT / "fixtures/evaluation/economic-risk-v1"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "dataset.jsonl"
    path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n"
    )
    metadata = dict(
        version=1,
        seed=20261121,
        rows=len(rows),
        families=FAMILIES,
        development=160,
        test=640,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        positive_class="REJECT",
        labeling="Independent Fraction arithmetic, four price vertices, published economic obligations; no production/Z3 imports",
        independence_limit="Same project specification and author; synthetic corpus, not external peer annotation or field accuracy",
    )
    (folder / "manifest.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
