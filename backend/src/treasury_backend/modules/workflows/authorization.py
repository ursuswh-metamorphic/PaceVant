from pydantic import ValidationError

from treasury_backend.core.domain import EconomicRiskAssessment, SecurityDecision
from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import Alignment, ChainBalances, Mandate
from treasury_backend.modules import decision as sde
from treasury_backend.modules import portfolio as portfolio
from treasury_backend.modules import proof as proof_service
from treasury_backend.modules import risk as economic_risk
from treasury_backend.modules.alignment.provider import inference_window
from treasury_backend.modules.alignment.runtime import ShieldRuntime
from treasury_backend.modules.temporal import storage as temporal_storage
from treasury_backend.modules.temporal.models import HybridTemporalAssessment
from treasury_backend.modules.workflows.evidence import verify_build
from treasury_backend.modules.workflows.mock import MockExecutionClient
from treasury_contracts.models import BuiltTransaction, SimulationEvidence, TransactionProposal
from treasury_contracts.v2 import ProofArtifactV2

from .context import ApprovedAttempt


class AuthorizationPipeline:
    def _approved(self, id_) -> ApprovedAttempt:
        workflow_id, bundle = self.store.decision(decision_id=id_)
        decision = SecurityDecision.model_validate(bundle["decision"])
        if self.settings.require_itag and not bundle.get("itag_assessment_hash"):
            raise ControlError("ITAG_APPROVAL_PROOF_REQUIRED", 403)
        if decision.verdict != "APPROVE" or decision.decision_id != id_:
            raise ControlError("DECISION_NOT_APPROVED", 403)
        if bundle["mode"] != self.settings.mode:
            raise ControlError("UNVERIFIED_SIMULATION_SOURCE", 403)
        if self.clock() >= decision.expires_at:
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        try:
            mandate = Mandate.model_validate(bundle["mandate"])
            proposal = TransactionProposal.model_validate(bundle["proposal"])
            aligned = Alignment.model_validate(bundle["alignment"])
            built = BuiltTransaction.model_validate(bundle["build"])
            sim = SimulationEvidence.model_validate(bundle["simulation"])
            risk = EconomicRiskAssessment.model_validate(bundle["risk"])
            snapshot = portfolio.parse_decision_snapshot(bundle["portfolio"])
            balances = ChainBalances.model_validate(bundle["chain_balances"])
        except (ValidationError, KeyError):
            raise ControlError("INVALID_APPROVAL_RECORD") from None
        if (
            (
                decision.intent_id,
                decision.build_id,
                decision.policy_hash,
                decision.calldata_hash,
                decision.simulation_evidence_root,
                decision.mandate_version,
                decision.snapshot_id,
            )
            != (
                proposal.intent_id,
                built.build_id,
                mandate.policy_hash,
                built.calldata_hash,
                sim.evidence_root,
                mandate.version,
                snapshot.snapshot_id,
            )
            or (risk.intent_id, risk.build_id, risk.snapshot_id)
            != (decision.intent_id, decision.build_id, decision.snapshot_id)
            or risk.result != "PASS"
            or aligned.verdict != "ALIGNED"
        ):
            raise ControlError("HASH_MISMATCH")
        return ApprovedAttempt(
            workflow_id,
            decision,
            mandate,
            proposal,
            aligned,
            built,
            sim,
            snapshot,
            balances,
            ProofArtifactV2.model_validate(bundle["proof"])
            if mandate.proof_policy and "proof" in bundle
            else None,
        )

    def _verify_approval(self, approved: ApprovedAttempt):
        mandate, built, sim = approved.mandate, approved.built, approved.evidence
        _, bundle = self.store.decision(decision_id=approved.decision.decision_id)
        temporal = None
        if bundle.get("itag_assessment_hash"):
            with self.store.connection() as conn:
                _, body, _ = temporal_storage.load(conn, bundle["itag_assessment_hash"])
            temporal = HybridTemporalAssessment.model_validate(body)
        proof = bundle.get("task_shield_proof")
        if self.shield.active or proof:
            if not proof or not proof.get("check_ids") or proof.get("unresolved_feedback"):
                raise ControlError("TASK_SHIELD_APPROVAL_PROOF_REQUIRED")
            from treasury_backend.modules.alignment.provider import safe_value

            if proof["proposal"] != safe_value(approved.proposal):
                raise ControlError("TASK_SHIELD_PROPOSAL_MISMATCH")
            self.shield.validate(proof["session_id"], proof["check_ids"], proof["revision"])
            from treasury_backend.modules.portfolio.observations import content_hash

            session = self.shield.state.session(proof["session_id"])
            if (
                session["mandate_hash"] != content_hash(mandate.model_dump())
                or session["workflow_id"] != approved.workflow_id
            ):
                raise ControlError("TASK_SHIELD_MANDATE_MISMATCH")
        snapshot = approved.snapshot
        self.require_priced_assets(mandate)
        if hasattr(snapshot, "observation_snapshot_id"):
            from treasury_backend.core.domain import ObservedPortfolioSnapshot
            from treasury_backend.modules.portfolio.observations import verify_snapshot_hash

            original = ObservedPortfolioSnapshot.model_validate(
                self.store.snapshot_record(snapshot.observation_snapshot_id)["snapshot"]
            )
            if (
                not verify_snapshot_hash(original)
                or original.content_hash != snapshot.observation_hash
            ):
                raise ControlError("SNAPSHOT_HASH_MISMATCH")
            if (
                self.store.history_version(
                    mandate.chain_id, mandate.vault_address, self.settings.mode
                )
                != snapshot.history_version
            ):
                raise ControlError("STALE_REQUIRES_REEVALUATION")
        if self.mandate(mandate.mandate_id) != mandate:
            raise ControlError("POLICY_REVOKED")
        client = self.client(approved.workflow_id, mandate)
        verify_build(mandate, approved.proposal, built)
        balances = client.balances()
        context = client.context(built=built, fork_block=sim.fork_block)
        fresh_observed = self.observe(
            client,
            mandate,
            balances,
            context,
            workflow_id=approved.workflow_id,
            built=built,
            decision_id=approved.decision.decision_id,
            phase="REVALIDATION",
            persist=False,
        )
        if hasattr(snapshot, "observation_snapshot_id") and not isinstance(
            client, MockExecutionClient
        ):
            header = client.rpc.eth.get_block(snapshot.block_number)
            if "0x" + header.hash.hex().removeprefix("0x") != snapshot.block_hash:
                raise ControlError("BLOCK_HASH_MISMATCH")
        if portfolio.policy_issues(mandate, context, self.clock()):
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        if (
            context.attestor != self.attestor.address
            or len({context.owner, context.relayer, context.attestor}) != 3
        ):
            raise ControlError("ATTESTOR_NOT_AUTHORIZED", 403)
        issues = self.verify_evidence(client, built, sim, context)
        price = self.price(client, sim.fork_block)
        if snapshot.oracle_feeds:
            # Re-read both pinned evidence and latest rounds. Changed rounds require a new proof.
            latest_price = self.price(client)
            if latest_price.oracle_feeds != snapshot.oracle_feeds or price.oracle_feeds != snapshot.oracle_feeds:
                raise ControlError("STALE_REQUIRES_REEVALUATION")
        balance_fields = (
            "usdc_base_units",
            "wavax_base_units",
            "daily_spent_usdc_base_units",
            "daily_execution_cost_usd_e8",
            "daily_execution_cost_wei",
            "utc_day",
        )
        if any(
            getattr(approved.balances, field) != getattr(balances, field)
            for field in balance_fields
        ) or (snapshot.price_usdc_usd_e8, snapshot.price_wavax_usd_e8) != (
            price.price_usdc_usd_e8,
            price.price_wavax_usd_e8,
        ):
            raise ControlError("STALE_REQUIRES_REEVALUATION")
        fresh_snapshot = portfolio.decision_snapshot(
            fresh_observed, balances, price, context, built, self.clock()
        )
        now = self.clock()
        if not portfolio.price_fresh(snapshot, now, portfolio.state_age(context)):
            raise ControlError("STALE_PRICE")
        risk = economic_risk.evaluate(
            mandate, approved.proposal, built, sim, fresh_snapshot, balances, context, now
        ).risk
        proof = None
        if mandate.proof_policy is not None:
            proof = proof_service.prove(
                mandate, built, sim, snapshot, context, now, self.store.proof_query
            )
            current = client.context(built=built)
            fields = (
                "session_id",
                "policy_hash",
                "starts_at",
                "expires_at",
                "active",
                "limit_usd_e8",
                "used_usd_e8",
                "global_limit_usd_e8",
                "global_used_usd_e8",
            )
            if (
                approved.proof is None
                or proof != approved.proof
                or proof.context_hash != approved.decision.proof_context_hash
                or current.proof_session is None
                or context.proof_session is None
                or any(
                    getattr(current.proof_session, f) != getattr(context.proof_session, f)
                    for f in fields
                )
                or current.proof_session.timestamp // 86400
                != context.proof_session.timestamp // 86400
            ):
                raise ControlError("PROOF_INVALID")
            client.preflight_v2(built, proof, mandate.session_id, mandate.required_stress)
        recomputed = sde.decide(
            mandate,
            approved.proposal,
            approved.alignment,
            context,
            now,
            built=built,
            evidence=sim,
            risk=risk,
            provenance_issues=issues,
            proof=proof,
            temporal=temporal,
        )
        if recomputed.verdict != "APPROVE" or now >= approved.decision.expires_at:
            raise ControlError(next(iter(recomputed.reason_codes), "STALE_REQUIRES_REEVALUATION"))
        return client, context

    def _verify_for_attestor(self, approved):
        _, context = self._verify_approval(approved)
        if approved.mandate.proof_policy is not None:
            return approved.proof, context.proof_session, context.max_approval_ttl
        return None

    def attest(self, id_):
        approved = self._approved(id_)
        mandate = approved.mandate
        scope = f"{self.settings.mode}:{mandate.chain_id}:{mandate.vault_address}"
        if self.settings.mode == "MOCK":
            scope += f":{approved.workflow_id}"
        return self.attestor.attest(
            id_,
            approved.workflow_id,
            approved.decision,
            approved.built,
            scope,
            lambda: self._verify_for_attestor(approved),
        )

    def _submit(self, workflow_id, decision, pdr):
        id_ = decision.decision_id
        try:
            approved = self._approved(id_)
            if self.clock() >= decision.expires_at:
                raise ControlError("STALE_REQUIRES_REEVALUATION")
        except ControlError as error:
            self.store.transition(
                workflow_id, id_, "ATTESTED", "EXPIRED", self.clock(), reason_codes=[error.code]
            )
            return
        built = approved.built
        # No LLM calls inside the attestor's SQLite reservation. The final write check is here,
        # before SUBMITTING and before client.execute, while deterministic verification remains intact.
        runtime = self.shield_runtimes.get(workflow_id)
        execute_call = None
        if self.shield.active:
            if runtime is None:
                session = self.shield.state.for_workflow(workflow_id)
                if not session:
                    raise ControlError("TASK_SHIELD_SESSION_NOT_FOUND")
                runtime = ShieldRuntime(self.shield, session["id"])
            try:
                with inference_window(decision.expires_at - self.clock()):
                    execute_call = runtime.before(
                        "execute_approved_swap",
                        {"build": built.model_dump(), "decision_id": id_},
                        approved.proposal.user_goal_reason,
                    )
                # A concurrent user cancellation invalidates the saved approval even if the model said yes.
                _, saved = self.store.decision(decision_id=id_)
                proof = saved["task_shield_proof"]
                self.shield.validate(proof["session_id"], proof["check_ids"], proof["revision"])
            except ControlError as error:
                self.store.transition(
                    workflow_id, id_, "ATTESTED", "EXPIRED", self.clock(), reason_codes=[error.code]
                )
                return
        try:
            # A final tool check can spend part of the signing window. Re-read
            # deterministic evidence after it finishes, immediately before submission.
            if self.clock() >= decision.expires_at:
                raise ControlError("STALE_REQUIRES_REEVALUATION")
            client, _ = self._verify_approval(approved)
            started = self.store.transition(
                workflow_id, id_, "ATTESTED", "SUBMITTING", self.clock()
            )
        except ControlError as error:
            self.store.transition(
                workflow_id, id_, "ATTESTED", "EXPIRED", self.clock(), reason_codes=[error.code]
            )
            return
        if not started:
            raise ControlError("SUBMISSION_ALREADY_STARTED")
        if self.clock() >= decision.expires_at:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "EXPIRED",
                self.clock(),
                reason_codes=["STALE_REQUIRES_REEVALUATION"],
            )
            return
        self.store.track_execution(workflow_id, id_, self.settings.mode, built, self.clock())
        try:
            submission = client.execute(built, pdr)
        except ControlError as error:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "SUBMITTING",
                self.clock(),
                reason_codes=["SUBMISSION_OUTCOME_UNKNOWN", error.code],
            )
            return
        if submission.tx_hash:
            self.store.track_execution(
                workflow_id, id_, self.settings.mode, built, self.clock(), submission.tx_hash
            )
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "SUBMITTED",
                self.clock(),
                tx_hash=submission.tx_hash,
            )
            if execute_call:
                try:
                    runtime.output(
                        "execute_approved_swap", execute_call[0], execute_call[1], submission
                    )
                except ControlError as error:
                    # Broadcast has already happened. Preserve its hash and monitoring reservation;
                    # a shield failure after submission must never cause a replacement/retry write.
                    self.shield.state.event(
                        runtime.session_id,
                        "POST_SUBMISSION_FEEDBACK",
                        self.clock(),
                        {"code": error.code, "decision_id": id_},
                    )
            self._reconcile(workflow_id, id_, built, client, submission.tx_hash)
        elif submission.status in {"STALE_REQUIRES_REEVALUATION", "FAILED_TO_SUBMIT"}:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "FAILED_TO_SUBMIT",
                self.clock(),
                reason_codes=[submission.status],
            )
        else:
            self.store.transition(
                workflow_id,
                id_,
                "SUBMITTING",
                "SUBMITTING",
                self.clock(),
                reason_codes=["SUBMISSION_OUTCOME_UNKNOWN"],
            )

    def saved_risk(self, evidence, snapshot_id):
        _, bundle = self.store.decision(build_id=evidence.build_id)
        if bundle.get("simulation") != evidence.model_dump():
            raise ControlError("HASH_MISMATCH")
        if "risk" not in bundle or bundle["risk"]["snapshot_id"] != snapshot_id:
            raise ControlError("SNAPSHOT_NOT_FOUND", 404)
        return EconomicRiskAssessment.model_validate(bundle["risk"])

    def saved_decision(self, refs):
        _, bundle = self.store.decision(intent_id=refs.intent_id, build_id=refs.build_id)
        decision = SecurityDecision.model_validate(bundle["decision"])
        if (decision.build_id, decision.snapshot_id, decision.simulation_evidence_root) != (
            refs.build_id,
            refs.snapshot_id,
            refs.simulation_evidence_root,
        ) or refs.alignment.model_dump() != bundle["alignment"]:
            raise ControlError("HASH_MISMATCH")
        return decision
