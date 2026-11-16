"""Every run is an isolated, pinned Anvil fork. No writes to the source RPC."""

import socket
import subprocess
import time
from contextlib import contextmanager
from eth_account import Account
from web3 import Web3
from ..chain import artifact, contract, plain
from ..crypto import (
    approval_for,
    content_hash,
    domain_for,
    keccak,
    message,
    approval_tuple,
)
from ..errors import PlaneError
from ..models import Baseline, BuiltTransaction, SimulationEvidence, StressTest
from ..evidence.extractor import assess, token_facts


def rpc(w3, method, params):
    result = w3.provider.make_request(method, params)
    if "error" in result:
        raise RuntimeError(f"{method}: {result['error'].get('message', 'RPC error')}")
    return result["result"]


@contextmanager
def fork_node(settings, block, chain_id):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    args = [
        settings.anvil_binary,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--silent",
        "--fork-url",
        settings.rpc_url,
        "--fork-block-number",
        str(block),
        "--chain-id",
        str(chain_id),
        "--hardfork",
        "cancun",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        w3 = Web3(
            Web3.HTTPProvider(
                f"http://127.0.0.1:{port}",
                request_kwargs={"timeout": settings.rpc_timeout},
            )
        )
        for _ in range(120):
            if proc.poll() is not None:
                raise PlaneError(
                    "SIMULATION_INCOMPLETE", "Anvil fork process failed", 503, True
                )
            if w3.is_connected():
                break
            time.sleep(0.1)
        else:
            raise PlaneError("SIMULATION_INCOMPLETE", "Anvil fork timed out", 503, True)
        yield w3
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def override_attestor(w3, vault, signer):
    # Use compiler storageLayout, preserving packed owner/pause/other fields.
    layout = next(
        x
        for x in artifact("PolicyVault")["storageLayout"]["storage"]
        if x["label"] == "attestor"
    )
    slot, offset = int(layout["slot"]), int(layout["offset"])
    old = int.from_bytes(w3.eth.get_storage_at(vault, slot), "big")
    mask = ((1 << 160) - 1) << (offset * 8)
    value = (old & ~mask) | (int(signer, 16) << (offset * 8))
    rpc(
        w3,
        "anvil_setStorageAt",
        [vault, hex(slot), "0x" + value.to_bytes(32, "big").hex()],
    )
    return {
        "kind": "ATTESTOR_STORAGE_ONLY",
        "slot": str(slot),
        "offset": offset,
        "previous_storage": "0x" + old.to_bytes(32, "big").hex(),
        "simulation_attestor": signer,
    }


class Simulator:
    def __init__(self, chain, store):
        self.chain, self.store = chain, store

    def simulate(self, build_id, expected_hash):
        b = BuiltTransaction.model_validate(self.store.get("build", build_id))
        saved = self.store.get("build-context", build_id)
        c = saved["context"]
        if (
            b.policy_hash != expected_hash
            or self.chain.context()["policy_hash"] != expected_hash
        ):
            raise PlaneError("HASH_MISMATCH", "Policy changed; rebuild required", 409)
        try:
            return self.store.get("evidence", build_id)
        except PlaneError as exc:
            if exc.code != "NOT_FOUND":
                raise
        refs, scenarios, complete = [], [], True
        with fork_node(self.chain.settings, c["block_number"], b.chain_id) as w3:
            vault = contract(w3, "PolicyVault", b.vault_address)
            router = contract(w3, "MockSwapAdapter", b.router)
            usdc, wavax = (
                contract(w3, "MockUSDC", b.token_in),
                contract(w3, "MockWAVAX", b.token_out),
            )
            for obj in (vault, router, usdc, wavax):
                if w3.eth.get_code(obj.address) != self.chain.w3.eth.get_code(
                    obj.address, c["block_number"]
                ):
                    raise PlaneError(
                        "SIMULATION_INCOMPLETE", "Fork bytecode mismatch", 503
                    )

            def balances():
                return {
                    "usdc_base_units": str(
                        usdc.functions.balanceOf(b.vault_address).call()
                    ),
                    "wavax_base_units": str(
                        wavax.functions.balanceOf(b.vault_address).call()
                    ),
                    "allowance_base_units": str(
                        usdc.functions.allowance(b.vault_address, b.router).call()
                    ),
                }

            if (
                balances() != {k: saved["snapshot"][k] for k in balances()}
                or Web3.to_hex(vault.functions.activePolicyHash().call())
                != b.policy_hash
                or str(router.functions.outputPerUsdc().call())
                != saved["output_per_usdc"]
                or Web3.to_hex(w3.eth.get_block(c["block_number"]).hash)
                != c["block_hash"]
            ):
                raise PlaneError(
                    "SIMULATION_INCOMPLETE",
                    "Fork state does not match committed snapshot",
                    503,
                )
            signer, relayer = Account.create(), Account.create()
            override = override_attestor(w3, b.vault_address, signer.address)
            if vault.functions.attestor().call() != signer.address:
                raise PlaneError("SIMULATION_INCOMPLETE", "Signer override failed", 503)
            rpc(w3, "anvil_setBalance", [relayer.address, hex(10**20)])
            # Root is a labelled simulation sentinel; the final evidence root is created after this run.
            approval = approval_for(b, content_hash({"simulation_only": b.build_id}))
            signature = Account.sign_message(
                message(domain_for(b), approval), signer.key
            ).signature
            encoded = vault.encode_abi(
                "executeApprovedSwap",
                args=[approval_tuple(approval), b.router_calldata, signature],
            )
            initial = rpc(w3, "evm_snapshot", [])
            for scenario_id, multiplier in [
                ("baseline", 10000),
                ("reserve_shift_mild", 9980),
                ("reserve_shift_adverse", 9800),
            ]:
                if scenario_id != "baseline":
                    if not rpc(w3, "evm_revert", [initial]):
                        raise PlaneError(
                            "SIMULATION_INCOMPLETE", "Snapshot restore failed", 503
                        )
                    initial = rpc(w3, "evm_snapshot", [])
                price = int(saved["output_per_usdc"]) * multiplier // 10000
                scenario = {
                    "scenario_id": scenario_id,
                    "price_multiplier_bps": multiplier,
                    "fork_block": c["block_number"],
                    "output_per_usdc": str(price),
                    "seed": 1,
                }
                if scenario_id != "baseline":
                    owner = router.functions.owner().call()
                    rpc(w3, "anvil_setBalance", [owner, hex(10**20)])
                    rpc(w3, "anvil_impersonateAccount", [owner])
                    # Mine setup and execution at the same pinned logical time, preserving TTL.
                    rpc(w3, "evm_setNextBlockTimestamp", [c["timestamp"] + 1])
                    tx = rpc(
                        w3,
                        "eth_sendTransaction",
                        [
                            {
                                "from": owner,
                                "to": b.router,
                                "data": router.encode_abi(
                                    "setOutputPerUsdc", args=[price]
                                ),
                                "gas": hex(150000),
                            }
                        ],
                    )
                    if w3.eth.wait_for_transaction_receipt(tx).status != 1:
                        raise PlaneError(
                            "SIMULATION_INCOMPLETE", "Stress setup failed", 503
                        )
                    rpc(w3, "anvil_stopImpersonatingAccount", [owner])
                before = balances()
                rpc(w3, "evm_setNextBlockTimestamp", [c["timestamp"] + 2])
                tx = {
                    "chainId": b.chain_id,
                    "nonce": w3.eth.get_transaction_count(relayer.address),
                    "to": b.vault_address,
                    "data": encoded,
                    "gas": 1500000,
                    "gasPrice": w3.eth.gas_price,
                }
                signed = relayer.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=15)
                after = balances()
                trace = rpc(
                    w3,
                    "debug_traceTransaction",
                    [Web3.to_hex(tx_hash), {"tracer": "callTracer"}],
                )
                facts = token_facts(
                    receipt,
                    b.vault_address,
                    b.router,
                    b.token_in,
                    b.token_out,
                    int(b.amount_in_base_units),
                    int(b.min_amount_out_base_units),
                )
                safe, rollback = assess(
                    receipt,
                    trace,
                    before,
                    after,
                    facts,
                    int(b.amount_in_base_units),
                    int(b.min_amount_out_base_units),
                )
                # Protected revert only when the encoded min-output failure is actually present in trace.
                min_selector = keccak(b"MinOutputNotMet()")[:10]

                def has_min_failure(node):
                    return str(node.get("output", ""))[:10] == min_selector or any(
                        has_min_failure(ch) for ch in node.get("calls", [])
                    )

                protected = rollback and has_min_failure(trace)
                status = (
                    "SUCCESS_SAFE"
                    if safe
                    else "PROTECTED_REVERT"
                    if protected
                    else "UNSAFE_EXECUTION"
                    if receipt.status
                    else "INCONCLUSIVE"
                )
                raw = {
                    "scenario": scenario,
                    "build": b.model_dump(),
                    "approval": approval.model_dump(),
                    "transaction": plain(w3.eth.get_transaction(tx_hash)),
                    "receipt": plain(receipt),
                    "trace": plain(trace),
                    "before": before,
                    "after": after,
                    "facts": facts,
                    "provenance": {
                        "source_rpc_block_hash": c["block_hash"],
                        "state_override": override,
                        "simulation_relayer": relayer.address,
                        "fidelity": "Pinned fork; signer and gas balances overridden; mock price stressed only in fork",
                    },
                }
                refs.append(self.store.artifact(raw))
                complete = complete and status not in {
                    "INCONCLUSIVE",
                    "UNSAFE_EXECUTION",
                }
                if scenario_id == "baseline":
                    baseline = Baseline(
                        execution_status="SUCCESS"
                        if safe
                        else "REVERTED"
                        if receipt.status == 0
                        else "INCONCLUSIVE",
                        token_in_delta_base_units=str(
                            int(after["usdc_base_units"])
                            - int(before["usdc_base_units"])
                        ),
                        token_out_delta_base_units=str(
                            int(after["wavax_base_units"])
                            - int(before["wavax_base_units"])
                        ),
                        unexpected_transfer=facts["unexpected_transfer"],
                        unauthorized_approval=facts["unauthorized_approval"],
                        gas_used=str(receipt.gasUsed),
                    )
                else:
                    scenarios.append(
                        StressTest(
                            scenario_id=scenario_id,
                            status=status,
                            scenario_hash=content_hash(scenario),
                            output_base_units=str(
                                int(after["wavax_base_units"])
                                - int(before["wavax_base_units"])
                            ),
                            revert_reason="MIN_OUTPUT_NOT_MET" if protected else None,
                        )
                    )
            bytecode_hash = keccak(w3.eth.get_code(b.vault_address))
        verification = (
            "COMPLETE"
            if complete and baseline.execution_status == "SUCCESS"
            else "INCONCLUSIVE"
        )
        manifest = {
            "schema_version": "1.1",
            "build_id": b.build_id,
            "intent_id": b.intent_id,
            "chain_id": b.chain_id,
            "vault_address": b.vault_address,
            "policy_hash": b.policy_hash,
            "calldata_hash": b.calldata_hash,
            "nonce": b.nonce,
            "deadline": b.deadline,
            "fork_block": c["block_number"],
            "fork_block_hash": c["block_hash"],
            "bytecode_hash": bytecode_hash,
            "deployment_bytecode_hashes": self.chain.deployment["bytecode_hashes"],
            "scenario_artifacts": refs,
            "parser_version": "extractor-v1",
            "verification_status": verification,
            "baseline": baseline.model_dump(),
            "stress_tests": [x.model_dump() for x in scenarios],
            "simulation_mode": "LOCAL_TEST_ATTESTOR",
            "source": "FORK_SIM"
            if self.chain.settings.mode == "fuji"
            else "REAL_LOCAL_SIM",
            "state_override": override,
            "created_at": int(time.time()),
            "timestamp": c["timestamp"],
        }
        manifest_ref = self.store.artifact(manifest)
        evidence = SimulationEvidence(
            intent_id=b.intent_id,
            build_id=b.build_id,
            chain_id=b.chain_id,
            vault_address=b.vault_address,
            policy_hash=b.policy_hash,
            calldata_hash=b.calldata_hash,
            nonce=b.nonce,
            deadline=b.deadline,
            fork_block=c["block_number"],
            bytecode_hash=bytecode_hash,
            simulation_mode="LOCAL_TEST_ATTESTOR",
            baseline=baseline,
            stress_tests=scenarios,
            verification_status=verification,
            source=manifest["source"],
            artifact_refs=[x["ref"] for x in refs],
            evidence_manifest_ref=manifest_ref["ref"],
            evidence_root=manifest_ref["content_hash"],
        )
        self.store.put("evidence", b.build_id, evidence.model_dump())
        return evidence.model_dump()
