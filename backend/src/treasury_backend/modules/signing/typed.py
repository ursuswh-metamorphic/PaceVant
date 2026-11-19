from eth_keys import keys
from eth_utils import keccak


def hash_bytes(value: bytes) -> str:
    return f"0x{keccak(value).hex()}"


def sign_digest(key: keys.PrivateKey, message_hash: bytes) -> str:
    signature = key.sign_msg_hash(message_hash).to_bytes()
    return "0x" + (signature[:64] + bytes([signature[64] + 27])).hex()
