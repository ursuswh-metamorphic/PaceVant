from typing import Protocol

import httpx
from web3 import Web3
from web3.exceptions import Web3Exception

from app.attestor.typed import hash_bytes
from app.errors import ControlError
from app.models import ChainBalances, ChainContext
from treasury_contracts.client import ExecutionAPIError
from treasury_contracts.client import ExecutionClient as SharedClient
from treasury_contracts.models import (
    BuiltTransaction,
    ExecutionResult,
    ExecutionSubmission,
    SignedPDR,
    SimulationEvidence,
    TransactionProposal,
)
from treasury_contracts.models import (
    ChainContext as WireContext,
)
from treasury_contracts.onchain import read_approval_state

DOMAIN_ERRORS = {
    "TOKEN_NOT_ALLOWED",
    "ROUTER_NOT_ALLOWED",
    "BAD_RECIPIENT",
    "TRADE_SIZE_LIMIT",
    "DAILY_SPEND_LIMIT",
    "INSUFFICIENT_BALANCE",
    "BAD_PRICE_OR_SLIPPAGE",
    "POLICY_REVOKED",
    "HASH_MISMATCH",
    "SIMULATION_INCOMPLETE",
    "NONCE_REPLAY",
    "EXPIRED_APPROVAL",
    "STALE_REQUIRES_REEVALUATION",
    "BAD_SIGNATURE",
    "REQUIRED_STRESS_NOT_SATISFIED",
}
MAX_RESPONSE_BYTES = 1_048_576


class ExecutionClient(Protocol):
    def context(
        self, *, built: BuiltTransaction | None = None, fork_block: int | None = None
    ) -> ChainContext: ...
    def balances(self) -> ChainBalances: ...
    def build(self, proposal: TransactionProposal) -> BuiltTransaction: ...
    def simulate(self, built: BuiltTransaction) -> SimulationEvidence: ...
    def execute(self, built: BuiltTransaction, pdr: SignedPDR) -> ExecutionSubmission: ...
    def execution(self, tx_hash: str) -> ExecutionResult: ...


class WorkflowSDK(SharedClient):
    """Reuse A's connection pool and preserve the request ID and retry payload."""

    def __init__(self, http: httpx.Client, request_id: str):
        self.http = http
        self.request_id = request_id

    def _request(self, method, path, **options):
        headers = {"X-Request-ID": self.request_id, **options.pop("headers", {})}
        for attempt in range(2):
            try:
                with self.http.stream(method, path, headers=headers, **options) as response:
                    if response.status_code == 503 and attempt == 0:
                        continue
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ControlError("EXECUTION_PLANE_RESPONSE_TOO_LARGE", 503)
                        data.extend(chunk)
                    response = httpx.Response(
                        response.status_code,
                        content=bytes(data),
                        headers={"X-Request-ID": response.headers.get("X-Request-ID", "unknown")},
                        request=response.request,
                    )
                    if response.is_error:
                        raise ExecutionAPIError(response)
                    response.raise_for_status()
                    return response
            except httpx.RequestError:
                if attempt:
                    raise ControlError("EXECUTION_PLANE_UNAVAILABLE", 503, retryable=True) from None
        raise ControlError("EXECUTION_PLANE_UNAVAILABLE", 503, retryable=True)


