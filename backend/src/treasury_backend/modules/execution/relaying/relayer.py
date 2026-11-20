import json
import time
import warnings
from eth_account import Account
from web3 import Web3
from web3.exceptions import TransactionNotFound
from treasury_backend.modules.execution.chain import plain
from treasury_backend.modules.execution.crypto import (
    approval_for,
    approval_tuple,
    canonical,
    content_hash,
    digest,
    domain_for,
    recover,
)
from treasury_backend.modules.execution.errors import PlaneError
from treasury_backend.modules.execution.dex.lfj import ADAPTER_VERSION
from treasury_backend.modules.execution.evidence.extractor import token_facts
from treasury_backend.modules.execution.models import (
    BuiltTransaction,
    ExecutionRequest,
    ExecutionResult,
    SimulationEvidence,
)
from treasury_contracts.v2 import (
    SignedPDRV2,
    ApprovalV2,
    DomainV2,
    digest_v2,
    message_v2,
    keccak as v2_keccak,
)


class Relayer:
    def __init__(self, chain, store):
        self.chain, self.store = chain, store
        self.gas_credit = None

    def execute(self, request: ExecutionRequest, *, dry_run=False):
        if self.chain.w3.eth.chain_id != self.chain.chain_id:
            raise PlaneError("CHAIN_MISMATCH", "RPC network changed", 503)
        b = BuiltTransaction.model_validate(self.store.get("build", request.build_id))
        billed = self.gas_credit is not None and self.gas_credit.billed(b.build_id)
        from treasury_contracts.oracle import CIRCLE_USDC, SOURCE_HASH, WAVAX

        if (b.adapter_version == ADAPTER_VERSION or self.chain.deployment.get("lfj_route")) and (
            (b.token_in.lower(), b.token_out.lower()) != (CIRCLE_USDC, WAVAX)
            or self.chain.context().get("proof_policy", {}).get("oracle_source_hash") != SOURCE_HASH
        ):
            # Reference observations are not authoritative valuations for LFJ faucet assets.
            raise PlaneError(
                "ORACLE_TOKEN_IDENTITY_MISMATCH",
                "LFJ execution needs an independent valuation for its exact test assets",
                409,
            )
        p = request.signed_pdr
        is_v2 = isinstance(p, SignedPDRV2)
        c = self.chain.context()
        if bool(c.get("proof_policy")) != is_v2:
            raise PlaneError(
                "PROOF_REQUIRED", "Deployment requires its configured PDR version", 409
            )
        request_hash = content_hash(request.model_dump())
        # Durable raw transaction journal BEFORE broadcasting; retry broadcasts the same signed bytes.
        with self.store.db() as db:
            row = db.execute(
                "SELECT request_hash,tx_hash,raw_tx,value FROM submissions WHERE build_id=?",
                (b.build_id,),
            ).fetchone()
        if row:
            if row[0] != request_hash:
                raise PlaneError("NONCE_REPLAY", "Build already submitted with another PDR", 409)
            if dry_run:
                return {"dry_run": True, "broadcast": False, **self.monitor(row[1])}
            if billed:
                # Demo retries are read-only. An absent receipt is not permission
                # to resend or spend additional gas; retain the same hash/hold.
                return {"tx_hash": row[1], "status": self.monitor(row[1])["status"]}
            try:
                self.chain.w3.eth.get_transaction(row[1])
            except TransactionNotFound:
                try:
                    self.chain.w3.eth.send_raw_transaction(Web3.to_bytes(hexstr=row[2]))
                except Exception:
                    # Original hash remains queryable even if rebroadcast times out.
                    pass
            return {"tx_hash": row[1], "status": self.monitor(row[1])["status"]}
        evidence = SimulationEvidence.model_validate(self.store.get("evidence", b.build_id))
        if is_v2:
            expected = ApprovalV2(
                intentHash=v2_keccak(b.intent_id.encode()),
                calldataHash=b.calldata_hash,
                policyHash=b.policy_hash,
                evidenceRoot=evidence.evidence_root,
                proofContextHash=p.approval.proofContextHash,
                postConditionsHash=p.phi.hash,
                sessionId=c["proof_session"]["session_id"],
                riskDebitUsdE8=p.approval.riskDebitUsdE8,
                nonce=b.nonce,
                deadline=str(b.deadline),
                adapter=b.router,
                tokenIn=b.token_in,
                tokenOut=b.token_out,
                amountIn=b.amount_in_base_units,
                minAmountOut=b.min_amount_out_base_units,
            )
            expected_domain = DomainV2(chainId=b.chain_id, verifyingContract=b.vault_address)
            if p.approval != expected or p.domain != expected_domain or evidence.effects_v2 is None:
                raise PlaneError(
                    "HASH_MISMATCH", "V2 PDR differs from immutable build/evidence/Phi", 409
                )
            actual_digest = digest_v2(p.domain, p.approval)
        else:
            actual_digest = digest(p.domain, p.approval)
        if (
            evidence.verification_status != "COMPLETE"
            or evidence.baseline.execution_status != "SUCCESS"
        ):
            raise PlaneError("SIMULATION_INCOMPLETE", "Complete successful evidence required", 409)
        if self.chain.settings.mode == "fuji" and evidence.source != "FORK_SIM":
            raise PlaneError("SIMULATION_INCOMPLETE", "Fuji requires verified fork evidence", 409)
        if p.build_id != b.build_id or (
            not is_v2
            and (
                # EIP-712 encodes address bytes; checksum/lowercase spelling is equivalent.
                digest(p.domain, p.approval)
                != digest(domain_for(b), approval_for(b, evidence.evidence_root))
            )
        ):
            raise PlaneError(
                "HASH_MISMATCH",
                "PDR must match immutable build and evidence exactly",
                409,
            )
        if actual_digest != p.typed_data_hash:
            raise PlaneError("BAD_SIGNATURE", "Typed-data digest mismatch")
        c = self.chain.context()
        manifest = json.loads(self.store.read_artifact(evidence.evidence_root[2:]))
        stale = (
            c["policy_hash"] != b.policy_hash
            or not c["policy_active"]
            or c["paused"]
            or c["timestamp"] > b.deadline
            or int(time.time()) > b.deadline
            or c["policy_expires_at"] < c["timestamp"]
            or c["block_number"] - evidence.fork_block > self.chain.settings.max_block_drift
            or max(c["timestamp"], int(time.time())) - manifest["timestamp"]
            > self.chain.settings.freshness_seconds
            or Web3.to_hex(self.chain.w3.eth.get_block(evidence.fork_block).hash)
            != manifest["fork_block_hash"]
            or self.chain.vault.functions.usedNonce(int(b.nonce)).call()
        )
        if stale:
            raise PlaneError(
                "STALE_REQUIRES_REEVALUATION",
                "Chain context changed; rebuild, simulate and re-attest",
                409,
            )
        try:
            signer = (
                Account.recover_message(message_v2(p.domain, p.approval), signature=p.signature)
                if is_v2
                else recover(p.domain, p.approval, p.signature)
            )
        except Exception:
            raise PlaneError("BAD_SIGNATURE", "Invalid EIP-712 signature") from None
        if signer.lower() != c["attestor"].lower():
            raise PlaneError("BAD_SIGNATURE", "Signature is not from current attestor")
        key = self.chain.settings.relayer_private_key.get_secret_value()
        if not key:
            raise PlaneError(
                "CONFIGURATION_ERROR",
                f"B_{self.chain.settings.mode.upper()}_RELAYER_PRIVATE_KEY is not configured",
                503,
            )
        account = Account.from_key(key)
        if account.address.lower() in {c["owner"].lower(), c["attestor"].lower()}:
            raise PlaneError(
                "CONFIGURATION_ERROR",
                "Relayer must be distinct from owner and attestor",
                503,
            )
        fn = (
            self.chain.vault.functions.executeApprovedSwapV2(
                p.approval.abi_tuple, b.router_calldata, p.phi.abi_tuple, p.signature
            )
            if is_v2
            else self.chain.vault.functions.executeApprovedSwap(
                approval_tuple(p.approval), b.router_calldata, p.signature
            )
        )
        try:
            gas = fn.estimate_gas({"from": account.address})
        except Exception:
            raise PlaneError(
                "STALE_REQUIRES_REEVALUATION",
                "On-chain preflight failed; review policy, budget, minOut and nonce",
                409,
            ) from None
        if dry_run:
            return {
                "dry_run": True,
                "broadcast": False,
                "status": "PREFLIGHT_PASSED",
                "build_id": b.build_id,
                "gas_estimate": str(gas),
            }
        tx = fn.build_transaction(
            {
                "from": account.address,
                "chainId": b.chain_id,
                "nonce": self.store.transaction_nonce(account.address, self.chain.w3.eth.get_transaction_count(account.address, "pending")),
                "gas": (gas * 110 + 99) // 100 + 5000 if billed else gas * 12 // 10 + 10000,
                "gasPrice": self.chain.w3.eth.gas_price,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = Web3.to_hex(signed.hash)
        raw = Web3.to_hex(signed.raw_transaction)
        result = ExecutionResult(
            build_id=b.build_id,
            decision_id=p.decision_id,
            chain_id=b.chain_id,
            tx_hash=tx_hash,
            status="SUBMITTED",
        ).model_dump()
        self.store.put("execution", tx_hash, result)
        self.store.put("submitted-pdr", tx_hash, p.model_dump())
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if billed:
                self.gas_credit.reserve(
                    db, b.build_id, tx_hash, tx["gas"] * tx["gasPrice"],
                    self.chain.w3.eth.get_balance(account.address, "pending"),
                )
            db.execute(
                "INSERT INTO submissions VALUES(?,?,?,?,?)",
                (b.build_id, request_hash, tx_hash, raw, canonical(result).decode()),
            )
        try:
            self.chain.w3.eth.send_raw_transaction(signed.raw_transaction)
        except Exception:
            return {"tx_hash": tx_hash, "status": "PENDING"}
        return {"tx_hash": tx_hash, "status": "SUBMITTED"}

    def monitor(self, tx_hash):
        base = self.store.get("execution", tx_hash)
        try:
            receipt = self.chain.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return {**base, "status": "PENDING"}
        canonical_block = self.chain.w3.eth.get_block(receipt.blockNumber)
        if canonical_block.hash != receipt.blockHash:
            return {**base, "status": "PENDING"}
        if (
            self.chain.w3.eth.block_number - receipt.blockNumber + 1
            < self.chain.settings.required_confirmations
        ):
            return {**base, "status": "PENDING"}
        b = BuiltTransaction.model_validate(self.store.get("build", base["build_id"]))
        route = self.chain.deployment.get("lfj_route") if b.adapter_version == ADAPTER_VERSION else None
        facts = token_facts(
            receipt,
            b.vault_address,
            b.router,
            b.token_in,
            b.token_out,
            int(b.amount_in_base_units),
            int(b.min_amount_out_base_units),
            dex_route=route,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            events = self.chain.vault.events.SwapExecuted().process_receipt(receipt)
        p = self.store.get("submitted-pdr", tx_hash)
        is_v2 = p.get("domain", {}).get("version") == "2"
        matching = [
            e
            for e in events
            if (
                e["address"].lower() == b.vault_address.lower()
                and e["args"]["nonce"] == int(b.nonce)
                and Web3.to_hex(e["args"]["policyHash"]) == b.policy_hash
                and Web3.to_hex(e["args"]["evidenceRoot"]) == p["approval"]["evidenceRoot"]
                and e["args"]["tokenIn"].lower() == b.token_in.lower()
                and e["args"]["tokenOut"].lower() == b.token_out.lower()
                and e["args"]["amountIn"] == int(b.amount_in_base_units)
                and e["args"]["amountOut"] == int(facts["token_out_delta_base_units"])
            )
        ]
        mismatch = receipt.status == 1 and (
            len(matching) != 1 or facts["unexpected_transfer"] or facts["unauthorized_approval"]
        )
        if route and receipt.status == 1:
            self.chain.verify_lfj(receipt.blockNumber)
            mismatch |= (
                not self.chain.vault.functions.usedNonce(int(b.nonce)).call(block_identifier=receipt.blockNumber)
                or self.chain.usdc.functions.allowance(b.vault_address, b.router).call(block_identifier=receipt.blockNumber) != 0
                or self.chain.usdc.functions.allowance(
                    b.router, Web3.to_checksum_address(route["lfj_router"])
                ).call(block_identifier=receipt.blockNumber) != 0
            )
        proof_state = None
        if is_v2 and receipt.status == 1:
            signed = SignedPDRV2.model_validate(p)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                commitments = self.chain.vault.events.ProofCommitted().process_receipt(receipt)
            commits = [e["args"] for e in commitments if e["args"]["nonce"] == int(b.nonce)]
            if len(commits) != 1:
                mismatch = True
            else:
                a = commits[0]
                reverse = b.token_in.lower() == self.chain.wavax.address.lower()
                di, do = (
                    (a["wavaxDelta"], a["usdcDelta"])
                    if reverse
                    else (a["usdcDelta"], a["wavaxDelta"])
                )
                mismatch |= (
                    di != int(facts["token_in_delta_base_units"])
                    or do != int(facts["token_out_delta_base_units"])
                    or Web3.to_hex(a["sessionId"]) != signed.approval.sessionId
                    or Web3.to_hex(a["proofContextHash"]) != signed.approval.proofContextHash
                    or Web3.to_hex(a["postConditionsHash"]) != signed.phi.hash
                    or a["riskDebitUsdE8"] != int(signed.approval.riskDebitUsdE8)
                )
                from treasury_contracts.onchain_v2 import read_v2_context

                proof_state = read_v2_context(
                    self.chain.w3,
                    b.vault_address,
                    signed.approval.sessionId,
                    receipt.blockNumber,
                    required=True,
                )["proof_session"]
                mismatch |= int(proof_state["used_usd_e8"]) < int(signed.approval.riskDebitUsdE8)
        protected = None
        if receipt.status == 0:
            try:
                trace = self.chain.w3.provider.make_request(
                    "debug_traceTransaction", [tx_hash, {"tracer": "callTracer"}]
                )["result"]
                selectors = {
                    v2_keccak(name.encode())[:10]: reason
                    for name, reason in (
                        ("PostConditionFailed()", "POSTCONDITION_FAILED"),
                        ("MinOutputNotMet()", "MIN_OUTPUT_NOT_MET"),
                        ("SessionRiskLimit()", "SESSION_RISK_LIMIT"),
                        ("GlobalRiskLimit()", "GLOBAL_RISK_LIMIT"),
                    )
                }
                protected = selectors.get(trace.get("output", "")[:10])
            except Exception:
                pass
        ref = self.store.artifact(
            {
                "receipt": plain(receipt),
                "events": plain(events),
                "facts": facts,
                "actual_delta_source": "RECEIPT_ERC20_TRANSFER_LOGS",
                "review_required": mismatch,
                "recommended_action": "PAUSE_REVIEW" if mismatch else None,
            }
        )
        return ExecutionResult(
            **{
                **base,
                "status": "CONFIRMED" if receipt.status == 1 else "REVERTED",
                "block_number": receipt.blockNumber,
                "block_hash": Web3.to_hex(receipt.blockHash),
                "confirmations": self.chain.w3.eth.block_number - receipt.blockNumber + 1,
                "proof_session": proof_state,
                "gas_used": str(receipt.gasUsed),
                "actual_token_in_delta_base_units": facts["token_in_delta_base_units"],
                "actual_token_out_delta_base_units": facts["token_out_delta_base_units"],
                "revert_reason": "CRITICAL_MISMATCH_PAUSE_REVIEW"
                if mismatch
                else protected or "ONCHAIN_REVERT"
                if receipt.status == 0
                else None,
                "event_refs": ["SwapExecuted"] if matching else [],
                "artifact_refs": [ref["ref"]],
            }
        ).model_dump()

    def reconciliation(self, tx_hash):
        from treasury_contracts.outcomes import verify_outcome
        from treasury_contracts.outcomes_v2 import parse_pdr
        from treasury_contracts.readonly import readonly_web3

        base = self.store.get("execution", tx_hash)
        built = BuiltTransaction.model_validate(self.store.get("build", base["build_id"]))
        pdr = parse_pdr(self.store.get("submitted-pdr", tx_hash))
        saved = self.store.get("build-context", built.build_id)
        evidence = self.store.get("evidence", built.build_id)
        reader = readonly_web3(self.chain.settings.rpc_url, built.chain_id)
        try:
            report = verify_outcome(
                reader, built, pdr, tx_hash,
                expected_relayer=self.chain.deployment["relayer"],
                expected_attestor=saved["context"]["attestor"],
                bytecode_hash=evidence["bytecode_hash"],
                evidence_root=evidence["evidence_root"],
            )
        finally:
            reader.provider.close()
        if (
            report.verification_status == "VERIFIED"
            and report.confirmations < self.chain.settings.required_confirmations
        ):
            report = report.model_copy(update={
                "verification_status": "PENDING",
                "reason_codes": ["INSUFFICIENT_CONFIRMATIONS"],
            })
        ref = self.store.artifact(report.model_dump())
        return report.model_copy(update={"artifact_refs": [ref["ref"]]}).model_dump()

    def submission_for_build(self, build_id):
        with self.store.db() as db:
            row = db.execute(
                "SELECT tx_hash FROM submissions WHERE build_id=?", (build_id,)
            ).fetchone()
        if row is None:
            raise PlaneError("NOT_FOUND", "No durable submission is known for this build", 404)
        value = self.store.get("execution", row[0])
        return {"tx_hash": row[0], "status": value["status"]}
