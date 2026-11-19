"""Authoritative Fuji provider: direct contract reads at one pinned block."""

import time

from eth_abi import decode, encode
from web3 import Web3

from treasury_backend.core.errors import ControlError
from treasury_contracts.oracle import CHAINLINK_SOURCE, CIRCLE_USDC, FEEDS, SOURCE_HASH, WAVAX
from treasury_contracts.v2 import FeedObservation

from .models import OraclePrice


class ChainlinkPriceProvider:
    def __init__(self, rpc_url, vault):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
        self.vault = vault

    def read(self, block="latest"):
        def call(w3, address, signature, returns, block):
            raw = w3.eth.call({"to": Web3.to_checksum_address(address),
                              "data": Web3.keccak(text=signature)[:4]}, block_identifier=block)
            decoded = decode(returns, raw)
            if encode(returns, decoded) != raw:
                raise ValueError("noncanonical oracle ABI")
            return decoded

        try:
            if self.w3.eth.chain_id != 43113:
                raise ValueError("chain")
            header = self.w3.eth.get_block(block)
            feeds, prices = [], {}
            for asset, (address, description, max_age) in sorted(FEEDS.items()):
                code = self.w3.eth.get_code(Web3.to_checksum_address(address), header.number)
                if not code:
                    raise ValueError("feed code missing")
                decimals = call(self.w3, address, "decimals()", returns=("uint8",), block=header.number)[0]
                actual = call(self.w3, address, "description()", returns=("string",), block=header.number)[0]
                if actual.replace(" ", "") != description:
                    raise ValueError("description")
                rid, answer, started, updated, answered = call(
                    self.w3, address, "latestRoundData()",
                    returns=("uint80", "int256", "uint256", "uint256", "uint80"), block=header.number,
                )
                feeds.append(FeedObservation(
                    asset=asset, feed=address, description=description, decimals=decimals,
                    answer_raw=str(answer), round_id=str(rid), answered_in_round=str(answered),
                    started_at=started, updated_at=updated, max_age_seconds=max_age,
                    bytecode_hash=Web3.to_hex(Web3.keccak(code)),
                ))
                prices[asset] = str(answer * 10**8 // 10**decimals)
            value = OraclePrice(
                chain_id=43113, vault_address=self.vault,
                price_usdc_usd_e8=prices[CIRCLE_USDC], price_wavax_usd_e8=prices[WAVAX],
                price_source=CHAINLINK_SOURCE, price_timestamp=min(f.updated_at for f in feeds),
                oracle_observed_at=header.timestamp, oracle_block_number=header.number,
                oracle_block_hash=Web3.to_hex(header.hash), oracle_feeds=feeds,
            )
            validate_price(value, int(time.time()))
            if self.w3.eth.get_block(header.number).hash != header.hash:
                raise ValueError("reorg")
            return value
        except ControlError:
            raise
        except Exception:
            raise ControlError("UNVERIFIED_PRICE", 503) from None


def validate_price(value, now):
    from treasury_contracts.oracle import validate_rounds

    if value.price_source != CHAINLINK_SOURCE:
        if value.oracle_feeds:
            raise ControlError("UNVERIFIED_PRICE")
        return
    try:
        validate_rounds(
            value.oracle_feeds, {CIRCLE_USDC: value.price_usdc_usd_e8, WAVAX: value.price_wavax_usd_e8},
            now, value.oracle_observed_at, value.chain_id, SOURCE_HASH,
        )
        if (value.price_timestamp != min(f.updated_at for f in value.oracle_feeds)
                or value.oracle_block_number is None or value.oracle_block_hash is None):
            raise ValueError("missing pinned provenance")
    except (ValueError, TypeError):
        raise ControlError("STALE_OR_UNVERIFIED_CHAINLINK_PRICE") from None
