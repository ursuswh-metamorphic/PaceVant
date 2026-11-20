"""Hand-check benchmark labels independently of the production evaluator."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "economic_oracle", ROOT / "tools/evaluation/economic_oracle.py"
)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def base():
    return json.loads(
        (ROOT / "fixtures/evaluation/economic-risk-v1/dataset.jsonl").read_text().splitlines()[0]
    )["input"]


def test_hand_calculated_one_dollar_loss_boundary():
    x = base() | dict(
        amount=1000000,
        cash=100000000,
        wavax=0,
        prices=[[100000000, 100000000], [100000000, 100000000]],
        output=970000000000000000,
        minimum=970000000000000000,
        loss_bps=300,
        tolerance=0,
    )
    assert oracle.label(x) == "APPROVE"  # $1 outgoing, exactly $0.03 loss.
    assert (
        oracle.label(x | {"output": 969999999999999999, "minimum": 969999999999999999}) == "REJECT"
    )


def test_hand_calculated_payment_spend_is_separate_from_loss():
    x = base() | dict(
        operation="payment",
        amount=1000000,
        received=1000000,
        minimum=1000000,
        output=0,
        session_risk=0,
        global_risk=0,
    )
    assert oracle.label(x) == "APPROVE"
    assert oracle.label(x | {"session_payment": 999999}) == "REJECT"
    assert oracle.label(x | {"received": 999999}) == "REJECT"


def test_entire_approval_lifetime_fits_oracle_window():
    x = base() | dict(age=240, ttl=60)
    assert oracle.label(x) == "APPROVE"
    assert oracle.label(x | {"age": 241}) == "REJECT"


def test_gold_labels_do_not_import_production_or_solver():
    source = (ROOT / "tools/evaluation/economic_oracle.py").read_text()
    assert "treasury_" not in source and "import z3" not in source
