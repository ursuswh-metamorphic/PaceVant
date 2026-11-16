import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps" / "control-plane"), str(ROOT / "packages" / "contracts-api")]


def main():
    from pydantic import TypeAdapter, ValidationError

    from app.domain import Id
    from app.errors import ControlError
    from app.orchestration.service import ControlPlane
    from app.settings import Settings
    from treasury_contracts.models import Hash

    parser = argparse.ArgumentParser(description="Recover a workflow from a B execution receipt.")
    parser.add_argument("workflow_id")
    parser.add_argument("tx_hash")
    args = parser.parse_args()
    try:
        workflow_id = TypeAdapter(Id).validate_python(args.workflow_id)
        tx_hash = TypeAdapter(Hash).validate_python(args.tx_hash)
    except ValidationError:
        parser.error("expected a workflow ID and a lowercase transaction hash")
    settings = Settings.from_env()
    if settings.mode == "MOCK":
        parser.error("receipt recovery requires the B HTTP client in LOCAL or FUJI mode")
    control = ControlPlane(settings)
    try:
        result = control.recover_submission(workflow_id, tx_hash)
        print(json.dumps({"workflow_id": workflow_id, "status": result["status"]}))
    except ControlError as exc:
        parser.exit(1, f"{exc.code}\n")
    finally:
        control.close()


if __name__ == "__main__":
    main()
