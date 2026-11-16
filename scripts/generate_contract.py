import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "contracts-api"))

WIRE_MODELS = (
    "TransactionProposal",
    "BuiltTransaction",
    "SimulationEvidence",
    "PortfolioSnapshot",
    "EconomicRiskAssessment",
    "SecurityDecision",
    "SignedPDR",
    "ExecutionResult",
    "ExecutionSubmission",
)


def schema():
    from treasury_contract import wire

    definitions = {}
    for name in WIRE_MODELS:
        model_schema = getattr(wire, name).model_json_schema()
        definitions.update(model_schema.pop("$defs", {}))
        definitions[name] = model_schema
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "AI Treasury Security wire contract v1.1",
        "$defs": definitions,
    }


if __name__ == "__main__":
    target = ROOT / "packages" / "contracts-api" / "schemas" / "v1.1.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(schema(), indent=2) + "\n", encoding="utf-8")
