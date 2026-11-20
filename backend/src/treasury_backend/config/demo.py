"""Explicit opt-in for one sponsor-funded demo identity, never a signing wallet."""

import os
from dataclasses import dataclass, field

from pydantic import TypeAdapter

from treasury_backend.core.domain import Address


@dataclass(frozen=True)
class DemoSettings:
    enabled: bool = False
    address: str = ""
    access_token: str = field(default="", repr=False)
    initial_credit_wei: int = 10**15
    max_transaction_fee_wei: int = 10**14

    def __post_init__(self):
        if not self.enabled:
            return
        TypeAdapter(Address).validate_python(self.address)
        if len(self.access_token) < 32:
            raise ValueError("Configure a separate demo access token of at least 32 characters")
        if not 0 < self.max_transaction_fee_wei <= self.initial_credit_wei <= 5 * 10**16:
            raise ValueError("Invalid demo gas budget: max fee <= credit <= 0.05 AVAX")

    @classmethod
    def from_env(cls):
        return cls.from_values(os.environ)

    @classmethod
    def from_values(cls, values):
        flag = values.get("PACEVANT_DEMO_ENABLED", "0")
        if flag not in {"0", "1"}:
            raise ValueError("PACEVANT_DEMO_ENABLED must be 0 or 1")
        return cls(
            enabled=flag == "1",
            address=values.get("TREASURY_DEMO_USER_ADDRESS", ""),
            access_token=values.get("PACEVANT_DEMO_ACCESS_TOKEN", ""),
            initial_credit_wei=int(values.get("PACEVANT_DEMO_INITIAL_CREDIT_WEI", str(10**15))),
            max_transaction_fee_wei=int(values.get("PACEVANT_DEMO_MAX_TX_FEE_WEI", str(10**14))),
        )
