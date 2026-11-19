"""Providers preserve the source update timestamp and never issue approvals."""

from typing import Protocol

from .models import OraclePrice


class PriceProvider(Protocol):
    def read(self) -> OraclePrice: ...
