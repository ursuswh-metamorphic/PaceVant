"""Evaluation subprocess: run the complete V1 deterministic pre-sign gates.

No key custody/signing. Invoked only by the local ablation harness.
"""

import json
import sys

from treasury_backend.core.domain import PortfolioSnapshot
from treasury_backend.core.models import ChainBalances, ChainContext, Mandate
from treasury_backend.modules.alignment import check
from treasury_backend.modules.decision import decide
from treasury_backend.modules.risk import evaluate
from treasury_backend.modules.workflows.evidence import verify_build
from treasury_contracts.models import BuiltTransaction, SimulationEvidence, TransactionProposal

v = json.load(sys.stdin)
m = Mandate.model_validate(v["mandate"])
p = TransactionProposal.model_validate(v["proposal"])
aligned = check(m, p, v["goal"])
if v.get("alignment_only"):
    print(aligned.model_dump_json())
    sys.exit(0)
b = BuiltTransaction.model_validate(v["build"])
sim = SimulationEvidence.model_validate(v["simulation"])
c = ChainContext.model_validate(v["context"])
snapshot = PortfolioSnapshot.model_validate(v["snapshot"])
balances = ChainBalances.model_validate(v["balances"])
verify_build(m, p, b)
risk = evaluate(m, p, b, sim, snapshot, balances, c, v["now"]).risk
decision = decide(m, p, aligned, c, v["now"], built=b, evidence=sim, risk=risk)
print(
    json.dumps(
        {
            "alignment": aligned.model_dump(),
            "risk": risk.model_dump(),
            "decision": decision.model_dump(),
        }
    )
)
