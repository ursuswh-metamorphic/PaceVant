"""Shared A/B DTOs, hashing and authenticated B client. Contains no signing key."""

from .models import (
    TransactionProposal,
    BuiltTransaction,
    SimulationEvidence,
    SignedPDR,
    Approval,
    Domain,
    ExecutionResult,
    ExecutionRequest,
    SimulationRequest,
    ChainContext,
    OnchainSnapshot,
    ExecutionSubmission,
    ErrorEnvelope,
    ApprovalChainState,
    ExecutionReconciliation,
)

__version__ = "1.3.0"

__all__ = [
    "TransactionProposal",
    "BuiltTransaction",
    "SimulationEvidence",
    "SignedPDR",
    "Approval",
    "Domain",
    "ExecutionResult",
    "ExecutionRequest",
    "SimulationRequest",
    "ChainContext",
    "OnchainSnapshot",
    "ExecutionSubmission",
    "ErrorEnvelope",
    "ApprovalChainState",
    "ExecutionReconciliation",
]
