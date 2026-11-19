import httpx

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.portfolio import fresh, state_age
from treasury_backend.modules.signing.typed import hash_bytes

FUJI_RPC = "https://api.avax-test.network/ext/bc/C/rpc"


class FujiVerifier:
    def __init__(self, http: httpx.Client, rpc_url=FUJI_RPC):
        self.http = http
        self.rpc_url = rpc_url

    def verify(self, context, now):
        fork_block = hex(context.fork_block)
        calls = (
            ("eth_chainId", []),
            ("eth_getBlockByNumber", ["latest", False]),
            ("eth_getBlockByNumber", [fork_block, False]),
            ("eth_getCode", [context.vault_address, fork_block]),
            ("eth_getCode", [context.vault_address, "latest"]),
        )
        try:
            response = self.http.post(
                self.rpc_url,
                json=[
                    {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
                    for i, (method, params) in enumerate(calls)
                ],
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list) or len(data) != len(calls):
                raise ValueError("incorrect JSON-RPC batch length")
            results = {item["id"]: item["result"] for item in data}
            chain, head, fork, fork_code, current_code = (results[index] for index in range(5))
            fork_code_bytes = bytes.fromhex(fork_code.removeprefix("0x"))
            current_code_bytes = bytes.fromhex(current_code.removeprefix("0x"))
            head_block = int(head["number"], 16)
            fork_timestamp = int(fork["timestamp"], 16)
            if (
                int(chain, 16) != context.chain_id
                or int(fork["number"], 16) != context.fork_block
                or fork["hash"] != context.fork_block_hash
                or fork_timestamp != context.fork_block_timestamp
                or not 0 <= head_block - context.fork_block <= context.max_block_drift
                or not fresh(fork_timestamp, now, state_age(context))
                or not fork_code_bytes
                or hash_bytes(fork_code_bytes) != context.bytecode_hash
                or current_code_bytes != fork_code_bytes
            ):
                raise ControlError("FUJI_DEPLOYMENT_MISMATCH")
        except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
            raise ControlError("FUJI_RPC_UNVERIFIED", 503, retryable=True) from None
