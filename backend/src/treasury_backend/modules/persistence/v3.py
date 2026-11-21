"""Additive V3 migration, durable request claims, immutable evidence, and signing reservation."""

import json
from uuid import uuid4

from treasury_backend.core.errors import ControlError
from treasury_contracts.crypto import content_hash

MIGRATION = """
CREATE TABLE IF NOT EXISTS treasury_schema_migrations(version INTEGER PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS treasury_requests(
 id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL,
 session_id TEXT NOT NULL, state TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS treasury_evidence(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL REFERENCES treasury_requests(id),
 stage TEXT NOT NULL, created_at INTEGER NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS treasury_activity(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL REFERENCES treasury_requests(id),
 stage TEXT NOT NULL, created_at INTEGER NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS treasury_activity_workflow ON treasury_activity(workflow_id,sequence);
CREATE INDEX IF NOT EXISTS treasury_evidence_workflow ON treasury_evidence(workflow_id,sequence);
CREATE TRIGGER IF NOT EXISTS treasury_activity_no_update BEFORE UPDATE ON treasury_activity
BEGIN SELECT RAISE(ABORT,'immutable treasury activity'); END;
CREATE TRIGGER IF NOT EXISTS treasury_activity_no_delete BEFORE DELETE ON treasury_activity
BEGIN SELECT RAISE(ABORT,'immutable treasury activity'); END;
CREATE TRIGGER IF NOT EXISTS treasury_evidence_no_update BEFORE UPDATE ON treasury_evidence
BEGIN SELECT RAISE(ABORT,'immutable treasury evidence'); END;
CREATE TRIGGER IF NOT EXISTS treasury_evidence_no_delete BEFORE DELETE ON treasury_evidence
BEGIN SELECT RAISE(ABORT,'immutable treasury evidence'); END;
INSERT OR IGNORE INTO treasury_schema_migrations VALUES(3,'Fixed operation treasury workflows and evidence');
"""
FINAL = {"CONFIRMED", "REVERTED", "REJECTED", "EXPIRED_UNSIGNED"}


class TreasuryStore:
    def __init__(self, store):
        self.store = store
        with store.connection() as db:
            db.executescript(MIGRATION)

    def claim(self, key, intent, now):
        if not key or not 1 <= len(key) <= 128:
            raise ControlError("IDEMPOTENCY_KEY_REQUIRED", 400)
        body = intent.model_dump(mode="json")
        hash_ = content_hash(body)
        with self.store.connection(write=True) as db:
            prior = db.execute(
                "SELECT * FROM treasury_requests WHERE request_key=?", (key,)
            ).fetchone()
            if prior:
                if prior["request_hash"] != hash_:
                    raise ControlError("IDEMPOTENCY_CONFLICT", 409)
                return json.loads(prior["body"]), False
            rows = db.execute(
                "SELECT state FROM treasury_requests WHERE session_id=?", (intent.session_id,)
            ).fetchall()
            if any(r[0] not in FINAL for r in rows):
                raise ControlError("SESSION_HAS_PENDING_EXECUTION", 409)
            id_ = "treasury_" + uuid4().hex
            record = {"workflow_id": id_, "intent": body, "status": "STARTED", "created_at": now}
            db.execute(
                "INSERT INTO treasury_requests VALUES(?,?,?,?,?,?)",
                (id_, key, hash_, intent.session_id, "STARTED", json.dumps(record)),
            )
            return record, True

    def event(self, id_, stage, value, now):
        with self.store.connection(write=True) as db:
            db.execute(
                "INSERT INTO treasury_evidence(workflow_id,stage,created_at,body) VALUES(?,?,?,?)",
                (id_, stage, now, json.dumps(value)),
            )

    def activity(self, id_, stage, value, now):
        """Public operational observations, separate from signed evidence/hashes."""
        with self.store.connection(write=True) as db:
            db.execute(
                "INSERT INTO treasury_activity(workflow_id,stage,created_at,body) VALUES(?,?,?,?)",
                (id_, stage, now, json.dumps(value)),
            )

    def update(self, id_, state, **values):
        with self.store.connection(write=True) as db:
            row = db.execute("SELECT body FROM treasury_requests WHERE id=?", (id_,)).fetchone()
            if row is None:
                raise ControlError("NOT_FOUND", 404)
            record = json.loads(row[0]) | values | {"status": state}
            db.execute(
                "UPDATE treasury_requests SET state=?,body=? WHERE id=?",
                (state, json.dumps(record), id_),
            )
        return record

    def sign_once(self, id_, sign):
        with self.store.connection(write=True) as db:
            record = json.loads(
                db.execute("SELECT body FROM treasury_requests WHERE id=?", (id_,)).fetchone()[0]
            )
            if "signed_approval" in record:
                return record["signed_approval"]
            if record["status"] != "PROVED":
                raise ControlError("DECISION_NOT_APPROVED", 403)
            signed = sign()
            record.update(status="SIGNED", signed_approval=signed)
            db.execute(
                "UPDATE treasury_requests SET state='SIGNED',body=? WHERE id=?",
                (json.dumps(record), id_),
            )
            return signed

    def get(self, id_):
        with self.store.connection() as db:
            row = db.execute("SELECT body FROM treasury_requests WHERE id=?", (id_,)).fetchone()
            if row is None:
                raise ControlError("NOT_FOUND", 404)
            record = json.loads(row[0])
            record["timeline"] = [
                {"stage": r[0], "created_at": r[1], "evidence": json.loads(r[2])}
                for r in db.execute(
                    "SELECT stage,created_at,body FROM treasury_evidence WHERE workflow_id=? ORDER BY sequence",
                    (id_,),
                )
            ]
            record["activity"] = [
                {"sequence": r[0], "stage": r[1], "created_at": r[2], **json.loads(r[3])}
                for r in db.execute(
                    "SELECT sequence,stage,created_at,body FROM treasury_activity WHERE workflow_id=? ORDER BY sequence",
                    (id_,),
                )
            ]
        # Signed approvals stay in the recovery ledger, not the public evidence view.
        record.pop("signed_approval", None)
        return record

    def history(self, limit=30):
        with self.store.connection() as db:
            records = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT body FROM treasury_requests ORDER BY rowid DESC LIMIT ?", (limit,)
                )
            ]
        for record in records:
            record.pop("signed_approval", None)
        return records

    def by_key(self, key):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT body FROM treasury_requests WHERE request_key=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def pending(self):
        return [row for row in self.history(1000) if row["status"] not in FINAL]
