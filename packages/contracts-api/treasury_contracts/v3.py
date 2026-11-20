"""V3 fixed-operation protocol. All asset amounts are integer strings, never floats."""

from typing import Annotated, Literal

from eth_abi import encode
from eth_account.messages import encode_typed_data
from eth_utils import is_checksum_address, to_checksum_address
from pydantic import AfterValidator, Field, field_validator, model_validator

from .crypto import content_hash, keccak
from .v2 import Wire
from .wire import Address, Hash, UInt

ZERO = "0x" + "00" * 20
ZERO_HASH = "0x" + "00" * 32
KINDS = {"TOKEN_SWAP": 1, "TOKEN_PAYMENT": 2, "VAULT_DEPOSIT": 3, "VAULT_WITHDRAW": 4}


def address(value):
    raw = value[2:]
    if raw != raw.lower() and raw != raw.upper() and not is_checksum_address(value):
        raise ValueError("invalid mixed-case address checksum")
    return value.lower()


Addr = Annotated[Address, AfterValidator(address)]
Amount = Annotated[UInt, AfterValidator(lambda v: v if 0 < int(v) < 2**255 else _bad_amount())]


def _bad_amount():
    raise ValueError("amount must be positive and fit int256")


class OperationIntent(Wire):
    operation: Literal["TOKEN_SWAP", "TOKEN_PAYMENT", "VAULT_DEPOSIT", "VAULT_WITHDRAW"]
    chain_id: Literal[31337, 43113]
    treasury: Addr
    session_id: Hash
    token_in: Addr
    token_out: Addr
    recipient: Addr
    amount: Amount
    min_output: UInt = "0"
    slippage_bps: int = Field(ge=0, le=1000, default=40)
    deadline: int = Field(gt=0, le=2**53 - 1)
    objective: str = Field(min_length=1, max_length=1200)
    rebalance: bool = False

    @model_validator(mode="after")
    def bounded(self):
        if self.rebalance and self.operation != "TOKEN_SWAP":
            raise ValueError("rebalancing produces swaps only")
        if int(self.min_output) >= 2**255:
            raise ValueError("output overflow")
        if self.operation == "TOKEN_PAYMENT" and self.token_in != self.token_out:
            raise ValueError("payments have one asset")
        return self

    @property
    def hash(self):
        return content_hash(self.model_dump(mode="json"))


class RebalanceRequest(Wire):
    operation: Literal["TREASURY_REBALANCE"] = "TREASURY_REBALANCE"
    session_id: Hash
    objective: str = Field(min_length=1, max_length=1200, default="Rebalance within owner targets")
    execute: bool = False


class RebalancePolicy(Wire):
    target_usdc_bps: int = Field(ge=0, le=10000, default=8000)
    target_wavax_bps: int = Field(ge=0, le=10000, default=2000)
    minimum_deviation_bps: int = Field(gt=0, le=5000, default=300)
    minimum_trade_usd_e8: Amount = "100000000"
    max_trade_usd_e8: Amount = "10000000000"

    @model_validator(mode="after")
    def allocations(self):
        if self.target_usdc_bps + self.target_wavax_bps != 10000:
            raise ValueError("targets must sum to 100%")
        if int(self.minimum_trade_usd_e8) > int(self.max_trade_usd_e8):
            raise ValueError("invalid trade interval")
        return self


