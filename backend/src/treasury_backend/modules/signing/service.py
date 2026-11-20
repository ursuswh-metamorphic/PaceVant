from collections import deque
from threading import Lock
from time import monotonic

from eth_keys import keys

from treasury_backend.core.domain import SecurityDecision
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.persistence import Store
from treasury_backend.modules.signing.typed import sign_digest
from treasury_contracts.crypto import approval_for, digest, domain_for
from treasury_contracts.models import BuiltTransaction, SignedPDR
from treasury_contracts.v2 import (
    DomainV2,
    ProofArtifactV2,
    SessionContext,
    SignedPDRV2,
    approval_v2,
    call_hash,
    digest_v2,
    session_hash,
)


class Attestor:
    def __init__(self, store: Store, key: keys.PrivateKey, clock):
        self.store = store
        self._key = key
        self.clock = clock
        self.attempts: deque[float] = deque()
        self.rate_lock = Lock()

    @property
    def address(self):
        return self._key.public_key.to_address()

    def _check_rate(self):
        with self.rate_lock:
            now = monotonic()
            while self.attempts and now - self.attempts[0] >= 60:
                self.attempts.popleft()
            if len(self.attempts) >= 60:
                raise ControlError("ATTESTATION_RATE_LIMITED", 429, retryable=True)
            self.attempts.append(now)

    def attest_operation(self, intent, built, effects, context, proof, decision, revalidate):
        """Called only inside the durable V3 signing reservation, after all persisted gates."""
        from treasury_contracts.crypto import content_hash
        from treasury_contracts.proof_v3 import prove_operation
        from treasury_contracts.v3 import Constraints, Operation, operation_digest
        self._check_rate()
        if (decision["verdict"] != "APPROVE" or self.clock() >= decision["expires_at"]
                or decision["intent_hash"] != intent.hash or decision["build_hash"] != content_hash(built)
                or decision["evidence_root"] != content_hash(effects) or decision["proof_hash"] != proof["proof_hash"]):
            raise ControlError("DECISION_NOT_APPROVED", 403)
        revalidate()
        verified = prove_operation(intent, built, effects, context)
        if verified != proof:
            raise ControlError("PROOF_INVALID", 409)
        phi = Constraints.model_validate(proof["phi"])
        operation = Operation.model_validate(built["operation"] | {
            "evidenceRoot": proof["evidence_root"], "proofContextHash": proof["proof_hash"],
            "constraintsHash": phi.hash, "riskDebitUsdE8": proof["risk_debit_usd_e8"],
            "spendDebitUsdE8": proof["spend_debit_usd_e8"]})
        hash_ = operation_digest(intent.chain_id, intent.treasury, operation)
        return {"operation": operation.model_dump(mode="json"), "phi": phi.model_dump(mode="json"),
                "signature": sign_digest(self._key, bytes.fromhex(hash_[2:])), "typed_data_hash": hash_}

    def attest(self, id_, workflow_id, decision, built, scope, verify):
        self._check_rate()
        if decision.verdict != "APPROVE" or decision.decision_id != id_:
            raise ControlError("DECISION_NOT_APPROVED", 403)
        if self.clock() >= decision.expires_at:
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        return self.store.reserve_signature(
            id_=id_,
            workflow_id=workflow_id,
            scope=scope,
            nonce=built.nonce,
            now=self.clock(),
            expires_at=decision.expires_at,
            sign=lambda: self._sign_after_verification(decision, built, verify),
        )

    def _sign_after_verification(
        self, decision: SecurityDecision, built: BuiltTransaction, verify
    ) -> tuple[SignedPDR | SignedPDRV2, int]:
        verified = verify()
        now = self.clock()
        ttl = 30
        if isinstance(verified, tuple) and len(verified) == 3:
            verified, ttl = verified[:2], verified[2]
        if type(ttl) is not int or not 0 < ttl <= 300:
            raise ControlError("PROOF_INVALID")
        if not now < decision.expires_at == built.deadline <= now + ttl:
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        if decision.simulation_evidence_root is None:
            raise ControlError("SIMULATION_INCOMPLETE")
        if (
            decision.intent_id,
            decision.build_id,
            decision.policy_hash,
            decision.calldata_hash,
        ) != (built.intent_id, built.build_id, built.policy_hash, built.calldata_hash):
            raise ControlError("HASH_MISMATCH")
        if decision.source == "SDE_V2" or decision.proof_context_hash is not None:
            if not isinstance(verified, tuple) or len(verified) != 2:
                raise ControlError("PROOF_REQUIRED")
            proof, session = verified
            if (
                not isinstance(proof, ProofArtifactV2)
                or proof.status != "VERIFIED"
                or proof.context_hash != decision.proof_context_hash
                or not isinstance(session, SessionContext)
                or proof.session_context_hash != session_hash(session)
                or proof.exact_call_hash != call_hash(built)
                or (proof.check_mode, proof.compile_mode, proof.risk_bound)
                != ("UNSAT", "UNSAT", "UNSAT")
                or not proof.assumptions_satisfiable
                or not proof.compiled_region_satisfiable
            ):
                raise ControlError("PROOF_INVALID")
            approval = approval_v2(
                built, decision.simulation_evidence_root, proof, session.session_id
            )
            domain = DomainV2(chainId=built.chain_id, verifyingContract=built.vault_address)
            message_hash = digest_v2(domain, approval)
            return SignedPDRV2(
                decision_id=decision.decision_id,
                build_id=built.build_id,
                domain=domain,
                approval=approval,
                phi=proof.phi,
                signature=sign_digest(self._key, bytes.fromhex(message_hash[2:])),
                typed_data_hash=message_hash,
            ), now
        domain = domain_for(built)
        approval = approval_for(built, decision.simulation_evidence_root)
        message_hash = digest(domain, approval)
        return SignedPDR(
            decision_id=decision.decision_id,
            build_id=built.build_id,
            domain=domain,
            approval=approval,
            signature=sign_digest(self._key, bytes.fromhex(message_hash[2:])),
            typed_data_hash=message_hash,
        ), now
