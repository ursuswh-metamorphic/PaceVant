"""Recover a known journaled submission through the running unified backend."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import TypeAdapter

from treasury_backend.core.domain import Id
from treasury_backend.operations.env import read_env
from treasury_backend.paths import ROOT
from treasury_contracts.models import Hash


def recover(api_url, token, workflow_id, tx_hash, *, transport=None):
    url = urlsplit(api_url)
    if (
        not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or not (
            url.scheme == "https"
            or (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost", "::1"})
        )
    ):
        raise ValueError("Use an HTTPS API origin or HTTP loopback, without credentials or path")
    if not token or len(token) < 24:
        raise ValueError("PACEVANT_OPERATOR_TOKEN must contain at least 24 characters")
    workflow_id = TypeAdapter(Id).validate_python(workflow_id)
    tx_hash = TypeAdapter(Hash).validate_python(tx_hash)
    with httpx.Client(
        base_url=api_url.rstrip("/"),
        headers={"Authorization": "Bearer " + token},
        timeout=30,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    ) as client:
        response = client.post(f"/v1/workflows/{workflow_id}/recover", json={"tx_hash": tx_hash})
        response.raise_for_status()
        return {"workflow_id": workflow_id, "status": response.json()["status"]}


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile a known tx hash with a SUBMITTING workflow; never signs or resends."
    )
    parser.add_argument("workflow_id")
    parser.add_argument("tx_hash")
    parser.add_argument(
        "--api-url", help="Unified backend origin; default uses TREASURY_A_PORT on loopback"
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    try:
        values = read_env(args.env_file)
        api_url = args.api_url or f"http://127.0.0.1:{values.get('TREASURY_A_PORT', '8000')}"
        result = recover(
            api_url, values.get("PACEVANT_OPERATOR_TOKEN", ""), args.workflow_id, args.tx_hash
        )
    except (ValueError, KeyError):
        parser.exit(
            1, "Invalid recovery configuration, identifiers or response; no signing attempted\n"
        )
    except httpx.HTTPError:
        # Do not echo service response bodies, tokens or authenticated endpoint URLs.
        parser.exit(
            1,
            "Recovery unavailable/rejected; check backend auth, workflow state and journal binding\n",
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
