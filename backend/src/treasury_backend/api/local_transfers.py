"""Execution primitives injected into the LOCAL payment coordinator by the app composition."""

from treasury_backend.modules.execution.chain import contract
from treasury_backend.modules.execution.simulation.runner import fork_node, override_attestor, rpc


class LocalTransferExecution:
    def __init__(self, runtime):
        self.runtime = runtime

    def token_contract(self, w3, name, address):
        return contract(w3, name, address)

    def simulation_fork(self, settings, block, chain_id):
        return fork_node(settings, block, chain_id)

    def simulation_attestor(self, w3, vault, signer):
        return override_attestor(w3, vault, signer)

    def simulation_rpc(self, w3, method, arguments):
        return rpc(w3, method, arguments)
