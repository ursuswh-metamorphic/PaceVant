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
from treasury_contracts.readonly import ReadError, readonly_web3

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
    "NO_LIQUIDITY",
    "LFJ_UNSUPPORTED_ROUTE",
    "LFJ_QUOTE_MISMATCH",
    "LFJ_INVALID_ROUTE",
    "LFJ_CALL_FAILED",
    "LFJ_CONTRACT_MISSING",
    "TOKEN_DECIMALS_MISMATCH",
    "BROADCAST_NOT_AUTHORIZED",
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
        self.rpc = readonly_web3(
            settings.chain_rpc_url, 31337 if settings.mode == "LOCAL" else 43113, seconds=180
        )

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
            from app.portfolio.observations import OracleBridge

            bridge = OracleBridge(self.rpc, {"number": remote.block_number}, remote.timestamp)
            try:
                decimals = [
                    bridge.eth_call(token, "decimals()", returns=("uint8",))[0]
                    for token in (remote.token_in, remote.token_out)
                ]
                actual_tokens = [
                    bridge.eth_call(vault, name, returns=("address",))[0].lower()
                    for name in ("usdc()", "wavax()")
                ]
            except Exception:
                raise ControlError("TOKEN_METADATA_UNAVAILABLE", 503) from None
            if decimals != [6, 18] or actual_tokens != [
                remote.token_in.lower(),
                remote.token_out.lower(),
            ]:
                raise ControlError("TOKEN_DECIMALS_OR_IDENTITY_MISMATCH")
            state = None
            if built is not None:
                if built.vault_address.lower() != remote.vault_address.lower():
                    raise ControlError("HASH_MISMATCH")
                state = read_approval_state(
                    self.settings.chain_rpc_url, built, timeout=3, block_number=remote.block_number
                )
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
        except (Web3Exception, OSError, ValueError, ReadError):
            raise ControlError("CHAIN_RPC_UNAVAILABLE", 503, retryable=True) from None
        return ChainContext(
            deployment=self.settings.mode,
            chain_id=remote.chain_id,
            vault_address=remote.vault_address,
            owner=remote.owner,
            router=remote.router,
            token_in=remote.token_in,
            token_out=remote.token_out,
            token_in_decimals=decimals[0],
            token_out_decimals=decimals[1],
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
        except (Web3Exception, OSError, ValueError, ReadError):
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
            remote["chain_id"],
            remote["vault_address"].lower(),
            remote["utc_day"],
            self.settings.mode,
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

    def submission_for_build(self, build_id):
        try:
            return self.sdk.submission_for_build(build_id)
        except ExecutionAPIError as error:
            if error.status_code == 404:
                return None
            raise ControlError("EXECUTION_PLANE_UNAVAILABLE", 503, retryable=True) from None

    def observe(self, mandate, *, block_number=None, history_version=0, include_oracles=False):
        from app.portfolio.observations import PortfolioReader

        return PortfolioReader(self.settings.mode, self.settings.chain_rpc_url).collect(
            mandate.vault_address,
            mandate=mandate,
            block_number=block_number,
            history_version=history_version,
            independent_reader=lambda n: self._call(self.sdk.snapshot, n),
            include_oracles=include_oracles,
        )

    def reconciliation(self, built, pdr, tx_hash, *, context=None, evidence=None):
        from treasury_contracts.outcomes import verify_outcome
        from treasury_contracts.readonly import readonly_web3

        reader = readonly_web3(self.settings.chain_rpc_url, built.chain_id)
        try:
            local = verify_outcome(
                reader,
                built,
                pdr,
                tx_hash,
                expected_relayer=self.settings.relayer_address,
                expected_attestor=context.attestor if context else None,
                bytecode_hash=evidence.bytecode_hash if evidence else None,
                evidence_root=evidence.evidence_root if evidence else None,
            )
        finally:
            reader.provider.close()
        # Compare two independently read reports; confirmation depth/observation time can differ.
        remote = self._call(self.sdk.reconciliation, tx_hash)
        keys = (
            "chain_id",
            "vault_address",
            "build_id",
            "decision_id",
            "tx_hash",
            "receipt_status",
            "canonical",
            "block_hash",
            "gas_used",
            "effective_gas_price_wei",
            "token_in_delta_base_units",
            "token_out_delta_base_units",
            "nonce_used",
            "allowances",
        )
        if local.verification_status == "VERIFIED" and any(
            getattr(local, k) != getattr(remote, k) for k in keys
        ):
            return local.model_copy(
                update={
                    "verification_status": "MISMATCH",
                    "reason_codes": ["INDEPENDENT_OUTCOME_MISMATCH"],
                }
            )
        return local

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
        except (Web3Exception, OSError, ValueError, ReadError):
            raise ControlError("CHAIN_RPC_UNAVAILABLE", 503, retryable=True) from None
