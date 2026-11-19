from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import Mandate
from treasury_backend.modules import portfolio as portfolio
from treasury_backend.modules.workflows.client import VerifiedExecutionClient
from treasury_contracts.models import BuiltTransaction


class OutcomeMonitor:
    def _reconcile(self, workflow_id, id_, built, client, tx_hash, receipt=None):
        try:
            receipt = receipt or client.execution(tx_hash)
        except ControlError:
            return
        if receipt.status in {"SUBMITTED", "PENDING"}:
            return
        details = {"receipt": receipt.model_dump()}
        state = receipt.status
        if (
            (receipt.tx_hash, receipt.decision_id, receipt.build_id, receipt.chain_id)
            != (tx_hash, id_, built.build_id, built.chain_id)
            or receipt.block_number is None
            or receipt.gas_used is None
        ):
            state = "RECEIPT_MISMATCH"
        elif state == "CONFIRMED":
            if (
                receipt.actual_token_in_delta_base_units != f"-{built.amount_in_base_units}"
                or int(receipt.actual_token_out_delta_base_units or "0")
                < int(built.min_amount_out_base_units)
                or not receipt.event_refs
                or receipt.revert_reason
            ):
                state = "RECEIPT_MISMATCH"
            else:
                try:
                    updated = client.balances()
                    if (updated.chain_id, updated.vault_address) == (
                        built.chain_id,
                        built.vault_address.lower(),
                    ) and updated.block_number >= receipt.block_number:
                        details["post_execution_balances"] = updated.model_dump()
                except ControlError:
                    pass
        elif state == "REVERTED" and (
            receipt.actual_token_in_delta_base_units
            == receipt.actual_token_out_delta_base_units
            == "0"
        ):
            if receipt.revert_reason in {
                "MIN_OUTPUT_NOT_MET",
                "POSTCONDITION_FAILED",
                "SESSION_RISK_LIMIT",
                "GLOBAL_RISK_LIMIT",
            }:
                details["reason_codes"] = ["PROTECTED_REVERT"]
        else:
            state = "RECEIPT_MISMATCH"
        if state in {"CONFIRMED", "REVERTED"} and isinstance(client, VerifiedExecutionClient):
            try:
                utc_day, gas_cost_wei = client.execution_fee(receipt)
                details["execution_fee"] = {
                    "chain_id": built.chain_id,
                    "vault_address": built.vault_address.lower(),
                    "utc_day": utc_day,
                    "gas_cost_wei": gas_cost_wei,
                }
            except ControlError as error:
                if error.code != "RECEIPT_MISMATCH":
                    return
                state = "RECEIPT_MISMATCH"
        self.store.transition(workflow_id, id_, "SUBMITTED", state, self.clock(), **details)

    def workflow(self, id_):
        workflow = self.store.workflow(id_)
        if workflow["mode"] != self.settings.mode:
            return workflow
        if self.settings.mode != "MOCK" and workflow["status"] in {"CONFIRMED", "REVERTED"}:
            last = workflow["timeline"][-1]
            _, bundle = self.store.decision(decision_id=last["decision_id"])
            mandate = Mandate.model_validate(bundle["mandate"])
            client = self.client(id_, mandate)
            try:
                current = client.execution(last["receipt"]["tx_hash"])
                # Revalidate canonical receipt even after initial confirmation.
                if current.status in {"PENDING", "SUBMITTED"} or current.block_hash != last[
                    "receipt"
                ].get("block_hash"):
                    self.store.transition(
                        id_,
                        last["decision_id"],
                        workflow["status"],
                        "SUBMITTED",
                        self.clock(),
                        tx_hash=last["receipt"]["tx_hash"],
                        reason_codes=["REORG_RECONCILIATION"],
                    )
                    workflow = self.store.workflow(id_)
            except ControlError:
                self.store.transition(
                    id_,
                    last["decision_id"],
                    workflow["status"],
                    "SUBMITTED",
                    self.clock(),
                    tx_hash=last["receipt"]["tx_hash"],
                    reason_codes=["RECEIPT_REVALIDATION_UNAVAILABLE"],
                )
                workflow = self.store.workflow(id_)
        if workflow["status"] in {"SUBMITTED", "SUBMITTING"}:
            event = workflow["timeline"][-1]
            _, bundle = self.store.decision(decision_id=event["decision_id"])
            mandate = Mandate.model_validate(bundle["mandate"])
            built = BuiltTransaction.model_validate(bundle["build"])
            client = self.client(id_, mandate)
            if workflow["status"] == "SUBMITTED":
                self._reconcile(id_, event["decision_id"], built, client, event["tx_hash"])
            elif self.clock() > built.deadline:
                self._expire_unknown_submission(id_, event["decision_id"], built, client)
            workflow = self.store.workflow(id_)
            if workflow["status"] not in {"SUBMITTED", "SUBMITTING"}:
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
