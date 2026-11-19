from pathlib import Path

from treasury_backend.core.errors import ControlError
from treasury_backend.core.json import json_object

from .models import OraclePrice
from .ports import PriceProvider


class JsonFilePriceProvider:
    """Read a producer snapshot verbatim; freshness remains checked by consumers."""

    def __init__(self, path: Path | None):
        self.path = path

    def read(self) -> OraclePrice:
        if self.path is None:
            raise ControlError("UNVERIFIED_PRICE", 503)
        try:
            value = OraclePrice.model_validate(json_object(self.path.read_bytes()))
            if value.price_source != "TRUSTED_TEST_ORACLE":
                raise ValueError("Chainlink evidence must be read directly from RPC")
            return value
        except (ValueError, OSError):
            raise ControlError("UNVERIFIED_PRICE", 503) from None


def build_provider(path: Path | None) -> PriceProvider:
    """Composition hook for a future reviewed feed/API adapter in this module."""
    return JsonFilePriceProvider(path)
