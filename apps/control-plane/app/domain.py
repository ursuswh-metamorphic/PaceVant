from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints

from treasury_contracts.models import Hash, UInt, Wire

Address = Annotated[
    str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$"), AfterValidator(str.lower)
]
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


class PortfolioSnapshot(Wire):
    snapshot_id: Id
    chain_id: Literal[31337, 43113]
    vault_address: Address
    block_number: Counter
    usdc_base_units: UInt
    wavax_base_units: UInt
    price_usdc_usd_e8: UInt
    price_wavax_usd_e8: UInt
    price_source: Id
    price_timestamp: Timestamp
    history_version: Counter


class AssetObservation(Wire):
    asset_id: str
    contract: Address | None
    symbol: str
    decimals: int | None
    balance_base_units: UInt | None
    verification_status: Literal["VERIFIED", "UNAVAILABLE", "UNVERIFIED"]
    bytecode_hash: Hash | None = None
    reason_codes: list[str] = Field(default_factory=list)


class PriceObservation(Wire):
    provider: str
    feed_contract: Address | None = None
    represented_pair: str
    price_usd_e8: UInt | None = None
    decimals: int | None = None
    updated_at: Timestamp | None = None
    round_id: str | None = None
    status: str
    display_eligible: bool = False
    valuation_eligible: bool = False
    authorization_eligible: bool = False
    source_ref: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class ObservedPortfolioSnapshot(Wire):
    schema_version: Literal["2.0"] = "2.0"
    snapshot_id: Id
    content_hash: Hash
    mode: Literal["MOCK", "LOCAL", "FUJI"]
    chain_id: Literal[31337, 43113]
    vault_address: Address
    block_number: Counter
    block_hash: Hash
    block_timestamp: Timestamp
    observed_at: Timestamp
    source_rpc_id: str
    policy_hash: Hash | None
    policy_version: Counter | None
    policy_state: dict = Field(default_factory=dict)
    assets: list[AssetObservation]
    price_observations: list[PriceObservation] = Field(default_factory=list)
    history_version: Counter
    verification_status: Literal["VERIFIED", "INCOMPLETE", "UNVERIFIED"]
    authorization_eligible: Literal[False] = False
    reason_codes: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    independent_balance_check: Literal["MATCHED", "MISMATCH", "NOT_AVAILABLE"] = "NOT_AVAILABLE"


class VerifiedDecisionSnapshot(PortfolioSnapshot):
    schema_version: Literal["2.0"] = "2.0"
    observation_snapshot_id: Id
    observation_hash: Hash
    content_hash: Hash
    eligible_for_authorization: Literal[True] = True
    verification_scope: Literal["MOCK_FIXTURE", "LOCAL_TEST_ORACLE"]
    block_hash: Hash
    block_timestamp: Timestamp
    observed_at: Timestamp
    source_rpc_id: str
    policy_hash: Hash
    policy_version: Counter
    asset_identities: list[str]
    build_id: str


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
