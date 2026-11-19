"""V2.1 wire contract and canonical ABI. Amounts/prices are integer base units/usdE8."""

from typing import Annotated, Literal

from eth_abi import encode
from eth_account.messages import encode_typed_data
from eth_utils import keccak as _keccak
from eth_utils import to_checksum_address
from pydantic import AfterValidator, Field, field_validator, model_validator

from .wire import Address, Delta, Hash, UInt
from .wire import Wire as BaseWire


def keccak(data: bytes) -> str:
    return "0x" + _keccak(data).hex()


class Wire(BaseWire):
    @field_validator("*", mode="before")
    @classmethod
    def freeze_arrays(cls, value, info):
        from typing import get_origin

        if (
            isinstance(value, list)
            and get_origin(cls.model_fields[info.field_name].annotation) is tuple
        ):
            return tuple(value)
        return value


Addr = Annotated[Address, AfterValidator(str.lower)]
ZERO_HASH = "0x" + "00" * 32
INT_MAX = 2**255 - 1


class Asset(Wire):
    address: Addr
    decimals: int = Field(ge=0, le=18)


class Registry(Wire):
    version: Literal[1] = 1
    assets: tuple[Asset, Asset]

    @model_validator(mode="after")
    def complete(self):
        if self.assets[0].address >= self.assets[1].address:
            raise ValueError("registry must be sorted and unique")
        if sorted(a.decimals for a in self.assets) != [6, 18]:
            raise ValueError("MVP requires USDC6 and WAVAX18")
        return self

    @property
    def hash(self):
        return keccak(
            encode(
                ["uint256", "(address,uint8)[]"],
                [self.version, [(a.address, a.decimals) for a in self.assets]],
            )
        )


class ProofPolicy(Wire):
    max_wavax_per_swap: UInt
    max_relative_loss_bps: int = Field(ge=0, lt=10000)
    fixed_loss_usd_e8: UInt
    oracle_band_bps: int = Field(ge=0, lt=10000)
    tolerance_bps: int = Field(ge=0, lt=10000)
    max_oracle_age: int = Field(gt=0, le=3600)
    max_session_risk_usd_e8: UInt
    global_daily_risk_usd_e8: UInt
    oracle_source_hash: Hash
    authorization: Literal["TEST_ONLY", "OWNER_APPROVED"]

    @model_validator(mode="after")
    def usable(self):
        if (
            int(self.max_session_risk_usd_e8) == 0
            or int(self.global_daily_risk_usd_e8) == 0
            or self.oracle_source_hash == ZERO_HASH
        ):
            raise ValueError("nonzero risk caps and oracle provenance required")
        return self

    @property
    def abi_tuple(self):
        return (
            int(self.max_wavax_per_swap),
            self.max_relative_loss_bps,
            int(self.fixed_loss_usd_e8),
            self.oracle_band_bps,
            self.tolerance_bps,
            self.max_oracle_age,
            int(self.max_session_risk_usd_e8),
            int(self.global_daily_risk_usd_e8),
            bytes.fromhex(self.oracle_source_hash[2:]),
            self.authorization == "OWNER_APPROVED",
        )

    @property
    def hash(self):
        return keccak(
            encode(
                ["(uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,bytes32,bool)"],
                [self.abi_tuple],
            )
        )


class DeploymentProofConfig(Wire):
    proof_policy: ProofPolicy
    session_limit_usd_e8: UInt
    session_duration_seconds: int = Field(gt=30, le=86400 * 7)
    approval_ttl_seconds: int = Field(default=30, gt=0, le=300)

    @model_validator(mode="after")
    def valid_session_limit(self):
        if not 0 < int(self.session_limit_usd_e8) <= int(self.proof_policy.max_session_risk_usd_e8):
            raise ValueError("invalid owner session limit")
        return self


class Price(Wire):
    asset: Addr
    low_usd_e8: UInt
    nominal_usd_e8: UInt
    high_usd_e8: UInt

    @model_validator(mode="after")
    def band(self):
        if not 0 < int(self.low_usd_e8) <= int(self.nominal_usd_e8) <= int(self.high_usd_e8):
            raise ValueError("empty/nonpositive price band")
        return self


class FeedObservation(Wire):
    asset: Addr
    feed: Addr
    description: str = Field(min_length=1, max_length=32)
    decimals: int = Field(ge=0, le=18)
    answer_raw: UInt
    round_id: UInt
    answered_in_round: UInt
    started_at: int = Field(gt=0)
    updated_at: int = Field(gt=0)
    max_age_seconds: int = Field(gt=0, le=86400)
    bytecode_hash: Hash


