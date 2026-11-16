"""Shared RFC 8785 and exact EIP-712 helpers for both A and B."""

import rfc8785
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from .models import Approval, BuiltTransaction, Domain

APPROVAL_FIELDS = [
    ("policyHash", "bytes32"),
    ("evidenceRoot", "bytes32"),
    ("router", "address"),
    ("tokenIn", "address"),
    ("tokenOut", "address"),
    ("amountIn", "uint256"),
    ("minAmountOut", "uint256"),
    ("calldataHash", "bytes32"),
    ("nonce", "uint256"),
    ("deadline", "uint256"),
]


def canonical(value) -> bytes:
    return rfc8785.dumps(value)


def keccak(data: bytes) -> str:
    return Web3.to_hex(Web3.keccak(data))


def content_hash(value) -> str:
    return keccak(canonical(value))


def approval_for(b: BuiltTransaction, root: str) -> Approval:
    return Approval(
        policyHash=b.policy_hash,
        evidenceRoot=root,
        router=b.router,
        tokenIn=b.token_in,
        tokenOut=b.token_out,
        amountIn=b.amount_in_base_units,
        minAmountOut=b.min_amount_out_base_units,
        calldataHash=b.calldata_hash,
        nonce=b.nonce,
        deadline=str(b.deadline),
    )


def domain_for(b: BuiltTransaction) -> Domain:
    return Domain(
        name="TreasuryPolicyVault",
        version="1",
        chainId=b.chain_id,
        verifyingContract=b.vault_address,
    )


def message(domain: Domain, approval: Approval):
    values = approval.model_dump()
    for name, kind in APPROVAL_FIELDS:
        if kind == "uint256":
            values[name] = int(values[name])
    return encode_typed_data(
        domain_data=domain.model_dump(),
        message_types={
            "Approval": [{"name": n, "type": t} for n, t in APPROVAL_FIELDS]
        },
        message_data=values,
    )


def digest(domain: Domain, approval: Approval) -> str:
    msg = message(domain, approval)
    return keccak(b"\x19" + msg.version + msg.header + msg.body)


def approval_tuple(a: Approval):
    return tuple(
        int(getattr(a, n))
        if t == "uint256"
        else Web3.to_checksum_address(getattr(a, n))
        if t == "address"
        else getattr(a, n)
        for n, t in APPROVAL_FIELDS
    )


def recover(domain: Domain, approval: Approval, signature: str):
    return Account.recover_message(message(domain, approval), signature=signature)
