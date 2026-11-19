from dataclasses import dataclass

from treasury_backend.core.domain import PortfolioSnapshot, SecurityDecision
from treasury_backend.core.models import Alignment, ChainBalances, Mandate
from treasury_contracts.models import BuiltTransaction, SimulationEvidence, TransactionProposal
from treasury_contracts.v2 import ProofArtifactV2


@dataclass(frozen=True)
class ApprovedAttempt:
    workflow_id: str
    decision: SecurityDecision
    mandate: Mandate
    proposal: TransactionProposal
    alignment: Alignment
    built: BuiltTransaction
    evidence: SimulationEvidence
    snapshot: PortfolioSnapshot
    balances: ChainBalances
    proof: ProofArtifactV2 | None = None