class OracleEvidence(Wire):
    chain_id: Literal[31337, 43113]
    vault: Addr
    source_hash: Hash
    timestamp: int = Field(ge=0)
    block_number: int = Field(ge=0)
    block_hash: Hash
    prices: tuple[Price, Price]
    controlled: Literal[True] = True
    feeds: tuple[FeedObservation, ...] = Field(default=(), max_length=2)

    @property
    def hash(self):
        legacy = keccak(
            encode(
                [
                    "uint256",
                    "address",
                    "bytes32",
                    "uint256",
                    "uint256",
                    "bytes32",
                    "(address,uint256,uint256,uint256)[]",
                ],
                [
                    self.chain_id,
                    self.vault,
                    bytes.fromhex(self.source_hash[2:]),
                    self.timestamp,
                    self.block_number,
                    bytes.fromhex(self.block_hash[2:]),
                    [
                        (p.asset, int(p.low_usd_e8), int(p.nominal_usd_e8), int(p.high_usd_e8))
                        for p in self.prices
                    ],
                ],
            )
        )
        if not self.feeds:
            return legacy
        import json

        return keccak(bytes.fromhex(legacy[2:]) + json.dumps(
            [f.model_dump(mode="json") for f in self.feeds],
            sort_keys=True, separators=(",", ":"),
        ).encode())


class BalanceRead(Wire):
    asset: Addr
    before: UInt
    after: UInt

    @property
    def delta(self):
        return int(self.after) - int(self.before)


class AllowanceRead(Wire):
    token: Addr
    spender: Addr
    before: UInt
    after: UInt


class EffectEvidenceV2(Wire):
    chain_id: Literal[31337, 43113]
    vault: Addr
    intent_hash: Hash
    policy_hash: Hash
    calldata_hash: Hash
    block_number: int = Field(ge=0)
    block_hash: Hash
    timestamp: int = Field(ge=0)
    registry_hash: Hash
    balances: tuple[BalanceRead, BalanceRead]
    allowances: tuple[AllowanceRead, AllowanceRead]
    unexpected_transfer: bool
    unauthorized_approval: bool
    simulator_version: Literal["guarded-v2.1"] = "guarded-v2.1"
    adapter_version: Literal["mock-swap-v1", "lfj-v1-fuji-v1"] = "mock-swap-v1"

    @property
    def hash(self):
        return keccak(
            encode(
                [
                    "uint256",
                    "address",
                    "bytes32",
                    "bytes32",
                    "bytes32",
                    "uint256",
                    "bytes32",
                    "uint256",
                    "bytes32",
                    "(address,uint256,uint256)[]",
                    "(address,address,uint256,uint256)[]",
                    "bool",
                    "bool",
                    "bytes32",
                    "bytes32",
                ],
                [
                    self.chain_id,
                    self.vault,
                    bytes.fromhex(self.intent_hash[2:]),
                    bytes.fromhex(self.policy_hash[2:]),
                    bytes.fromhex(self.calldata_hash[2:]),
                    self.block_number,
                    bytes.fromhex(self.block_hash[2:]),
                    self.timestamp,
                    bytes.fromhex(self.registry_hash[2:]),
                    [(b.asset, int(b.before), int(b.after)) for b in self.balances],
                    [(a.token, a.spender, int(a.before), int(a.after)) for a in self.allowances],
                    self.unexpected_transfer,
                    self.unauthorized_approval,
                    bytes.fromhex(keccak(self.simulator_version.encode())[2:]),
                    bytes.fromhex(keccak(self.adapter_version.encode())[2:]),
                ],
            )
        )


class BalanceBound(Wire):
    asset: Addr
    min_delta: Delta

    @model_validator(mode="after")
    def signed_range(self):
        if not -(2**255) <= int(self.min_delta) <= INT_MAX:
            raise ValueError("int256 overflow")
        return self


class AllowanceCap(Wire):
    token: Addr
    spender: Addr
    max_remaining: Literal["0"] = "0"


