from collections import deque
from threading import Lock
from time import monotonic

from eth_keys import keys

from app.attestor.typed import approval_for, digest, sign_digest
from app.errors import ControlError
from app.storage import Store
from treasury_contract.wire import BuiltTransaction, Domain, SecurityDecision, SignedPDR


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
    ) -> tuple[SignedPDR, int]:
        verify()
        now = self.clock()
        if not now < decision.expires_at == built.deadline <= now + 30:
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        if decision.simulation_evidence_root is None:
            raise ControlError("SIMULATION_INCOMPLETE")
        domain = Domain(verifyingContract=built.vault_address, chainId=built.chain_id)
        approval = approval_for(built, decision.simulation_evidence_root)
        message_hash = digest(domain, approval)
        return SignedPDR(
            decision_id=decision.decision_id,
            build_id=built.build_id,
            domain=domain,
            approval=approval,
            signature=sign_digest(self._key, message_hash),
            typed_data_hash=f"0x{message_hash.hex()}",
        ), now
