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