class PostConditionsV2(Wire):
    balance_bounds: tuple[BalanceBound, BalanceBound]
    allowance_caps: tuple[AllowanceCap, AllowanceCap]

    @model_validator(mode="after")
    def canonical(self):
        if self.balance_bounds[0].asset >= self.balance_bounds[1].asset:
            raise ValueError("Phi assets must be sorted and unique")
        pairs = [(a.token, a.spender) for a in self.allowance_caps]
        if pairs != sorted(set(pairs)):
            raise ValueError("Phi allowances must be sorted and unique")
        return self

    @property
    def abi_tuple(self):
        return (
            [(to_checksum_address(b.asset), int(b.min_delta)) for b in self.balance_bounds],
            [
                (to_checksum_address(a.token), to_checksum_address(a.spender), 0)
                for a in self.allowance_caps
            ],
        )

    @property
    def abi_bytes(self):
        return encode(["((address,int256)[],(address,address,uint256)[])"], [self.abi_tuple])

    @property
    def hash(self):
        return keccak(self.abi_bytes)


class SessionContext(Wire):
    session_id: Hash
    policy_hash: Hash
    starts_at: int = Field(ge=0)
    expires_at: int = Field(ge=0)
    active: bool
    limit_usd_e8: UInt
    used_usd_e8: UInt
    global_limit_usd_e8: UInt
    global_used_usd_e8: UInt
    block_number: int = Field(ge=0)
    block_hash: Hash
    timestamp: int = Field(ge=0)


Verdict = Literal["SAT", "UNSAT", "UNKNOWN"]


class ProofArtifactV2(Wire):
    status: Literal["VERIFIED", "VIOLATED", "INCONCLUSIVE", "ERROR"]
    reason: str
    check_mode: Verdict = "UNKNOWN"
    compile_mode: Verdict = "UNKNOWN"
    risk_bound: Verdict = "UNKNOWN"
    assumptions_satisfiable: bool = False
    compiled_region_satisfiable: bool = False
    phi: PostConditionsV2 | None = None
    risk_debit_usd_e8: UInt | None = None
    query_hashes: tuple[Hash, ...] = Field(default=(), max_length=12)
    encoder_version: Literal["pgs-treasury-2.1.0"] = "pgs-treasury-2.1.0"
    solver_version: str
    source_hash: Hash
    policy_hash: Hash
    policy_config_hash: Hash
    registry_hash: Hash
    oracle_hash: Hash
    exact_call_hash: Hash
    evidence_root: Hash
    session_context_hash: Hash
    fallback_tau_zero: bool = False
    witness: dict[str, str] | None = None

    @property
    def context_hash(self):
        # ABI commitment to every source/obligation/version. Full JSON is only an audit container.
        def h(x):
            return bytes.fromhex(x[2:])

        return keccak(
            encode(
                ["bytes32[]", "uint256", "bool", "bool", "bool"],
                [
                    [
                        h(x)
                        for x in (
                            self.policy_hash,
                            self.policy_config_hash,
                            self.registry_hash,
                            self.oracle_hash,
                            self.exact_call_hash,
                            self.evidence_root,
                            self.session_context_hash,
                            self.source_hash,
                            keccak(self.encoder_version.encode()),
                            keccak(self.solver_version.encode()),
                            keccak(self.status.encode()),
                            keccak(self.reason.encode()),
                            keccak(self.check_mode.encode()),
                            keccak(self.compile_mode.encode()),
                            keccak(self.risk_bound.encode()),
                            self.phi.hash if self.phi else ZERO_HASH,
                            *self.query_hashes,
                        )
                    ],
                    int(self.risk_debit_usd_e8 or "0"),
                    self.assumptions_satisfiable,
                    self.compiled_region_satisfiable,
                    self.fallback_tau_zero,
                ],
            )
        )


APPROVAL_V2_FIELDS = [
    ("intentHash", "bytes32"),
    ("calldataHash", "bytes32"),
    ("policyHash", "bytes32"),
    ("evidenceRoot", "bytes32"),
    ("proofContextHash", "bytes32"),
    ("postConditionsHash", "bytes32"),
    ("sessionId", "bytes32"),
    ("riskDebitUsdE8", "uint256"),
    ("nonce", "uint256"),
    ("deadline", "uint256"),
    ("adapter", "address"),
    ("tokenIn", "address"),
    ("tokenOut", "address"),
    ("amountIn", "uint256"),
    ("minAmountOut", "uint256"),
]


