from uuid import uuid4

import rfc8785
from eth_abi import encode as abi_encode
from eth_utils import keccak

from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import ChainBalances, ChainContext, EvidenceReport, Manifest
from treasury_backend.modules.oracle.models import OraclePrice
from treasury_backend.modules.signing.typed import hash_bytes
from treasury_contracts.crypto import approval_for, recover
from treasury_contracts.models import (
    Baseline,
    BuiltTransaction,
    ExecutionResult,
    ExecutionSubmission,
    SimulationEvidence,
    StressTest,
)

# Placeholder adapter ABI is scoped to the mock. B owns the real adapter and exact calldata.
SELECTOR = keccak(text="swapExactInput(address,address,uint256,uint256,address,uint256)")[:4]
BLOCK = 12345678
BYTECODE = hash_bytes(b"pacevant mock vault placeholder")


class MockExecutionClient:
    def __init__(self, mandate, signer, fixture, clock):
        self.mandate = mandate
        self.signer = signer
        self.clock = clock
        self.fixture = fixture
        self.artifacts = {}
        self.simulations = {}
        self.builds = {}
        self.receipts = {}
        self.used_nonces = set()
        self.usdc = int(fixture["usdc_base_units"])
        self.wavax = int(fixture["wavax_base_units"])
        self.spent = int(fixture.get("daily_spent_usdc_base_units", "0"))
        self.daily_cost = 0
        self.block = BLOCK
        self.idempotent_executions = {}
        self.policy_changed = False
        self.block_times = {BLOCK: clock()}

    def context(self, *, built=None, fork_block=None):
        m = self.mandate
        return ChainContext(
            deployment="MOCK",
            chain_id=m.chain_id,
            vault_address=m.vault_address,
            owner=m.owner,
            router=m.router,
            token_in=m.token_in,
            token_out=m.token_out,
            token_in_decimals=6,
            token_out_decimals=18,
            policy_hash=hash_bytes(b"revoked") if self.policy_changed else m.policy_hash,
            policy_version=m.version,
            policy_expires_at=m.expires_at,
            max_slippage_bps=m.max_slippage_bps,
            paused=False,
            attestor=self.signer,
            relayer="0x" + "55" * 20,
            block_number=self.block,
            block_timestamp=self.clock(),
            fork_block=fork_block,
            fork_block_hash=self.block_hash(fork_block) if fork_block is not None else None,
            fork_block_timestamp=self.block_times.get(fork_block),
            nonce_used=built.nonce in self.used_nonces if built is not None else None,
            bytecode_hash=BYTECODE,
            max_usdc_per_swap_base_units=m.max_usdc_per_swap_base_units,
            max_usdc_spend_per_day_base_units=m.max_usdc_spend_per_day_base_units,
        )

    @staticmethod
    def block_hash(block):
        return hash_bytes(f"mock block {block}".encode())

    def balances(self):
        context = self.context()
        return ChainBalances(
            chain_id=context.chain_id,
            vault_address=context.vault_address,
            policy_hash=context.policy_hash,
            block_number=self.block,
            block_timestamp=context.block_timestamp,
            usdc_base_units=str(self.usdc),
            wavax_base_units=str(self.wavax),
            utc_day=self.clock() // 86400,
            daily_spent_usdc_base_units=str(self.spent),
            daily_execution_cost_usd_e8=str(self.daily_cost),
            max_fee_per_gas_wei="25000000000",
        )

    def price(self):
        return OraclePrice(
            chain_id=self.mandate.chain_id,
            vault_address=self.mandate.vault_address,
            price_usdc_usd_e8="100000000",
            price_wavax_usd_e8="2000000000",
            price_source="TRUSTED_TEST_ORACLE",
            price_timestamp=self.clock() - self.fixture.get("price_age_seconds", 0),
        )

    def build(self, proposal):
        build_id = f"build_{uuid4().hex}"
        amount = int(proposal.amount_in_base_units)
        out = amount * 10**12 // 20
        min_out = out * (10_000 - proposal.slippage_bps) // 10_000
        nonce = str(uuid4().int)
        calldata = SELECTOR + abi_encode(
            ["address", "address", "uint256", "uint256", "address", "uint256"],
            [
                proposal.token_in,
                proposal.token_out,
                amount,
                min_out,
                proposal.recipient,
                proposal.deadline,
            ],
        )
        built = BuiltTransaction(
            build_id=build_id,
            intent_id=proposal.intent_id,
            chain_id=proposal.chain_id,
            vault_address=proposal.vault_address,
            router=proposal.router,
            token_in=proposal.token_in,
            token_out=proposal.token_out,
            amount_in_base_units=str(amount),
            min_amount_out_base_units=str(min_out),
            router_calldata=f"0x{calldata.hex()}",
            calldata_hash=hash_bytes(calldata),
            policy_hash=self.mandate.policy_hash,
            nonce=nonce,
            deadline=proposal.deadline,
            quote_ref=f"quote_{uuid4().hex}",
            adapter_version="mock-swap-v1",
        )
        self.builds[built.build_id] = built
        return built

    def simulate(self, built):
        root = f"artifact://simulation/{built.build_id}"
        report_ref, manifest_ref = f"{root}/report.json", f"{root}/manifest.json"
        out = int(built.amount_in_base_units) * 10**12 // 20
        report = EvidenceReport(
            intent_id=built.intent_id,
            build_id=built.build_id,
            nonce=built.nonce,
            deadline=built.deadline,
            simulation_mode="LOCAL_TEST_ATTESTOR",
            source="MOCK_FIXTURE",
            baseline=Baseline(
                execution_status="SUCCESS",
                token_in_delta_base_units=f"-{built.amount_in_base_units}",
                token_out_delta_base_units=str(out),
                unexpected_transfer=False,
                unauthorized_approval=False,
                gas_used="210000",
            ),
            stress_tests=[
                StressTest(
                    scenario_id="reserve_shift_mild",
                    status="SUCCESS_SAFE",
                    scenario_hash=hash_bytes(b"mock reserve_shift_mild"),
                    output_base_units=str(
                        max(int(built.min_amount_out_base_units), out * 999 // 1000)
                    ),
                ),
                StressTest(
                    scenario_id="reserve_shift_adverse",
                    status="PROTECTED_REVERT",
                    scenario_hash=hash_bytes(b"mock reserve_shift_adverse"),
                    revert_reason="MIN_OUTPUT_NOT_MET",
                ),
            ],
        )
        report_bytes = rfc8785.dumps(report.model_dump())
        manifest = Manifest(
            chain_id=built.chain_id,
            vault_address=built.vault_address,
            policy_hash=built.policy_hash,
            calldata_hash=built.calldata_hash,
            fork_block=self.block,
            fork_block_hash=self.block_hash(self.block),
            fork_block_timestamp=self.block_times[self.block],
            bytecode_hash=BYTECODE,
            parser_version="extractor-v1",
            verification_status="COMPLETE",
            artifact_hashes={report_ref: hash_bytes(report_bytes)},
        )
        manifest_bytes = rfc8785.dumps(manifest.model_dump())
        self.artifacts.update({report_ref: report_bytes, manifest_ref: manifest_bytes})
        evidence = SimulationEvidence(
            schema_version="1.1",
            **report.model_dump(),
            **manifest.model_dump(
                exclude={
                    "artifact_hashes",
                    "fork_block_hash",
                    "fork_block_timestamp",
                }
            ),
            artifact_refs=[report_ref],
            evidence_manifest_ref=manifest_ref,
            evidence_root=hash_bytes(manifest_bytes),
        )
        self.simulations[built.build_id] = evidence
        return evidence

    def artifact(self, reference):
        if reference not in self.artifacts:
            raise ControlError("SIMULATION_INCOMPLETE")
        return self.artifacts[reference]

    def execute(self, built, pdr):
        if pdr.decision_id in self.idempotent_executions:
            return self.idempotent_executions[pdr.decision_id]
        context = self.context(built=built)
        if context.nonce_used:
            raise ControlError("NONCE_REPLAY")
        if context.policy_hash != built.policy_hash or built.deadline <= self.clock():
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        original = self.builds.get(built.build_id)
        evidence = self.simulations.get(built.build_id)
        if (
            original != built
            or evidence is None
            or pdr.build_id != built.build_id
            or pdr.domain.verifyingContract != built.vault_address
            or pdr.approval != approval_for(built, evidence.evidence_root)
            or recover(pdr.domain, pdr.approval, pdr.signature).lower() != self.signer
        ):
            raise ControlError("BAD_SIGNATURE")
        amount = int(built.amount_in_base_units)
        if amount > min(
            self.usdc, int(self.mandate.max_usdc_per_swap_base_units)
        ) or self.spent + amount > int(self.mandate.max_usdc_spend_per_day_base_units):
            raise ControlError("TRADE_SIZE_LIMIT")
        out = int(evidence.baseline.token_out_delta_base_units)
        self.usdc -= amount
        self.wavax += out
        self.spent += amount
        self.daily_cost += 10_500_000
        self.used_nonces.add(built.nonce)
        self.block += 1
        self.block_times[self.block] = self.clock()
        tx_hash = hash_bytes(f"mock receipt {pdr.decision_id}".encode())
        self.receipts[tx_hash] = ExecutionResult(
            build_id=built.build_id,
            decision_id=pdr.decision_id,
            chain_id=built.chain_id,
            tx_hash=tx_hash,
            status="CONFIRMED",
            block_number=self.block,
            gas_used="210000",
            actual_token_in_delta_base_units=str(-amount),
            actual_token_out_delta_base_units=str(out),
            event_refs=["SwapExecuted"],
        )
        response = ExecutionSubmission(tx_hash=tx_hash, status="SUBMITTED")
        self.idempotent_executions[pdr.decision_id] = response
        return response

    def execution(self, tx_hash):
        if tx_hash not in self.receipts:
            raise ControlError("EXECUTION_NOT_FOUND", 404)
        return self.receipts[tx_hash]