class RestExecutionClient:
    def __init__(self, http, request_id, settings, store):
        self.sdk = WorkflowSDK(http, request_id)
        self.settings = settings
        self.store = store
        self.rpc = Web3(Web3.HTTPProvider(settings.chain_rpc_url, request_kwargs={"timeout": 3}))

    @staticmethod
    def _call(fn, *args):
        try:
            return fn(*args)
        except ExecutionAPIError as exc:
            code = exc.code if exc.code in DOMAIN_ERRORS else "EXECUTION_PLANE_UNAVAILABLE"
            raise ControlError(code, exc.status_code, exc.retryable) from None
        except (ValueError, KeyError, TypeError, httpx.HTTPError):
            raise ControlError("INVALID_EXECUTION_PLANE_RESPONSE", 503) from None

    def context(self, *, built=None, fork_block=None):
        remote = WireContext.model_validate(self._call(self.sdk.context))
        expected = 31337 if self.settings.mode == "LOCAL" else 43113
        if remote.chain_id != expected or remote.mode != self.settings.mode.lower():
            raise ControlError("CHAIN_MISMATCH")
        try:
            if self.rpc.eth.chain_id != remote.chain_id:
                raise ControlError("CHAIN_MISMATCH")
            block = self.rpc.eth.get_block(remote.block_number)
            if Web3.to_hex(block.hash) != remote.block_hash or block.timestamp != remote.timestamp:
                raise ControlError("HASH_MISMATCH")
            vault = Web3.to_checksum_address(remote.vault_address)
            code = self.rpc.eth.get_code(vault, block_identifier=remote.block_number)
            if not code:
                raise ControlError("HASH_MISMATCH")
            state = None
            if built is not None:
                if built.vault_address.lower() != remote.vault_address.lower():
                    raise ControlError("HASH_MISMATCH")
                state = read_approval_state(self.settings.chain_rpc_url, built, timeout=3)
                if (
                    state.policy_hash != remote.policy_hash
                    or state.policy_active != remote.policy_active
                    or state.policy_expires_at != remote.policy_expires_at
                    or state.paused != remote.paused
                    or state.attestor.lower() != remote.attestor.lower()
                    or state.bytecode_hash != hash_bytes(code)
                ):
                    raise ControlError("STALE_REQUIRES_REEVALUATION")
            fork = self.rpc.eth.get_block(fork_block) if fork_block is not None else None
            if fork is not None:
                fork_code = self.rpc.eth.get_code(vault, block_identifier=fork.number)
                if fork_code != code:
                    raise ControlError("HASH_MISMATCH")
        except (Web3Exception, OSError, ValueError):
            raise ControlError("CHAIN_RPC_UNAVAILABLE", 503, retryable=True) from None
        return ChainContext(
            deployment=self.settings.mode,
            chain_id=remote.chain_id,
            vault_address=remote.vault_address,
            owner=remote.owner,
            router=remote.router,
            token_in=remote.token_in,
            token_out=remote.token_out,
            token_in_decimals=6,
            token_out_decimals=18,
            policy_hash=remote.policy_hash,
            policy_version=remote.policy_version,
            policy_active=remote.policy_active,
            policy_expires_at=remote.policy_expires_at,
            paused=remote.paused,
            attestor=remote.attestor,
            relayer=self.settings.relayer_address,
            block_number=state.block_number if state is not None else remote.block_number,
            block_timestamp=state.timestamp if state is not None else remote.timestamp,
            bytecode_hash=hash_bytes(code),
            fork_block=fork_block,
            fork_block_hash=Web3.to_hex(fork.hash) if fork is not None else None,
            fork_block_timestamp=fork.timestamp if fork is not None else None,
            nonce_used=state.nonce_used if state is not None else None,
            max_usdc_per_swap_base_units=remote.max_per_swap_base_units,
            max_usdc_spend_per_day_base_units=remote.max_spend_per_day_base_units,
            max_slippage_bps=remote.max_slippage_bps,
            max_approval_ttl=remote.max_approval_ttl,
        )

    def balances(self):
        remote = self._call(self.sdk.snapshot)
        try:
            block = self.rpc.eth.get_block(remote["block_number"])
            if (
                Web3.to_hex(block.hash) != remote["block_hash"]
                or block.timestamp != remote["timestamp"]
            ):
                raise ControlError("HASH_MISMATCH")
            price = self.rpc.eth.gas_price
        except (Web3Exception, OSError, ValueError):
            raise ControlError("CHAIN_RPC_UNAVAILABLE", 503, retryable=True) from None
        fields = (
            "chain_id",
            "vault_address",
            "policy_hash",
            "block_number",
            "usdc_base_units",
            "wavax_base_units",
            "utc_day",
            "daily_spent_usdc_base_units",
        )
        spent_wei = self.store.execution_gas_spent(
            remote["chain_id"], remote["vault_address"].lower(), remote["utc_day"]
        )
        return ChainBalances(
            **{field: remote[field] for field in fields},
            block_timestamp=remote["timestamp"],
            max_fee_per_gas_wei=str(price),
            daily_execution_cost_wei=str(spent_wei),
            daily_execution_cost_usd_e8="0",
        )

    def build(self, proposal):
        return self._call(self.sdk.build, proposal, f"build-{proposal.intent_id}")

    def simulate(self, built):
        return self._call(self.sdk.simulate, built, f"simulate-{built.build_id}")

    def verify_evidence(self, built, evidence):
        return self.sdk.verify_evidence(built, evidence)

    def execute(self, built, pdr):
        key = f"execute-{pdr.decision_id}"
        response = self._call(self.sdk.execute, built.build_id, pdr, key)
        return ExecutionSubmission.model_validate(response)

    def execution(self, tx_hash):
        return self._call(self.sdk.result, tx_hash)

    def execution_fee(self, receipt):
        try:
            raw = self.rpc.eth.get_transaction_receipt(receipt.tx_hash)
            block = self.rpc.eth.get_block(receipt.block_number)
            if (
                raw.blockHash != block.hash
                or raw.blockNumber != receipt.block_number
                or raw.gasUsed != int(receipt.gas_used)
                or raw.status != (1 if receipt.status == "CONFIRMED" else 0)
                or raw["from"].lower() != self.settings.relayer_address.lower()
            ):
                raise ControlError("RECEIPT_MISMATCH")
            return block.timestamp // 86400, str(raw.gasUsed * raw.effectiveGasPrice)
        except (Web3Exception, OSError, ValueError):
            raise ControlError("CHAIN_RPC_UNAVAILABLE", 503, retryable=True) from None
