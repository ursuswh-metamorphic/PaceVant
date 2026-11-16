import json
import time
import warnings
from eth_account import Account
from web3 import Web3
from web3.exceptions import TransactionNotFound
from ..chain import plain
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
from ..evidence.extractor import token_facts
from ..models import (
    BuiltTransaction,
    ExecutionRequest,
    ExecutionResult,
    SimulationEvidence,
)


class Relayer:
    def __init__(self, chain, store):
        self.chain, self.store = chain, store

    def execute(self, request: ExecutionRequest):
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
                raise PlaneError(
                    "NONCE_REPLAY", "Build already submitted with another PDR", 409
                )
            try:
                self.chain.w3.eth.get_transaction(row[1])
            except TransactionNotFound:
                try:
                    self.chain.w3.eth.send_raw_transaction(Web3.to_bytes(hexstr=row[2]))
                except Exception:
                    # Original hash remains queryable even if rebroadcast times out.
                    pass
            return {"tx_hash": row[1], "status": self.monitor(row[1])["status"]}
        evidence = SimulationEvidence.model_validate(
            self.store.get("evidence", b.build_id)
        )
        if (
            evidence.verification_status != "COMPLETE"
            or evidence.baseline.execution_status != "SUCCESS"
        ):
            raise PlaneError(
                "SIMULATION_INCOMPLETE", "Complete successful evidence required", 409
            )
        if self.chain.settings.mode == "fuji" and evidence.source != "FORK_SIM":
            raise PlaneError(
                "SIMULATION_INCOMPLETE", "Fuji requires verified fork evidence", 409
            )
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
        manifest = json.loads(self.store.read_artifact(evidence.evidence_root[2:]))
        stale = (
            c["policy_hash"] != b.policy_hash
            or not c["policy_active"]
            or c["paused"]
            or c["timestamp"] > b.deadline
            or int(time.time()) > b.deadline
            or c["policy_expires_at"] < c["timestamp"]
            or c["block_number"] - evidence.fork_block
            > self.chain.settings.max_block_drift
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
        fn = self.chain.vault.functions.executeApprovedSwap(
            approval_tuple(p.approval), b.router_calldata, p.signature
        )
        try:
            gas = fn.estimate_gas({"from": account.address})
        except Exception:
            raise PlaneError(
                "STALE_REQUIRES_REEVALUATION",
                "On-chain preflight failed; review policy, budget, minOut and nonce",
                409,
            ) from None
        tx = fn.build_transaction(
            {
                "from": account.address,
                "chainId": b.chain_id,
                "nonce": self.chain.w3.eth.get_transaction_count(
                    account.address, "pending"
                ),
                "gas": gas * 12 // 10 + 10000,
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
        b = BuiltTransaction.model_validate(self.store.get("build", base["build_id"]))
        facts = token_facts(
            receipt,
            b.vault_address,
            b.router,
            b.token_in,
            b.token_out,
            int(b.amount_in_base_units),
            int(b.min_amount_out_base_units),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            events = self.chain.vault.events.SwapExecuted().process_receipt(receipt)
        p = self.store.get("submitted-pdr", tx_hash)
        matching = [
            e
            for e in events
            if (
                e["address"].lower() == b.vault_address.lower()
                and e["args"]["nonce"] == int(b.nonce)
                and Web3.to_hex(e["args"]["policyHash"]) == b.policy_hash
                and Web3.to_hex(e["args"]["evidenceRoot"])
                == p["approval"]["evidenceRoot"]
            )
        ]
        mismatch = receipt.status == 1 and (
            len(matching) != 1
            or facts["unexpected_transfer"]
            or facts["unauthorized_approval"]
        )
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
                "gas_used": str(receipt.gasUsed),
                "actual_token_in_delta_base_units": facts["token_in_delta_base_units"],
                "actual_token_out_delta_base_units": facts[
                    "token_out_delta_base_units"
                ],
                "revert_reason": "CRITICAL_MISMATCH_PAUSE_REVIEW"
                if mismatch
                else "ONCHAIN_REVERT"
                if receipt.status == 0
                else None,
                "event_refs": ["SwapExecuted"] if matching else [],
                "artifact_refs": [ref["ref"]],
            }
        ).model_dump()
