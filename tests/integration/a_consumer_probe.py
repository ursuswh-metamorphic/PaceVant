"""Independent LOCAL TEST consumer: only the shared SDK, never B's app package.

This is a protocol probe, NOT A's Planner/SDE/production attestor. The caller must
provide an ephemeral local key via environment. It refuses every non-local chain.
"""

import json
import os
import sys
import time

from eth_account import Account
from web3 import Web3

from treasury_contracts import TransactionProposal, SignedPDR, Domain, Approval
from treasury_contracts.client import ExecutionAPIError, ExecutionClient
from treasury_contracts.crypto import approval_for, domain_for, message, digest
from treasury_contracts.onchain import read_approval_state


def main():
    with ExecutionClient(
        os.environ["CONSUMER_API_URL"],
        os.environ["CONSUMER_API_KEY"],
        request_id="independent_consumer_probe",
    ) as client:
        context = client.context()
        if context["mode"] != "local" or context["chain_id"] != 31337:
            raise RuntimeError("Protocol probe refuses non-local execution")
        before = client.snapshot()
        proposal = TransactionProposal(
            intent_id="consumer_probe",
            mandate_id="mandate_demo",
            mandate_version=1,
            action="SWAP_EXACT_INPUT",
            chain_id=context["chain_id"],
            vault_address=context["vault_address"],
            router=context["router"],
            token_in=context["token_in"],
            token_out=context["token_out"],
            amount_in_base_units="200000000",
            slippage_bps=40,
            recipient=context["vault_address"],
            deadline=min(int(time.time()), context["timestamp"]) + 25,
            user_goal_reason="TEST ONLY: independent consumer protocol acceptance",
        )
        build = client.build(proposal, "consumer:0:build")
        assert client.build(proposal, "consumer:0:build") == build
        evidence = client.simulate(build, "consumer:0:simulate")
        client.verify_evidence(build, evidence)
        assert (
            evidence.verification_status == "COMPLETE"
            and evidence.source == "REAL_LOCAL_SIM"
        )
        assert evidence.baseline.execution_status == "SUCCESS"
        assert (
            not evidence.baseline.unexpected_transfer
            and not evidence.baseline.unauthorized_approval
        )
        assert client.snapshot() == before
        # Controlled test oracle ONLY: price=20 USD/WAVAX, no fees. A owns real pricing/risk.
        projected_usdc = int(before["usdc_base_units"]) + int(
            evidence.baseline.token_in_delta_base_units
        )
        projected_wavax = int(before["wavax_base_units"]) + int(
            evidence.baseline.token_out_delta_base_units
        )
        usdc_usd_e8 = projected_usdc * 100000000 // 10**6
        wavax_usd_e8 = projected_wavax * 2000000000 // 10**18
        assert wavax_usd_e8 * 10000 <= (usdc_usd_e8 + wavax_usd_e8) * 2500
        state = read_approval_state(os.environ["CONSUMER_RPC_URL"], build)
        assert (
            state.policy_hash == build.policy_hash
            and state.policy_active
            and not state.paused
        )
        assert state.bytecode_hash == evidence.bytecode_hash and not state.nonce_used
        assert max(state.timestamp, int(time.time())) <= build.deadline
        # Sign exact committed fields, deliberately using lowercase EVM addresses.
        d = domain_for(build).model_dump()
        d["verifyingContract"] = d["verifyingContract"].lower()
        domain = Domain.model_validate(d)
        a = approval_for(build, evidence.evidence_root).model_dump()
        for field in ("router", "tokenIn", "tokenOut"):
            a[field] = a[field].lower()
        approval = Approval.model_validate(a)
        signed = Account.sign_message(
            message(domain, approval), os.environ["CONSUMER_TEST_ATTESTOR_KEY"]
        )
        assert (
            Account.from_key(os.environ["CONSUMER_TEST_ATTESTOR_KEY"]).address.lower()
            == state.attestor.lower()
        )
        pdr = SignedPDR(
            decision_id="LOCAL_PROTOCOL_PROBE_NOT_A_SDE",
            build_id=build.build_id,
            domain=domain,
            approval=approval,
            signature=Web3.to_hex(signed.signature),
            typed_data_hash=digest(domain, approval),
        )
        tampered = SignedPDR.model_validate(
            {
                **pdr.model_dump(),
                "approval": {**approval.model_dump(), "minAmountOut": "1"},
            }
        )
        try:
            client.execute(build.build_id, tampered, "consumer:0:tampered")
        except ExecutionAPIError as exc:
            assert (
                exc.code == "HASH_MISMATCH"
                and exc.status_code == 409
                and not exc.retryable
            )
            assert exc.correlation_id == "independent_consumer_probe"
        else:
            raise AssertionError("Tampered PDR was accepted")
        submission = client.execute(build.build_id, pdr, "consumer:0:execute")
        assert (
            client.execute(build.build_id, pdr, "consumer:0:execute")["tx_hash"]
            == submission["tx_hash"]
        )
        for _ in range(50):
            result = client.result(submission["tx_hash"])
            if result.status not in {"PENDING", "SUBMITTED"}:
                break
            time.sleep(0.1)
        assert result.status == "CONFIRMED"
        assert result.actual_token_in_delta_base_units == "-200000000"
        assert result.actual_token_out_delta_base_units == "10000000000000000000"
        assert read_approval_state(os.environ["CONSUMER_RPC_URL"], build).nonce_used
        assert "app" not in sys.modules, (
            "Consumer accidentally imported a backend app package"
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "consumer_mode": "ISOLATED_LOCAL_PROTOCOL_PROBE",
                    "a_implementation_exercised": False,
                    "backend_app_imported": False,
                    "sdk_only_http_pipeline": True,
                    "lowercase_eip712_addresses": True,
                    "manifest_and_artifacts_verified": True,
                    "readonly_nonce_preflight": True,
                    "tampered_approval_rejected": True,
                    "idempotent_submission": True,
                    "execution_status": result.status,
                }
            )
        )


if __name__ == "__main__":
    main()
