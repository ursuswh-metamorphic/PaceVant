"""Oracle input contract; add reviewed sources here before owner policy cutover."""

from typing import Literal, get_args

from pydantic import Field

from treasury_backend.core.domain import Address, Timestamp
from treasury_contracts.models import UInt, Wire
from treasury_contracts.oracle import CHAINLINK_SOURCE, SOURCE_HASH
from treasury_contracts.v2 import FeedObservation, keccak

OracleSource = Literal["TRUSTED_TEST_ORACLE", "CHAINLINK_FUJI_CIRCLE_USDC_AVAX_V1"]
DEFAULT_SOURCE_ID = "TRUSTED_TEST_ORACLE"


def is_supported_source(source: str) -> bool:
    return source in get_args(OracleSource)


def source_hash(source: str) -> str:
    if not is_supported_source(source):
        raise ValueError("Unsupported oracle source")
    return SOURCE_HASH if source == CHAINLINK_SOURCE else keccak(source.encode())


class OraclePrice(Wire):
    chain_id: Literal[31337, 43113]
    vault_address: Address
    price_usdc_usd_e8: UInt
    price_wavax_usd_e8: UInt
    price_source: OracleSource
    price_timestamp: Timestamp
    oracle_observed_at: Timestamp | None = None
    oracle_block_number: Timestamp | None = None
    oracle_block_hash: str | None = None
    oracle_feeds: list[FeedObservation] = Field(default_factory=list, max_length=2)
