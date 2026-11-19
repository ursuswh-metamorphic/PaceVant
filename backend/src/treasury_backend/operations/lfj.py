"""Read a pinned LFJ quote and reference oracle observations from Fuji."""

import httpx
from web3 import Web3

from treasury_backend.modules.execution.dex.lfj import LFJClient
from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.oracle.fuji.fuji_oracles import CHAINLINK_FEEDS, chainlink
from treasury_backend.modules.oracle.fuji.fuji_rpc import FujiReadError, FujiRPC, quantity
from treasury_contracts.v2 import keccak

from .env import PUBLIC_RPC
from .errors import OpsError


def preflight():
    """Use the same public RPC for both readers and check a common block identity."""
    import rfc8785

    try:
        w3 = Web3(Web3.HTTPProvider(PUBLIC_RPC, request_kwargs={"timeout": 8}))
        route = LFJClient(w3).preflight()
        with httpx.Client(trust_env=False, follow_redirects=False) as http:
            reader = FujiRPC(http)
            if quantity(reader.rpc("eth_chainId", [])) != 43113:
                raise FujiReadError("FUJI_CHAIN_MISMATCH")
            reader.block = {
                "number": route["block_number"],
                "hash": route["block_hash"],
                "timestamp": route["block_timestamp"],
            }
            if not 0 <= reader.now - reader.block["timestamp"] <= 120:
                raise FujiReadError("FUJI_BLOCK_CHANGED_OR_STALE")
            reader.verify_block()
            observations = [chainlink(reader, *feed) for feed in CHAINLINK_FEEDS]
            reader.verify_block()
    except PlaneError as exc:
        raise OpsError(exc.code) from None
    except FujiReadError as exc:
        raise OpsError(exc.code) from None
    except Exception:
        raise OpsError("FUJI_PREFLIGHT_UNAVAILABLE") from None
    report = {
        "preflight": route,
        "oracle_observations": observations,
        "used_for_sde_or_attestation": False,
        "broadcast": False,
    }
    return {**report, "observation_hash": keccak(rfc8785.dumps(report))}
