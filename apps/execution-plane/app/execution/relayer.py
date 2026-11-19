import json
import time
from eth_account import Account
from web3 import Web3
from web3.exceptions import TransactionNotFound
from ..crypto import (
    approval_for,
    approval_tuple,
    canonical,
    content_hash,
    digest,
    domain_for,
    recover,
)
from ..errors import PlaneError
from ..models import (
    BuiltTransaction,
    ExecutionRequest,
    ExecutionResult,
    SimulationEvidence,
)


class Relayer:
    def __init__(self, chain, store):
        self.chain, self.store = chain, store

    def execute(self, request: ExecutionRequest, *, dry_run=False):
        if self.chain.w3.eth.chain_id != self.chain.chain_id:
            raise PlaneError("CHAIN_MISMATCH", "RPC network changed", 503)
        if (
            self.chain.settings.mode == "fuji"
            and not dry_run
            and not self.chain.settings.fuji_broadcast_authorized
        ):
            raise PlaneError(
                "BROADCAST_NOT_AUTHORIZED",
                "Fuji execution is disabled until explicitly authorized",
                403,
            )
        b = BuiltTransaction.model_validate(self.store.get("build", request.build_id))
        p = request.signed_pdr
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
                return {
                    "dry_run": True,
                    "broadcast": False,
                    "tx_hash": row[1],
                    "status": self.monitor(row[1])["status"],
                }
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
        if (
            evidence.verification_status != "COMPLETE"
            or evidence.baseline.execution_status != "SUCCESS"
        ):
            raise PlaneError("SIMULATION_INCOMPLETE", "Complete successful evidence required", 409)
        if self.chain.settings.mode == "fuji" and evidence.source != "FORK_SIM":
            raise PlaneError("SIMULATION_INCOMPLETE", "Fuji requires verified fork evidence", 409)
        if (
            p.build_id != b.build_id
            # EIP-712 encodes address bytes; checksum/lowercase spelling is equivalent.
            or digest(p.domain, p.approval)
            != digest(domain_for(b), approval_for(b, evidence.evidence_root))
        ):
            raise PlaneError(
                "HASH_MISMATCH",
                "PDR must match immutable build and evidence exactly",
                409,
            )
        if digest(p.domain, p.approval) != p.typed_data_hash:
            raise PlaneError("BAD_SIGNATURE", "Typed-data digest mismatch")
        c = self.chain.context()
        if self.chain.is_lfj:
            from ..dex.lfj import LFJClient

            route = self.chain.verify_lfj(c["block_number"])
            current_quote = LFJClient(self.chain.w3).verified_quote(
                int(b.amount_in_base_units), c["block_number"], route
            )
            if int(current_quote["amount_out_base_units"]) < int(b.min_amount_out_base_units):
                raise PlaneError(
                    "STALE_REQUIRES_REEVALUATION", "LFJ quote moved below signed minOut", 409
                )
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
            signer = recover(p.domain, p.approval, p.signature)
        except Exception:
            raise PlaneError("BAD_SIGNATURE", "Invalid EIP-712 signature") from None
        if signer.lower() != c["attestor"].lower():
            raise PlaneError("BAD_SIGNATURE", "Signature is not from current attestor")
        key = self.chain.settings.relayer_private_key.get_secret_value()
        if not key and not dry_run:
            raise PlaneError(
                "CONFIGURATION_ERROR",
                f"B_{self.chain.settings.mode.upper()}_RELAYER_PRIVATE_KEY is not configured",
                503,
            )
        account = Account.from_key(key) if key else None
        sender = account.address if account else self.chain.deployment.get("relayer")
        if not sender or sender.lower() in {c["owner"].lower(), c["attestor"].lower()}:
            raise PlaneError(
                "CONFIGURATION_ERROR",
                "Relayer must be distinct from owner and attestor",
                503,
            )
        fn = self.chain.vault.functions.executeApprovedSwap(
            approval_tuple(p.approval), b.router_calldata, p.signature
        )
        try:
            gas = fn.estimate_gas({"from": sender})
        except Exception:
            raise PlaneError(
                "STALE_REQUIRES_REEVALUATION",
                "On-chain preflight failed; review policy, budget, minOut and nonce",
                409,
            ) from None
        tx = fn.build_transaction(
            {
                "from": sender,
                "chainId": b.chain_id,
                "nonce": self.chain.w3.eth.get_transaction_count(sender, "pending"),
                "gas": gas * 12 // 10 + 10000,
                "gasPrice": self.chain.w3.eth.gas_price,
            }
        )
        if dry_run:
            return {
                "dry_run": True,
                "broadcast": False,
                "status": "PREFLIGHT_PASSED",
                "build_id": b.build_id,
                "relayer": sender,
                "gas_estimate": str(gas),
                "evidence_root": evidence.evidence_root,
                "typed_data_hash": p.typed_data_hash,
                "quote_ref": b.quote_ref,
                "block_number": c["block_number"],
            }
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
            db.execute(
                "INSERT INTO submissions VALUES(?,?,?,?,?)",
                (b.build_id, request_hash, tx_hash, raw, canonical(result).decode()),
            )
        try:
            self.chain.w3.eth.send_raw_transaction(signed.raw_transaction)
        except Exception:
            return {"tx_hash": tx_hash, "status": "PENDING"}
        return {"tx_hash": tx_hash, "status": "SUBMITTED"}

    def reconciliation(self, tx_hash):
        from treasury_contracts.models import SignedPDR
        from treasury_contracts.outcomes import verify_outcome
        from treasury_contracts.readonly import readonly_web3

        base = self.store.get("execution", tx_hash)
        built = BuiltTransaction.model_validate(self.store.get("build", base["build_id"]))
        pdr = SignedPDR.model_validate(self.store.get("submitted-pdr", tx_hash))
        saved = self.store.get("build-context", built.build_id)
        evidence = self.store.get("evidence", built.build_id)
        reader = readonly_web3(self.chain.settings.rpc_url, built.chain_id)
        try:
            report = verify_outcome(reader, built, pdr, tx_hash,
                expected_relayer=self.chain.deployment["relayer"],
                expected_attestor=saved["context"]["attestor"],
                bytecode_hash=evidence["bytecode_hash"], evidence_root=evidence["evidence_root"])
        finally:
            reader.provider.close()
        ref = self.store.artifact(report.model_dump())
        return report.model_copy(update={"artifact_refs":[ref["ref"]]}).model_dump()

    def submission_for_build(self, build_id):
        with self.store.db() as db:
            row = db.execute("SELECT tx_hash FROM submissions WHERE build_id=?",(build_id,)).fetchone()
        if row is None:
            raise PlaneError("NOT_FOUND", "No durable submission is known for this build", 404)
        value=self.store.get("execution",row[0])
        return {"tx_hash":row[0],"status":value["status"]}

    def monitor(self, tx_hash):
        report = self.reconciliation(tx_hash)
        base = self.store.get("execution", tx_hash)
        status = report["receipt_status"]
        if status not in {"SUCCESS","REVERTED"} or not report["canonical"]:
            return {**base,"status":"PENDING"}
        mismatch = report["verification_status"]!="VERIFIED"
        return ExecutionResult(**{**base,"status":"CONFIRMED" if status=="SUCCESS" else "REVERTED",
            "block_number":report["block_number"],"gas_used":report["gas_used"],
            "actual_token_in_delta_base_units":report["token_in_delta_base_units"],
            "actual_token_out_delta_base_units":report["token_out_delta_base_units"],
            "revert_reason":"CRITICAL_MISMATCH_PAUSE_REVIEW" if mismatch else "ONCHAIN_REVERT" if status=="REVERTED" else None,
            "event_refs":["SwapExecuted"] if report["swap_events"] else [],
            "artifact_refs":report["artifact_refs"]}).model_dump()
