"""Controlled demo producer only; not a market-feed implementation."""

import time

from treasury_backend.core.errors import ControlError

from .models import DEFAULT_SOURCE_ID, OraclePrice


def snapshot(w3, *, chain_id, vault, prices, local=False):
    if w3.eth.chain_id != chain_id:
        raise ControlError("ORACLE_CHAIN_MISMATCH")
    if local:
        if not w3.client_version.lower().startswith("anvil"):
            raise ControlError("LOCAL_ORACLE_REQUIRES_ANVIL")
        w3.provider.make_request("evm_mine", [])
    block = w3.eth.get_block("latest")
    now = int(time.time())
    if not 0 <= now - block.timestamp <= 60:
        raise ControlError("ORACLE_CHAIN_HEAD_NOT_FRESH")
    if min(map(int, prices)) <= 0:
        raise ControlError("ORACLE_PRICE_NOT_POSITIVE")
    value = OraclePrice(
        chain_id=chain_id,
        vault_address=vault,
        price_source=DEFAULT_SOURCE_ID,
        price_usdc_usd_e8=prices[0],
        price_wavax_usd_e8=prices[1],
        price_timestamp=now,
    )
    return value, block.number
