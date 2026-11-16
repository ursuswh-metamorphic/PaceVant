"""Shared A/B integration contract v1.1. Money crosses the wire as decimal strings."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Address = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]
Hash = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-f]{64}$")]
HexBytes = Annotated[str, StringConstraints(pattern=r"^0x(?:[0-9a-f]{2})*$")]
UInt = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]*)$")]
Delta = Annotated[str, StringConstraints(pattern=r"^-?(0|[1-9][0-9]*)$")]


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @field_validator("*", mode="after")
    @classmethod
    def uint_range(cls, value, info):
        if (
            isinstance(value, str)
            and any(
                getattr(meta, "pattern", None)
                in {r"^(0|[1-9][0-9]*)$", r"^-?(0|[1-9][0-9]*)$"}
                for meta in cls.model_fields[info.field_name].metadata
            )
            and abs(int(value)) >= 2**256
        ):
            raise ValueError("uint256 overflow")
        return value


class TransactionProposal(Wire):
    intent_id: str = Field(min_length=1, max_length=128)
    mandate_id: str = Field(min_length=1, max_length=128)
    mandate_version: int = Field(ge=1)
    action: Literal["SWAP_EXACT_INPUT"]
    chain_id: int = Field(gt=0)
    vault_address: Address
    router: Address
    token_in: Address
    token_out: Address
    amount_in_base_units: UInt
    slippage_bps: int = Field(ge=0, le=10000)
    recipient: Address
    deadline: int = Field(gt=0, le=9007199254740991)
    user_goal_reason: str = Field(max_length=4096)


class BuiltTransaction(Wire):
    build_id: str
    intent_id: str
    chain_id: int
    vault_address: Address
    router: Address
    token_in: Address
    token_out: Address
    amount_in_base_units: UInt
    min_amount_out_base_units: UInt
    router_calldata: HexBytes
    calldata_hash: Hash
    policy_hash: Hash
    nonce: UInt
    deadline: int
    quote_ref: str
    adapter_version: Literal["mock-swap-v1"] = "mock-swap-v1"


class Approval(Wire):
    policyHash: Hash
    evidenceRoot: Hash
    router: Address
    tokenIn: Address
    tokenOut: Address
    amountIn: UInt
    minAmountOut: UInt
    calldataHash: Hash
    nonce: UInt
    deadline: UInt


class Domain(Wire):
    name: Literal["TreasuryPolicyVault"]
    version: Literal["1"]
    chainId: int
    verifyingContract: Address


class SignedPDR(Wire):
    decision_id: str = Field(min_length=1)
    build_id: str
    domain: Domain
    approval: Approval
    signature: Annotated[str, StringConstraints(pattern=r"^0x[0-9a-f]{130}$")]
    typed_data_hash: Hash


class Baseline(Wire):
    execution_status: Literal["SUCCESS", "REVERTED", "INCONCLUSIVE"]
    token_in_delta_base_units: Delta
    token_out_delta_base_units: Delta
    unexpected_transfer: bool
    unauthorized_approval: bool
    gas_used: UInt


class StressTest(Wire):
    scenario_id: str
    status: Literal[
        "SUCCESS_SAFE", "PROTECTED_REVERT", "UNSAFE_EXECUTION", "INCONCLUSIVE"
    ]
    scenario_hash: Hash
    output_base_units: UInt | None = None
    revert_reason: str | None = None


class SimulationEvidence(Wire):
    schema_version: Literal["1.1"] = "1.1"
    intent_id: str
    build_id: str
    chain_id: int
    vault_address: Address
    policy_hash: Hash
    calldata_hash: Hash
    nonce: UInt
    deadline: int
    fork_block: int
    bytecode_hash: Hash
    simulation_mode: Literal["LOCAL_TEST_ATTESTOR"]
    baseline: Baseline
    stress_tests: list[StressTest]
    verification_status: Literal["COMPLETE", "INCOMPLETE", "INCONCLUSIVE"]
    parser_version: Literal["extractor-v1"] = "extractor-v1"
    source: Literal["MOCK_FIXTURE", "REAL_LOCAL_SIM", "FORK_SIM"]
    artifact_refs: list[str]
    evidence_manifest_ref: str
    evidence_root: Hash


class ExecutionResult(Wire):
    build_id: str
    decision_id: str
    chain_id: int
    tx_hash: Hash
    status: Literal[
        "SUBMITTED",
        "PENDING",
        "CONFIRMED",
        "REVERTED",
        "FAILED_TO_SUBMIT",
        "STALE_REQUIRES_REEVALUATION",
    ]
    block_number: int | None = None
    gas_used: UInt | None = None
    actual_token_in_delta_base_units: Delta | None = None
    actual_token_out_delta_base_units: Delta | None = None
    revert_reason: str | None = None
    event_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)


class SimulationRequest(Wire):
    build_id: str
    expected_policy_hash: Hash


class ExecutionRequest(Wire):
    build_id: str
    signed_pdr: SignedPDR


ExecutionStatus = Literal[
    "SUBMITTED",
    "PENDING",
    "CONFIRMED",
    "REVERTED",
    "FAILED_TO_SUBMIT",
    "STALE_REQUIRES_REEVALUATION",
]


class ExecutionSubmission(Wire):
    tx_hash: Hash
    status: ExecutionStatus


class ChainContext(Wire):
    chain_id: int
    vault_address: Address
    router: Address
    token_in: Address
    token_out: Address
    policy_hash: Hash
    policy_active: bool
    policy_version: int
    policy_expires_at: int
    attestor: Address
    owner: Address
    paused: bool
    max_per_swap_base_units: UInt
    max_spend_per_day_base_units: UInt
    max_slippage_bps: int
    max_approval_ttl: int
    block_number: int
    block_hash: Hash
    timestamp: int
    mode: Literal["local", "fuji"]
    supported_action: Literal["SWAP_EXACT_INPUT"]


class OnchainSnapshot(Wire):
    """B's chain facts; A adds trusted prices/history to its PortfolioSnapshot."""

    snapshot_id: str
    chain_id: int
    vault_address: Address
    block_number: int
    block_hash: Hash
    timestamp: int
    policy_hash: Hash
    usdc_base_units: UInt
    wavax_base_units: UInt
    allowance_base_units: UInt
    utc_day: int
    daily_spent_usdc_base_units: UInt
    max_spend_per_day_base_units: UInt
    provenance: Literal["CHAIN_READS_NO_PRICE_OR_EXPOSURE_ASSERTION"]


class ErrorDetail(Wire):
    code: str
    message: str
    retryable: bool
    correlation_id: str


class ErrorEnvelope(Wire):
    error: ErrorDetail


class ApprovalChainState(Wire):
    """Read-only SDK pre-attestation check. Never constitutes an APPROVE decision."""

    chain_id: int
    vault_address: Address
    block_number: int
    block_hash: Hash
    timestamp: int
    policy_hash: Hash
    policy_active: bool
    policy_expires_at: int
    paused: bool
    attestor: Address
    nonce: UInt
    nonce_used: bool
    bytecode_hash: Hash
