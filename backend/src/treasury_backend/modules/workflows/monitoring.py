from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import Mandate
from treasury_backend.modules import portfolio as portfolio
from treasury_contracts.models import BuiltTransaction


class WorkflowMonitor:
    def _reconcile(self, workflow_id, id_, built, client, tx_hash, receipt=None):
        self.store.track_execution(
            workflow_id, id_, self.settings.mode, built, self.clock(), tx_hash
        )
        return self.monitor.process(id_, force=True, client=client, receipt=receipt)

    def workflow(self, id_):
        workflow = self.store.workflow(id_)
        if workflow["mode"] != self.settings.mode:
            return workflow
        candidates = [e for e in reversed(workflow["timeline"]) if e.get("decision_id")]
        if candidates and workflow["status"] in {
            "SUBMITTING",
            "SUBMITTED",
            "CONFIRMED",
            "REVERTED",
            "RECEIPT_MISMATCH",
        }:
            id_decision = candidates[0]["decision_id"]
            job = self.store.monitor_job(id_decision)
            if job is None:
                self.monitor.bootstrap()
                job = self.store.monitor_job(id_decision)
            if job and (self.settings.mode != "MOCK" or id_ in self.mock_clients):
                self.monitor.process(id_decision, force=True)
            workflow = self.store.workflow(id_)
            if workflow["status"] == "SUBMITTING":
                _, bundle = self.store.decision(decision_id=id_decision)
                built = BuiltTransaction.model_validate(bundle["build"])
                if self.clock() > built.deadline:
                    try:
                        mandate = Mandate.model_validate(bundle["mandate"])
                        self._expire_unknown_submission(
                            id_, id_decision, built, self._monitor_client(id_, mandate)
                        )
                    except ControlError:
                        pass
            workflow = self.store.workflow(id_)
            job = self.store.monitor_job(id_decision)
            workflow["reconciliation"] = self.store.outcome_projection(id_decision)
            workflow["monitoring"] = (
                {"state": job["state"], "next_poll_at": job["next_at"], "attempts": job["attempts"]}
                if job
                else None
            )
            if workflow["status"] not in {"SUBMITTING", "SUBMITTED"}:
                self.mock_clients.pop(id_, None)
        return workflow

    def _expire_unknown_submission(self, workflow_id, decision_id, built, client):
        try:
            context = client.context(built=built)
        except ControlError:
            return
        if (
            (context.chain_id, context.vault_address, context.deployment)
            == (built.chain_id, built.vault_address.lower(), self.settings.mode)
            and portfolio.fresh(context.block_timestamp, self.clock())
            and context.block_timestamp > built.deadline
            and context.nonce_used is False
        ):
            self.store.transition(
                workflow_id,
                decision_id,
                "SUBMITTING",
                "EXPIRED",
                self.clock(),
                reason_codes=["SUBMISSION_NOT_CONFIRMED_BY_DEADLINE"],
            )

    def recover_submission(self, workflow_id, tx_hash):
        workflow = self.store.workflow(workflow_id)
        if workflow["mode"] != self.settings.mode or workflow["status"] != "SUBMITTING":
            raise ControlError("NO_UNKNOWN_SUBMISSION")
        id_ = workflow["timeline"][-1]["decision_id"]
        _, bundle = self.store.decision(decision_id=id_)
        mandate = Mandate.model_validate(bundle["mandate"])
        built = BuiltTransaction.model_validate(bundle["build"])
        client = self.client(workflow_id, mandate)
        receipt = client.execution(tx_hash)
        if (receipt.tx_hash, receipt.decision_id, receipt.build_id, receipt.chain_id) != (
            tx_hash,
            id_,
            built.build_id,
            built.chain_id,
        ) or receipt.status not in {"SUBMITTED", "PENDING", "CONFIRMED", "REVERTED"}:
            raise ControlError("RECEIPT_MISMATCH")
        if self.store.transition(
            workflow_id, id_, "SUBMITTING", "SUBMITTED", self.clock(), tx_hash=tx_hash
        ):
            self._reconcile(workflow_id, id_, built, client, tx_hash, receipt)
        return self.store.workflow(workflow_id)
