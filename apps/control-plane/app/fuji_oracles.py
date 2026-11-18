"""Public Fuji oracle contracts and observation-only price normalization."""

from app.fuji_rpc import EXPLORER, FujiReadError

CHAINLINK_DIRECTORY = (
    "https://reference-data-directory.vercel.app/feeds-avalanche-fuji-testnet.json"
)
CHAINLINK_FEEDS = (
    ("AVAX/USD", "0x5498BB86BC934c8D34FDA08E81D444153d0D06aD", 600),
    ("USDC/USD", "0x97FE42a7E96640D932bbc0e1580c73E705A8EB73", 86400),
)
PYTH_FUJI = "0x23f0e8FAeE7bbb405E7A7C3d60138FCfd43d7509"
PYTH_AVAX = "93da3352f9f1d105fdfe4971cfa80e9dd777bfc5d0f683ebb6e1294b92137bb7"
PYTH_DIRECTORY = (
    "https://github.com/pyth-network/pyth-crosschain/blob/main/"
    "contract_manager/src/store/contracts/EvmPriceFeedContracts.json"
)


def chainlink(reader, pair, address, heartbeat):
    out = {
        "provider": "CHAINLINK",
        "pair": pair,
        "network": "AVALANCHE_FUJI",
        "contract": address,
        "source_url": CHAINLINK_DIRECTORY,
        "explorer_url": f"{EXPLORER}/address/{address}",
        "status": "UNAVAILABLE",
        "usable_for_decisions": False,
        "freshness_limit_seconds": heartbeat,
    }
    try:
        out["bytecode_hash"] = reader.code(address)
        (decimals,) = reader.eth_call(address, "decimals()", returns=("uint8",))
        (description,) = reader.eth_call(address, "description()", returns=("string",))
        if description.replace(" ", "") != pair or not 0 <= decimals <= 18:
            raise FujiReadError("ORACLE_METADATA_MISMATCH")
        round_id, price, started, updated, answered = reader.eth_call(
            address,
            "latestRoundData()",
            returns=("uint80", "int256", "uint256", "uint256", "uint80"),
        )
        out.update(
            decimals=decimals,
            answer_raw=str(price),
            round_started_at=started,
            round_id=str(round_id),
            answered_in_round=str(answered),
            updated_at=updated,
            age_seconds=reader.now - updated if updated else None,
        )
        if (
            price <= 0
            or round_id == 0
            or answered < round_id
            or not 0 < started <= updated <= reader.block["timestamp"]
        ):
            out.update(status="UNVERIFIED", reason_code="ORACLE_INVALID_ROUND")
        else:
            out.update(
                price_usd_e8=str(price * 10**8 // 10**decimals),
                status="WITHIN_HEARTBEAT" if reader.now - updated <= heartbeat else "STALE",
            )
    except FujiReadError as error:
        out["reason_code"] = error.code
    return out


def pyth(reader):
    out = {
        "provider": "PYTH",
        "pair": "AVAX/USD",
        "network": "AVALANCHE_FUJI",
        "contract": PYTH_FUJI,
        "feed_id": "0x" + PYTH_AVAX,
        "source_url": PYTH_DIRECTORY,
        "explorer_url": f"{EXPLORER}/address/{PYTH_FUJI}",
        "status": "UNAVAILABLE",
        "usable_for_decisions": False,
        "freshness_limit_seconds": 60,
        "update_model": "PULL_ONCHAIN",
    }
    try:
        out["bytecode_hash"] = reader.code(PYTH_FUJI)
        price, confidence, exponent, updated = reader.eth_call(
            PYTH_FUJI,
            "getPriceUnsafe(bytes32)",
            ("bytes32",),
            (bytes.fromhex(PYTH_AVAX),),
            ("int64", "uint64", "int32", "uint256"),
        )
        out.update(
            price_raw=str(price),
            updated_at=updated,
            age_seconds=reader.now - updated if updated else None,
            exponent=exponent,
            confidence_raw=str(confidence),
        )
        if price <= 0 or not -18 <= exponent <= 0 or not 0 < updated <= reader.block["timestamp"]:
            out.update(status="UNVERIFIED", reason_code="ORACLE_INVALID_UPDATE")
        else:
            scale = exponent + 8
            amount = price * 10**scale if scale >= 0 else price // 10 ** (-scale)
            out.update(
                price_usd_e8=str(amount),
                confidence_bps=(confidence * 10000 + price - 1) // price,
                status="FRESH" if reader.now - updated <= 60 else "STALE",
            )
    except FujiReadError as error:
        out["reason_code"] = error.code
    return out
