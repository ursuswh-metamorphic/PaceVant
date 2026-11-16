from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.domain import Address, ArtifactRef, Bps, Counter, Id, Source, Timestamp
from treasury_contracts.models import Baseline, Hash, StressTest, UInt, Wire

Mode = Literal["MOCK", "LOCAL", "FUJI"]
Goal = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Scenario = Literal["normal_swap", "exposure_limit", "stale_price", "injection"]


class WorkflowRequest(Wire):
    goal: Goal
    mandate_id: Id
    scenario: Scenario | None = None


class Mandate(Wire):
    mandate_id: Id
    version: Annotated[int, Field(gt=0)]
    chain_id: Literal[31337, 43113] = 43113
    vault_address: Address
    owner: Address
    router: Address
    token_in: Address
    token_out: Address
    policy_hash: Hash
    max_usdc_per_swap_base_units: UInt
    max_usdc_spend_per_day_base_units: UInt
    max_daily_execution_cost_usd_e8: UInt
    max_avax_exposure_bps: Bps
    max_slippage_bps: Bps
    max_replans: Annotated[int, Field(ge=0, le=2)]
    expires_at: Timestamp
    status: Literal["ACTIVE", "PAUSED", "REVOKED"]
    required_stress: dict[Id, Literal["SUCCESS_REQUIRED", "PROTECTED_REVERT_ALLOWED"]]


class ChainContext(Wire):
    deployment: Mode
    chain_id: Literal[31337, 43113]
    vault_address: Address
    owner: Address
    router: Address
    token_in: Address
    token_out: Address
    token_in_decimals: Literal[6]
    token_out_decimals: Literal[18]
    policy_hash: Hash
    policy_version: int
    policy_active: bool = True
    policy_expires_at: Timestamp | None = None
    paused: bool
    attestor: Address
    relayer: Address
    block_number: Counter
    block_timestamp: Timestamp
    bytecode_hash: Hash
    fork_block: Counter | None = None
    fork_block_hash: Hash | None = None
    fork_block_timestamp: Timestamp | None = None
    nonce_used: bool | None = None
    max_usdc_per_swap_base_units: UInt
    max_usdc_spend_per_day_base_units: UInt
    max_slippage_bps: Bps = 100
    max_approval_ttl: Annotated[int, Field(gt=0)] = 30


class ChainBalances(Wire):
    chain_id: Literal[31337, 43113]
    vault_address: Address
    policy_hash: Hash
    block_number: Counter
    block_timestamp: Timestamp
    usdc_base_units: UInt
    wavax_base_units: UInt
    utc_day: Counter
    daily_spent_usdc_base_units: UInt
    daily_execution_cost_usd_e8: UInt
    daily_execution_cost_wei: UInt = "0"
    max_fee_per_gas_wei: UInt


class OraclePrice(Wire):
    chain_id: Literal[31337, 43113]
    vault_address: Address
    price_usdc_usd_e8: UInt
    price_wavax_usd_e8: UInt
    price_source: Literal["TRUSTED_TEST_ORACLE"]
    price_timestamp: Timestamp


class Alignment(Wire):
    verdict: Literal["ALIGNED", "MISALIGNED", "UNCERTAIN"]
    reason_codes: list[Id]
    shield_model_version: Literal["rules-v1"] = "rules-v1"
    evidence_refs: list[Hash]


class Manifest(Wire):
    chain_id: Literal[43113]
    vault_address: Address
    policy_hash: Hash
    calldata_hash: Hash
    fork_block: Counter
    fork_block_hash: Hash
    fork_block_timestamp: Timestamp
    bytecode_hash: Hash
    parser_version: Id
    verification_status: Literal["COMPLETE", "INCOMPLETE", "INCONCLUSIVE"]
    artifact_hashes: dict[ArtifactRef, Hash]


class EvidenceReport(Wire):
    intent_id: Id
    build_id: Id
    nonce: UInt
    deadline: Timestamp
    simulation_mode: Id
    source: Source
    baseline: Baseline
    stress_tests: list[StressTest]