class ApprovalV2(Wire):
    intentHash: Hash
    calldataHash: Hash
    policyHash: Hash
    evidenceRoot: Hash
    proofContextHash: Hash
    postConditionsHash: Hash
    sessionId: Hash
    riskDebitUsdE8: UInt
    nonce: UInt
    deadline: UInt
    adapter: Addr
    tokenIn: Addr
    tokenOut: Addr
    amountIn: UInt
    minAmountOut: UInt

    @property
    def abi_tuple(self):
        return tuple(
            int(getattr(self, n))
            if t == "uint256"
            else to_checksum_address(getattr(self, n))
            if t == "address"
            else getattr(self, n)
            for n, t in APPROVAL_V2_FIELDS
        )


class DomainV2(Wire):
    name: Literal["TreasuryPolicyVault"] = "TreasuryPolicyVault"
    version: Literal["2"] = "2"
    chainId: Literal[31337, 43113]
    verifyingContract: Addr


class SignedPDRV2(Wire):
    decision_id: str
    build_id: str
    domain: DomainV2
    approval: ApprovalV2
    phi: PostConditionsV2
    signature: Annotated[str, Field(pattern=r"^0x[0-9a-f]{130}$")]
    typed_data_hash: Hash


class PreflightV2Request(Wire):
    build_id: str = Field(min_length=1, max_length=128)
    proof: ProofArtifactV2
    session_id: Hash
    required_stress: dict[
        Literal["reserve_shift_mild", "reserve_shift_adverse"],
        Literal["SUCCESS_REQUIRED", "PROTECTED_REVERT_ALLOWED"],
    ] = Field(
        default_factory=lambda: {
            "reserve_shift_mild": "SUCCESS_REQUIRED",
            "reserve_shift_adverse": "PROTECTED_REVERT_ALLOWED",
        },
        max_length=2,
    )


def message_v2(domain: DomainV2, approval: ApprovalV2):
    data = approval.model_dump()
    for n, t in APPROVAL_V2_FIELDS:
        if t == "uint256":
            data[n] = int(data[n])
    return encode_typed_data(
        domain_data=domain.model_dump(),
        message_types={"ApprovalV2": [{"name": n, "type": t} for n, t in APPROVAL_V2_FIELDS]},
        message_data=data,
    )


def digest_v2(domain, approval):
    msg = message_v2(domain, approval)
    return keccak(b"\x19" + msg.version + msg.header + msg.body)


def call_hash(b):
    return keccak(
        encode(
            [
                "uint256",
                "address",
                "address",
                "address",
                "address",
                "uint256",
                "uint256",
                "uint256",
                "uint256",
                "bytes32",
                "bytes32",
            ],
            [
                b.chain_id,
                b.vault_address,
                b.router,
                b.token_in,
                b.token_out,
                int(b.amount_in_base_units),
                int(b.min_amount_out_base_units),
                int(b.nonce),
                b.deadline,
                bytes.fromhex(b.policy_hash[2:]),
                bytes.fromhex(b.calldata_hash[2:]),
            ],
        )
    )


def session_hash(s: SessionContext):
    return keccak(
        encode(
            [
                "bytes32",
                "bytes32",
                "uint256",
                "uint256",
                "bool",
                "uint256",
                "uint256",
                "uint256",
                "uint256",
                "uint256",
                "bytes32",
                "uint256",
            ],
            [
                bytes.fromhex(s.session_id[2:]),
                bytes.fromhex(s.policy_hash[2:]),
                s.starts_at,
                s.expires_at,
                s.active,
                int(s.limit_usd_e8),
                int(s.used_usd_e8),
                int(s.global_limit_usd_e8),
                int(s.global_used_usd_e8),
                s.block_number,
                bytes.fromhex(s.block_hash[2:]),
                s.timestamp,
            ],
        )
    )


def approval_v2(b, evidence_root, proof, session_id):
    if proof.status != "VERIFIED" or proof.phi is None or proof.risk_debit_usd_e8 is None:
        raise ValueError("verified proof required")
    return ApprovalV2(
        intentHash=keccak(b.intent_id.encode()),
        calldataHash=b.calldata_hash,
        policyHash=b.policy_hash,
        evidenceRoot=evidence_root,
        proofContextHash=proof.context_hash,
        postConditionsHash=proof.phi.hash,
        sessionId=session_id,
        riskDebitUsdE8=proof.risk_debit_usd_e8,
        nonce=b.nonce,
        deadline=str(b.deadline),
        adapter=b.router,
        tokenIn=b.token_in,
        tokenOut=b.token_out,
        amountIn=b.amount_in_base_units,
        minAmountOut=b.min_amount_out_base_units,
    )
