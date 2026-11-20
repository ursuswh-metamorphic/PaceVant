"""Public MVP boundary: exactly two financial operations and three existing EOA roles."""

from typing import Literal

from eth_account import Account
from eth_account.messages import encode_defunct
from pydantic import model_validator

from .crypto import content_hash
from .v3 import ZERO, Addr, Amount, Hash, OperationIntent, RebalancePolicy, Wire


class MvpIntent(OperationIntent):
    operation: Literal["SWAP_EXACT_IN", "USDC_PAYMENT"]

    def internal(self):
        return OperationIntent.model_validate(
            self.model_dump(mode="json")
            | {"operation": "TOKEN_SWAP" if self.operation == "SWAP_EXACT_IN" else "TOKEN_PAYMENT"}
        )

    @model_validator(mode="after")
    def payment(self):
        if self.operation == "USDC_PAYMENT" and (self.token_in != self.token_out or self.rebalance):
            raise ValueError("payment has one asset and is not a rebalance")
        return self


class MvpManifest(Wire):
    schema_version: Literal[1] = 1
    protocol: Literal["PACEVANT_MVP"] = "PACEVANT_MVP"
    environment: Literal["LOCAL_TEST", "ANVIL_FORK", "REAL_FUJI_EXECUTION"]
    chain_id: Literal[31337, 43113]
    treasury: Addr
    usdc: Addr
    wavax: Addr
    adapter: Addr
    owner: Addr
    attestor: Addr
    relayer: Addr
    default_session_id: Hash
    payee_candidates: tuple[Addr, ...]
    code_hashes: dict[str, Hash]
    owner_signature: str = "0x"
    local_usdc_price_e8: Amount = "100000000"
    local_wavax_price_e8: Amount = "2000000000"
    max_daily_execution_cost_usd_e8: Amount = "100000000"
    max_price_impact_bps: int = 100
    rebalance_policy: RebalancePolicy = RebalancePolicy()

    @property
    def shares(self):
        # Reserved zero slot in the fixed guard ABI, never an investment-vault identity.
        return ZERO

    @model_validator(mode="after")
    def identities(self):
        if len({self.treasury, self.usdc, self.wavax, self.adapter}) != 4 or ZERO in {
            self.treasury,
            self.usdc,
            self.wavax,
            self.adapter,
        }:
            raise ValueError("invalid contract registry")
        if len({self.owner, self.attestor, self.relayer}) != 3 or ZERO in {
            self.owner,
            self.attestor,
            self.relayer,
        }:
            raise ValueError("three distinct existing EOAs required")
        if set(self.code_hashes) != {"treasury", "usdc", "wavax", "adapter"}:
            raise ValueError("complete code identities required")
        if not 0 <= self.max_price_impact_bps <= 1000:
            raise ValueError("invalid price impact limit")
        if self.environment != "LOCAL_TEST" and self.chain_id != 43113:
            raise ValueError("Fuji chain identity required")
        return self

    def signing_message(self):
        return encode_defunct(
            text="PACEVANT_MVP_MANIFEST:"
            + content_hash(self.model_dump(mode="json", exclude={"owner_signature"}))
        )

    def verify_owner(self):
        try:
            if (
                Account.recover_message(
                    self.signing_message(), signature=self.owner_signature
                ).lower()
                != self.owner
            ):
                raise ValueError()
        except Exception:
            raise ValueError("OWNER_MANIFEST_SIGNATURE_INVALID") from None
