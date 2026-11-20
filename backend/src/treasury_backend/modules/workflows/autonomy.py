"""Explicitly enabled, persisted local autonomy. Owner session remains the authority."""

import json
from threading import Event, Thread

from treasury_backend.core.errors import ControlError
from treasury_contracts.v3 import RebalanceRequest


class AutonomousTreasury:
    def __init__(self, workflows):
        self.workflows = workflows
        self.store = workflows.control.store
        self.stop = Event()
        self.thread = None
        with self.store.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS treasury_autonomy(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)"
            )
            db.execute(
                "INSERT OR IGNORE INTO treasury_autonomy VALUES(1,?)",
                (json.dumps({"enabled": False}),),
            )

    def state(self):
        with self.store.connection() as db:
            return json.loads(
                db.execute("SELECT body FROM treasury_autonomy WHERE id=1").fetchone()[0]
            )

    def configure(self, enabled, session_id):
        if enabled:
            context = self.workflows.execution.context(session_id)
            if not context["authority"]["operation_mask"] & 16:
                raise ControlError("REBALANCE_NOT_AUTHORIZED", 403)
        result = {
            "enabled": enabled,
            "session_id": session_id,
            "updated_at": self.workflows.clock(),
        }
        with self.store.connection(write=True) as db:
            db.execute("UPDATE treasury_autonomy SET body=? WHERE id=1", (json.dumps(result),))
        return result

    def tick(self):
        state = self.state()
        if not state["enabled"]:
            return None
        session = state["session_id"]
        # Reconciliation must resolve prior unknown receipts before another operation is considered.
        for pending in self.workflows.store.pending():
            self.workflows.reconcile(pending["workflow_id"])
        if self.workflows.store.pending():
            return {"reason": "PENDING_RECONCILIATION"}
        try:
            request = RebalanceRequest(session_id=session, execute=True)
            context = self.workflows.execution.context(session)
            key = (
                "auto:"
                + session[2:18]
                + ":"
                + str(context["authority"]["actions"])
                + ":"
                + str(self.workflows.clock() // 60)
            )
            result = self.workflows.rebalance(request, key)
            if result.get("status") in {
                "REJECTED",
                "REVERTED",
                "SIGNED_REQUIRES_RECOVERY",
                "SUBMITTED_UNKNOWN",
                "REORGED",
                "REPLACED_UNVERIFIED",
            }:
                self.configure(False, session)
                result = result | {"autonomy_disabled": True}
            return result
        except (ValueError, ControlError) as exc:
            # Never renew session, relax policy, or keep retrying unavailable authority.
            self.configure(False, session)
            return {"reason": getattr(exc, "code", str(exc)), "autonomy_disabled": True}

    def start(self):
        def loop():
            while not self.stop.wait(15):
                try:
                    self.reconcile_outcomes()
                    self.tick()
                except Exception:
                    state = self.state()
                    self.configure(False, state.get("session_id"))

        self.thread = Thread(target=loop, daemon=True, name="treasury-v3-local-autonomy")
        self.thread.start()

    def reconcile_outcomes(self):
        """Read-only observer remains active even when autonomous spending is disabled."""
        with self.workflows.execution.exclusive():
            for record in self.workflows.store.history(30):
                if record.get("outcome") or record["status"] not in {
                    "REJECTED",
                    "EXPIRED_UNSIGNED",
                }:
                    self.workflows.reconcile(record["workflow_id"])

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=45)
