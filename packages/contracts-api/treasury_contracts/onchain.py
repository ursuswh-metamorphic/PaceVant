"""Read-only Vault preflight for A. No signing, submission or owner operations."""

import json
from importlib.resources import files

from web3 import Web3

from .crypto import keccak
from .models import ApprovalChainState, BuiltTransaction


def vault_abi():
    return json.loads(
        files("treasury_contracts")
        .joinpath("abi/PolicyVault.json")
        .read_text(encoding="utf-8")
    )


def read_approval_state(
    rpc_url: str, build: BuiltTransaction, timeout: int = 10, block_number: int | None = None
) -> ApprovalChainState:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
    if w3.eth.chain_id != build.chain_id:
        raise ValueError("RPC chain does not match build")
    block = w3.eth.get_block(block_number if block_number is not None else "latest")
    code = w3.eth.get_code(Web3.to_checksum_address(build.vault_address), block.number)
    if not code:
        raise ValueError("Vault is not deployed on this RPC")
    vault = w3.eth.contract(
        address=Web3.to_checksum_address(build.vault_address), abi=vault_abi()
    )

    def call(name, *args):
        return getattr(vault.functions, name)(*args).call(block_identifier=block.number)

    return ApprovalChainState(
        chain_id=build.chain_id,
        vault_address=build.vault_address,
        block_number=block.number,
        block_hash=Web3.to_hex(block.hash),
        timestamp=block.timestamp,
        policy_hash=Web3.to_hex(call("activePolicyHash")),
        policy_active=call("policyActive"),
        policy_expires_at=call("policyExpiresAt"),
        paused=call("paused"),
        attestor=call("attestor"),
        nonce=build.nonce,
        nonce_used=call("usedNonce", int(build.nonce)),
        bytecode_hash=keccak(code),
    )
