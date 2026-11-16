from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


def uint256(value: str) -> str:
    if abs(int(value)) >= 2**256:
        raise ValueError("integer is outside uint256 magnitude")
    return value


UInt = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]{0,77})$"), AfterValidator(uint256)]
Delta = Annotated[
    str, StringConstraints(pattern=r"^(0|-?[1-9][0-9]{0,77})$"), AfterValidator(uint256)
]
Hash = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-f]{64}$")]
Address = Annotated[
    str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$"), AfterValidator(str.lower)
]
Calldata = Annotated[str, StringConstraints(pattern=r"^0x(?:[0-9a-fA-F]{2}){4,4096}$")]
Signature = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{130}$")]
Id = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,100}$")]
ArtifactRef = Annotated[
    str,
    StringConstraints(
        pattern=r"^artifact://[a-zA-Z0-9_-]+(/[a-zA-Z0-9_.-]+){1,8}$", max_length=250
    ),
]
Bps = Annotated[int, Field(ge=0, le=10000)]
Counter = Annotated[int, Field(ge=0, le=2**53 - 1)]
Timestamp = Counter
Source = Literal["MOCK_FIXTURE", "REAL_LOCAL_SIM", "FORK_SIM"]
Verdict = Literal["APPROVE", "REPLAN", "REJECT", "ESCALATE"]
ExecutionStatus = Literal[
    "SUBMITTED",
    "PENDING",
    "CONFIRMED",
    "REVERTED",
    "FAILED_TO_SUBMIT",
    "STALE_REQUIRES_REEVALUATION",
]


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class TransactionProposal(Wire):
    intent_id: Id
    mandate_id: Id
    mandate_version: Annotated[int, Field(gt=0)]
    action: Literal["SWAP_EXACT_INPUT"]
    chain_id: Literal[43113]
    vault_address: Address
    router: Address
    token_in: Address
    token_out: Address
    amount_in_base_units: UInt
    slippage_bps: Bps
    recipient: Address
    deadline: Timestamp
    user_goal_reason: Annotated[str, StringConstraints(min_length=1, max_length=250)]


class BuiltTransaction(Wire):
    build_id: Id
    intent_id: Id
    chain_id: Literal[43113]
    vault_address: Address
    router: Address
    token_in: Address
    token_out: Address
    amount_in_base_units: UInt
    min_amount_out_base_units: UInt
    router_calldata: Calldata
    calldata_hash: Hash
    policy_hash: Hash
    nonce: UInt
    deadline: Timestamp
    quote_ref: Id
    adapter_version: Id


class Baseline(Wire):
    execution_status: Literal["SUCCESS", "REVERTED", "INCONCLUSIVE"]
    token_in_delta_base_units: Delta
    token_out_delta_base_units: Delta
    unexpected_transfer: bool
    unauthorized_approval: bool
    gas_used: UInt


class StressTest(Wire):
    scenario_id: Id
    status: Literal["SUCCESS_SAFE", "PROTECTED_REVERT", "UNSAFE_EXECUTION", "INCONCLUSIVE"]
    output_base_units: UInt | None = None
    revert_reason: Id | None = None


class SimulationEvidence(Wire):
    schema_version: Literal["1.1"]
    intent_id: Id
    build_id: Id
    chain_id: Literal[43113]
    vault_address: Address
    policy_hash: Hash
    calldata_hash: Hash
    nonce: UInt
    deadline: Timestamp
    fork_block: Counter
    bytecode_hash: Hash
    simulation_mode: Id
    baseline: Baseline
    stress_tests: Annotated[list[StressTest], Field(max_length=20)]
    verification_status: Literal["COMPLETE", "INCOMPLETE", "INCONCLUSIVE"]
    parser_version: Id
    source: Source
    artifact_refs: Annotated[list[ArtifactRef], Field(min_length=1, max_length=20)]
    evidence_manifest_ref: ArtifactRef
    evidence_root: Hash


class PortfolioSnapshot(Wire):
    snapshot_id: Id
    chain_id: Literal[43113]
    vault_address: Address
    block_number: Counter
    usdc_base_units: UInt
    wavax_base_units: UInt
    price_usdc_usd_e8: UInt
    price_wavax_usd_e8: UInt
    price_source: Id
    price_timestamp: Timestamp
    history_version: Counter


class EconomicRiskAssessment(Wire):
    intent_id: Id
    build_id: Id
    snapshot_id: Id
    result: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    projected_wavax_exposure_bps: Bps | None
    max_wavax_exposure_bps: Bps
    violations: list[Id]
    calculation_version: Literal["risk-v1"] = "risk-v1"


class SecurityDecision(Wire):
    decision_id: Id
    intent_id: Id
    build_id: Id | None
    verdict: Verdict
    reason_codes: list[Id]
    policy_hash: Hash
    calldata_hash: Hash | None
    simulation_evidence_root: Hash | None
    mandate_version: int
    snapshot_id: Id | None
    created_at: Timestamp
    expires_at: Timestamp
    source: Literal["SDE_V1"] = "SDE_V1"


class Domain(Wire):
    name: Literal["TreasuryPolicyVault"] = "TreasuryPolicyVault"
    version: Literal["1"] = "1"
    chainId: Literal[43113] = 43113
    verifyingContract: Address


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


class SignedPDR(Wire):
    decision_id: Id
    build_id: Id
    domain: Domain
    approval: Approval
    signature: Signature
    typed_data_hash: Hash


class ExecutionResult(Wire):
    build_id: Id
    decision_id: Id
    chain_id: Literal[43113]
    tx_hash: Hash | None
    status: ExecutionStatus
    block_number: Counter | None = None
    gas_used: UInt | None = None
    actual_token_in_delta_base_units: Delta | None = None
    actual_token_out_delta_base_units: Delta | None = None
    revert_reason: Id | None = None
    event_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)


class ExecutionSubmission(Wire):
    tx_hash: Hash | None
    status: ExecutionStatus
