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
)

__version__ = "1.1.0"

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
]