class Manifest(Wire):
    """Owner/operator-installed local configuration; never writable through the agent API."""
    schema_version: Literal[3] = 3
    environment: Literal["LOCAL", "LOCAL_FORK"]
    chain_id: Literal[31337, 43113]
    treasury: Addr
    usdc: Addr
    wavax: Addr
    shares: Addr
    adapter: Addr
    owner: Addr
    attestor: Addr
    relayer: Addr
    default_session_id: Hash | None = None
    payee_candidates: tuple[Addr, ...] = ()
    # Local fixture reference prices are explicitly not Chainlink or production valuations.
    local_usdc_price_e8: Amount = "100000000"
    local_wavax_price_e8: Amount = "2000000000"
    max_price_impact_bps: int = Field(ge=0, le=1000, default=100)
    rebalance_policy: RebalancePolicy = Field(default_factory=RebalancePolicy)
    code_hashes: dict[str, Hash]
    owner_signature: str = "0x"

    @model_validator(mode="after")
    def identities(self):
        contracts = [self.treasury, self.usdc, self.wavax, self.shares, self.adapter]
        if len(set(contracts)) != 5 or ZERO in contracts:
            raise ValueError("contract registry identities must be distinct")
        if len({self.owner, self.attestor, self.relayer}) != 3:
            raise ValueError("owner, attestor and relayer must differ")
        if set(self.code_hashes) != {"treasury", "usdc", "wavax", "shares", "adapter"}:
            raise ValueError("all contract code identities are required")
        if self.environment == "LOCAL_FORK" and self.chain_id != 43113:
            raise ValueError("Fuji fork requires chain 43113")
        return self

    def signing_message(self):
        from eth_account.messages import encode_defunct
        return encode_defunct(text="PACEVANT_V3_MANIFEST:" + content_hash(self.model_dump(mode="json", exclude={"owner_signature"})))

    def verify_owner(self):
        from eth_account import Account
        try:
            if Account.recover_message(self.signing_message(), signature=self.owner_signature).lower() != self.owner:
                raise ValueError("OWNER_MANIFEST_SIGNATURE_INVALID")
        except Exception:
            raise ValueError("OWNER_MANIFEST_SIGNATURE_INVALID") from None


class Constraints(Wire):
    before_balances: tuple[UInt, UInt, UInt, UInt]
    min_deltas: tuple[str, str, str, str]
    receipt_credit: UInt
    max_wavax_balance: UInt

    @field_validator("min_deltas")
    @classmethod
    def deltas(cls, values):
        import re

        if any(not re.fullmatch(r"-?(0|[1-9][0-9]*)", v) or not -(2**255) < int(v) < 2**255 for v in values):
            raise ValueError("invalid signed deltas")
        return values

    @property
    def abi_tuple(self):
        return ([int(v) for v in self.before_balances], [int(v) for v in self.min_deltas],
                int(self.receipt_credit), int(self.max_wavax_balance))

    @property
    def hash(self):
        return keccak(encode(["(uint256[4],int256[4],uint256,uint256)"], [self.abi_tuple]))


OPERATION_FIELDS = [
    ("kind", "uint8"), ("rebalance", "bool"),
    *[(n, "bytes32") for n in ("policyHash", "sessionId", "intentHash", "evidenceRoot",
                                "proofContextHash", "constraintsHash", "calldataHash")],
    *[(n, "address") for n in ("target", "tokenIn", "tokenOut", "recipient")],
    *[(n, "uint256") for n in ("amount", "minOutput", "spendDebitUsdE8", "riskDebitUsdE8", "nonce", "deadline")],
]


class Operation(Wire):
    kind: int = Field(ge=1, le=4)
    rebalance: bool
    policyHash: Hash
    sessionId: Hash
    intentHash: Hash
    evidenceRoot: Hash
    proofContextHash: Hash
    constraintsHash: Hash
    calldataHash: Hash
    target: Addr
    tokenIn: Addr
    tokenOut: Addr
    recipient: Addr
    amount: Amount
    minOutput: Amount
    spendDebitUsdE8: Amount
    riskDebitUsdE8: UInt
    nonce: UInt
    deadline: UInt

    @property
    def abi_tuple(self):
        return tuple(int(getattr(self, n)) if t.startswith("uint") else
                     to_checksum_address(getattr(self, n)) if t == "address" else getattr(self, n)
                     for n, t in OPERATION_FIELDS)


def operation_message(chain_id, treasury, operation):
    return encode_typed_data(
        domain_data={"name": "TreasuryPolicyVault", "version": "3", "chainId": chain_id, "verifyingContract": treasury},
        message_types={"Operation": [{"name": n, "type": t} for n, t in OPERATION_FIELDS]},
        message_data=dict(zip((n for n, _ in OPERATION_FIELDS), operation.abi_tuple, strict=True)),
    )


def operation_digest(chain_id, treasury, operation):
    msg = operation_message(chain_id, treasury, operation)
    return keccak(b"\x19" + msg.version + msg.header + msg.body)


def call_hash(target, value, calldata):
    return keccak(encode(["address", "uint256", "bytes"], [target, value, bytes.fromhex(calldata.removeprefix("0x"))]))
