from eth_abi import encode as abi_encode
from eth_keys import keys
from eth_utils import keccak

from treasury_contract.wire import Approval, BuiltTransaction, Domain

APPROVAL_TYPE = (
    "Approval(bytes32 policyHash,bytes32 evidenceRoot,address router,address tokenIn,"
    "address tokenOut,uint256 amountIn,uint256 minAmountOut,bytes32 calldataHash,"
    "uint256 nonce,uint256 deadline)"
)
DOMAIN_TYPES = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]
DOMAIN_TYPE = "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"


def hash_bytes(value: bytes) -> str:
    return f"0x{keccak(value).hex()}"


def approval_for(built: BuiltTransaction, evidence_root: str) -> Approval:
    return Approval(
        policyHash=built.policy_hash,
        evidenceRoot=evidence_root,
        router=built.router,
        tokenIn=built.token_in,
        tokenOut=built.token_out,
        amountIn=built.amount_in_base_units,
        minAmountOut=built.min_amount_out_base_units,
        calldataHash=built.calldata_hash,
        nonce=built.nonce,
        deadline=str(built.deadline),
    )


def typed_data(domain: Domain, approval: Approval) -> dict:
    members = APPROVAL_TYPE.removeprefix("Approval(").removesuffix(")").split(",")
    return {
        "types": {
            "EIP712Domain": DOMAIN_TYPES,
            "Approval": [
                {"name": name, "type": kind}
                for kind, name in (member.split() for member in members)
            ],
        },
        "primaryType": "Approval",
        "domain": domain.model_dump(),
        "message": approval.model_dump(),
    }


def digest(domain: Domain, approval: Approval) -> bytes:
    data = typed_data(domain, approval)
    domain_separator = keccak(
        abi_encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [
                keccak(text=DOMAIN_TYPE),
                keccak(text=domain.name),
                keccak(text=domain.version),
                domain.chainId,
                domain.verifyingContract,
            ],
        )
    )
    types = ["bytes32"]
    values = [keccak(text=APPROVAL_TYPE)]
    for member in data["types"]["Approval"]:
        kind, value = member["type"], data["message"][member["name"]]
        types.append(kind)
        if kind == "bytes32":
            value = bytes.fromhex(value[2:])
        elif kind == "uint256":
            value = int(value)
        values.append(value)
    struct_hash = keccak(abi_encode(types, values))
    return keccak(b"\x19\x01" + domain_separator + struct_hash)


def sign_digest(key: keys.PrivateKey, message_hash: bytes) -> str:
    signature = key.sign_msg_hash(message_hash).to_bytes()
    return "0x" + (signature[:64] + bytes([signature[64] + 27])).hex()


def recover_signer(message_hash: bytes, signature: str) -> str:
    raw = bytes.fromhex(signature[2:])
    if len(raw) != 65 or raw[-1] not in (27, 28):
        raise ValueError("invalid Ethereum signature")
    normalized = keys.Signature(signature_bytes=raw[:64] + bytes([raw[-1] - 27]))
    return normalized.recover_public_key_from_msg_hash(message_hash).to_address()
