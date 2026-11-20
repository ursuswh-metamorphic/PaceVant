"""EVM block compatibility and pinned batch reads for Avalanche and local forks."""

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware


def evm_web3(provider):
    """Accept Avalanche's extended extraData without changing block identity.

    The standard Web3 middleware renames the extra-data field before Ethereum's
    32-byte validation. Hash, timestamp, number and all state checks are retained.
    Also applies to Anvil forks, which can return the original Fuji header.
    """
    w3 = Web3(provider)
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def read_functions(w3, functions, block):
    if type(block) is not int or block < 0:
        raise ValueError("batch reads require an explicit block")
    functions = list(functions)
    with w3.batch_requests() as batch:
        for fn in functions:
            batch.add(fn.call(block_identifier=block))
        result = batch.execute()
    if len(result) != len(functions):
        raise ValueError("incomplete RPC batch")
    return result
