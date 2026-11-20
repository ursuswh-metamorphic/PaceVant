"""Export only local Anvil demo decisions from the two-authorized-swaps pytest fixture."""

import argparse
import json
import sqlite3
from pathlib import Path

from treasury_backend.core.domain import EconomicRiskAssessment
from treasury_backend.core.models import Alignment, ChainContext, Mandate
from treasury_backend.modules.alignment import check
from treasury_backend.modules.decision import decide
from treasury_backend.modules.temporal.explainer import explain
from treasury_backend.modules.temporal.models import Graph, HybridTemporalAssessment
from treasury_contracts.models import BuiltTransaction, SimulationEvidence, TransactionProposal
from treasury_contracts.v2 import ProofArtifactV2


def compare_proven_candidate(data, assessment, goal):
    """Shadow only. Require a complete recorded financial proof, risk and simulation."""
    if (data.get("proof") or {}).get("status") != "VERIFIED" or data["risk"]["result"] != "PASS":
        return None
    mandate = Mandate.model_validate(data["mandate"])
    proposal = TransactionProposal.model_validate(data["proposal"])
    wallet = check(mandate, proposal, goal)
    shield = Alignment.model_validate(data["alignment"])
    temporal = assessment.model_copy(
        update={
            "verdict": assessment.deterministic.verdict,
            "reason_codes": [v.code for v in assessment.deterministic.violations],
        }
    )
    evidence = dict(
        built=BuiltTransaction.model_validate(data["build"]),
        evidence=SimulationEvidence.model_validate(data["simulation"]),
        risk=EconomicRiskAssessment.model_validate(data["risk"]),
        proof=ProofArtifactV2.model_validate(data["proof"]),
        provenance_issues=[
            c for c in data["decision"]["reason_codes"] if not c.startswith("ITAG_")
        ],
    )
    context = ChainContext.model_validate(data["chain_context"])
    variants = {
        "wallet": (wallet, None),
        "shield": (shield, None),
        "temporal": (wallet, temporal),
        "shield_temporal": (shield, temporal),
        "hybrid": (shield, assessment),
    }
    outcomes = {
        key: decide(
            mandate,
            proposal,
            aligned,
            context,
            data["decision"]["created_at"],
            temporal=gate,
            **evidence,
        ).verdict
        for key, (aligned, gate) in variants.items()
    }
    if outcomes["hybrid"] != data["decision"]["verdict"]:
        raise ValueError("Shadow full hybrid disagrees with the archived decision")
    return outcomes


def export(path):
    rows = []
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for workflow, candidate, body in db.execute(
            "SELECT workflow_id,intent_id,body FROM decisions ORDER BY rowid"
        ):
            data = json.loads(body)
            if data["mode"] != "LOCAL" or data["proposal"]["chain_id"] != 31337:
                raise ValueError("Expected a LOCAL Anvil test database")
            a, g = db.execute(
                "SELECT body,graph FROM itag_assessments WHERE candidate_id=?", (candidate,)
            ).fetchone()
            assessment = HybridTemporalAssessment.model_validate_json(a)
            graph = Graph.model_validate_json(g)
            if assessment.semantic.provider_metadata.get("scope") != "SCRIPTED_ITAG_REPLAY":
                raise ValueError("Expected a scripted assessment")
            events = [
                (s, t, json.loads(b))
                for s, t, b in db.execute(
                    "SELECT stage,created_at,body FROM events WHERE workflow_id=? ORDER BY sequence",
                    (workflow,),
                )
            ]
            outcome = db.execute(
                "SELECT body FROM outcome_projections WHERE decision_id=?",
                (data["decision"]["decision_id"],),
            ).fetchone()
            projection = json.loads(outcome[0]) if outcome else {}
            # Bound the export to public test identifiers and evaluated evidence. No PDR bytes or credentials.
            goals = [
                n.data["content"]
                for n in graph.nodes
                if n.trust == "AUTHENTICATED"
                and n.kind == "AUTHENTICATED_USER_INTENT"
                and n.data.get("role") == "USER"
            ]
            if len(goals) != 1:
                raise ValueError("Expected one authenticated workflow goal in this fixture")
            goal = goals[0]
            rows.append(
                {
                    "workflow": workflow,
                    "shadow_sde": compare_proven_candidate(data, assessment, goal),
                    "sde": data["decision"]["verdict"],
                    "sde_reason_codes": data["decision"]["reason_codes"],
                    "risk": data["risk"]["result"],
                    "proof": (data.get("proof") or {}).get("status"),
                    "candidate": data["proposal"],
                    "graph_hash": assessment.graph_hash,
                    "graph": graph.model_dump(mode="json"),
                    "explanation": explain(assessment, graph).model_dump(mode="json"),
                    "timings_ms": [
                        body["timing_ms"] for stage, _, body in events if stage == "ITAG_ASSESSED"
                    ],
                    "stages": [{"stage": s, "unix_seconds": t} for s, t, _ in events],
                    "signed": any(s == "ATTESTED" for s, _, _ in events),
                    "receipt": {
                        k: v
                        for k, v in (projection.get("receipt") or {}).items()
                        if k in {"tx_hash", "block_number", "block_hash", "gas_used", "status"}
                    },
                    "outcome": projection.get("state"),
                    "task_shield": data["task_shield_proof"],
                }
            )
    return {
        "source": "LOCAL_ANVIL_SCRIPTED_MODEL",
        "chain_id": 31337,
        "public_broadcasts": 0,
        "rows": rows,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("database", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    report = export(args.database)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=1)
        stream.write("\n")
