import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from treasury_backend.core.errors import ControlError

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    stage TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    intent_id TEXT NOT NULL UNIQUE,
    build_id TEXT UNIQUE,
    snapshot_id TEXT UNIQUE,
    body TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS decisions_no_update
BEFORE UPDATE ON decisions BEGIN SELECT RAISE(ABORT, 'immutable decision'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete
BEFORE DELETE ON decisions BEGIN SELECT RAISE(ABORT, 'immutable decision'); END;

CREATE TABLE IF NOT EXISTS attestations (
    decision_id TEXT PRIMARY KEY REFERENCES decisions(id),
    scope TEXT NOT NULL,
    nonce TEXT NOT NULL,
    state TEXT NOT NULL,
    issued_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    signed_pdr TEXT NOT NULL,
    UNIQUE(scope, nonce)
);
CREATE INDEX IF NOT EXISTS attestations_scope_state ON attestations(scope, state);
CREATE TABLE IF NOT EXISTS proof_artifacts (
    context_hash TEXT PRIMARY KEY, decision_id TEXT NOT NULL UNIQUE REFERENCES decisions(id),
    status TEXT NOT NULL, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compiled_postconditions (
    context_hash TEXT PRIMARY KEY REFERENCES proof_artifacts(context_hash),
    post_conditions_hash TEXT NOT NULL, abi_blob BLOB NOT NULL
);
CREATE TRIGGER IF NOT EXISTS proofs_no_update BEFORE UPDATE ON proof_artifacts
BEGIN SELECT RAISE(ABORT, 'immutable proof'); END;
CREATE TRIGGER IF NOT EXISTS proofs_no_delete BEFORE DELETE ON proof_artifacts
BEGIN SELECT RAISE(ABORT, 'immutable proof'); END;
CREATE TRIGGER IF NOT EXISTS phi_no_update BEFORE UPDATE ON compiled_postconditions
BEGIN SELECT RAISE(ABORT, 'immutable Phi'); END;
CREATE TRIGGER IF NOT EXISTS phi_no_delete BEFORE DELETE ON compiled_postconditions
BEGIN SELECT RAISE(ABORT, 'immutable Phi'); END;
"""


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store:
    def proof(self, context_hash):
        with self.connection() as conn:
            row = conn.execute(
                "SELECT body FROM proof_artifacts WHERE context_hash=?", (context_hash,)
            ).fetchone()
        if row is None:
            raise ControlError("PROOF_NOT_FOUND", 404)
        return json.loads(row[0])

    def proof_query(self, hash_, raw):
        from treasury_contracts.v2 import keccak

        if keccak(raw) != hash_:
            raise ControlError("HASH_MISMATCH")
        directory = self.path.parent / "proof-queries"
        directory.mkdir(parents=True, exist_ok=True)
        file = directory / (hash_[2:] + ".smt2")
        if file.exists() and file.read_bytes() != raw:
            raise ControlError("HASH_MISMATCH")
        file.write_bytes(raw)

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self, *, write=False):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def start(self, id_, metadata):
        with self.connection(write=True) as conn:
            conn.execute("INSERT INTO workflows VALUES (?, 'STARTED', ?)", (id_, dump(metadata)))

    @staticmethod
    def _event(conn, id_, stage, now, data):
        conn.execute(
            "INSERT INTO events(workflow_id, stage, created_at, body) VALUES (?, ?, ?, ?)",
            (id_, stage, now, dump(data)),
        )
        conn.execute("UPDATE workflows SET status=? WHERE id=?", (stage, id_))

    def event(self, id_, stage, now, **data):
        with self.connection(write=True) as conn:
            self._event(conn, id_, stage, now, data)

    def workflow(self, id_):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (id_,)).fetchone()
            if row is None:
                raise ControlError("WORKFLOW_NOT_FOUND", 404)
            events = conn.execute(
                "SELECT * FROM events WHERE workflow_id=? ORDER BY sequence", (id_,)
            ).fetchall()
        return {
            "workflow_id": id_,
            "status": row["status"],
            **json.loads(row["body"]),
            "timeline": [
                {"stage": event["stage"], "at": event["created_at"], **json.loads(event["body"])}
                for event in events
            ],
        }

    def execution_gas_spent(self, chain_id: int, vault_address: str, utc_day: int) -> int:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT json_extract(body, '$.execution_fee.gas_cost_wei')
                FROM events WHERE stage IN ('CONFIRMED', 'REVERTED')
                  AND json_extract(body, '$.execution_fee.chain_id') = ?
                  AND json_extract(body, '$.execution_fee.vault_address') = ?
                  AND json_extract(body, '$.execution_fee.utc_day') = ?
                  AND sequence IN (
                    SELECT MAX(sequence) FROM events WHERE stage IN ('CONFIRMED','REVERTED')
                    GROUP BY COALESCE(json_extract(body, '$.receipt.tx_hash'), 'event_' || sequence)
                  )
                """,
                (chain_id, vault_address, utc_day),
            ).fetchall()
        return sum(int(row[0]) for row in rows)

    def record(self, workflow_id, stage, decision, bundle, suggested_amount, evaluation):
        with self.connection(write=True) as conn:
            try:
                conn.execute(
                    "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        decision.decision_id,
                        workflow_id,
                        decision.intent_id,
                        decision.build_id,
                        decision.snapshot_id,
                        dump(bundle),
                    ),
                )
            except sqlite3.IntegrityError:
                raise ControlError("DECISION_REFERENCE_ALREADY_USED") from None
            event_data = {"decision": decision.model_dump()}
            if evaluation:
                self._event(conn, workflow_id, "EVALUATED", decision.created_at, evaluation)
            if bundle.get("proof"):
                from treasury_contracts.v2 import ProofArtifactV2

                proof = ProofArtifactV2.model_validate(bundle["proof"])
                conn.execute(
                    "INSERT INTO proof_artifacts VALUES (?, ?, ?, ?)",
                    (proof.context_hash, decision.decision_id, proof.status, dump(bundle["proof"])),
                )
                if proof.phi:
                    conn.execute(
                        "INSERT INTO compiled_postconditions VALUES (?, ?, ?)",
                        (proof.context_hash, proof.phi.hash, proof.phi.abi_bytes),
                    )
                self._event(
                    conn,
                    workflow_id,
                    "PROVED"
                    if proof.status == "VERIFIED"
                    else "PROOF_INCONCLUSIVE"
                    if proof.status == "INCONCLUSIVE"
                    else "PROOF_REJECTED",
                    decision.created_at,
                    {"proof": bundle["proof"]},
                )
            if stage == "REPLAN_REQUIRED" and suggested_amount:
                event_data["suggested_amount_base_units"] = str(suggested_amount)
            self._event(conn, workflow_id, stage, decision.created_at, event_data)

    def decision(self, *, decision_id=None, intent_id=None, build_id=None):
        filters = [
            (key, value)
            for key, value in [
                ("id", decision_id),
                ("intent_id", intent_id),
                ("build_id", build_id),
            ]
            if value is not None
        ]
        if not filters:
            raise ValueError("decision reference required")
        where = " AND ".join(f"{key}=?" for key, _ in filters)
        with self.connection() as conn:
            row = conn.execute(
                f"SELECT workflow_id, body FROM decisions WHERE {where}",
                tuple(value for _, value in filters),
            ).fetchone()
        if row is None:
            raise ControlError("DECISION_NOT_FOUND", 404)
        return row["workflow_id"], json.loads(row["body"])

    def history_version(self):
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM events WHERE stage='CONFIRMED'"
            ).fetchone()
        return row[0]

    def attempts(self, workflow_id):
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT body FROM decisions WHERE workflow_id=? ORDER BY rowid", (workflow_id,)
            ).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def reserve_signature(self, *, id_, workflow_id, scope, nonce, now, expires_at, sign):
        with self.connection(write=True) as conn:
            policy = conn.execute(
                "SELECT json_extract(body, '$.mandate.policy_hash') FROM decisions WHERE id=?",
                (id_,),
            ).fetchone()
            recent = conn.execute(
                """SELECT json_extract(e.body, '$.receipt.revert_reason')
                FROM events e JOIN attestations a ON a.decision_id=json_extract(e.body, '$.decision_id')
                JOIN decisions d ON d.id=a.decision_id
                WHERE a.scope=? AND e.stage IN ('CONFIRMED','REVERTED')
                  AND a.state IN ('CONFIRMED','REVERTED')
                  AND json_extract(d.body, '$.mandate.policy_hash')=?
                  AND e.sequence IN (
                    SELECT MAX(latest.sequence) FROM events latest
                    WHERE latest.stage IN ('CONFIRMED','REVERTED')
                    GROUP BY json_extract(latest.body, '$.decision_id')
                  )
                ORDER BY e.sequence DESC LIMIT 2""",
                (scope, policy[0] if policy else None),
            ).fetchall()
            if len(recent) == 2 and all(
                row[0]
                in {
                    "MIN_OUTPUT_NOT_MET",
                    "POSTCONDITION_FAILED",
                    "SESSION_RISK_LIMIT",
                    "GLOBAL_RISK_LIMIT",
                }
                for row in recent
            ):
                raise ControlError("SIGNER_QUARANTINED", 403)
            issued = conn.execute(
                "SELECT 1 FROM attestations WHERE decision_id=?", (id_,)
            ).fetchone()
            if issued:
                raise ControlError("ATTESTATION_ALREADY_ISSUED")
            if conn.execute(
                "SELECT 1 FROM attestations WHERE scope=? AND "
                "(state IN ('SUBMITTING', 'SUBMITTED', 'RECEIPT_MISMATCH') "
                "OR (state='ATTESTED' AND expires_at>?))",
                (scope, now),
            ).fetchone():
                raise ControlError("VAULT_APPROVAL_IN_FLIGHT")
            if conn.execute(
                "SELECT 1 FROM attestations WHERE scope=? AND nonce=?", (scope, nonce)
            ).fetchone():
                raise ControlError("NONCE_REPLAY")
            # Once the SQLite write lock has been acquired, recheck chain, evidence and
            # economic state before signing. No other local approval can pass the gate meanwhile.
            signed, issued_at = sign()
            conn.execute(
                "INSERT INTO attestations VALUES (?, ?, ?, 'ATTESTED', ?, ?, ?)",
                (
                    id_,
                    scope,
                    nonce,
                    issued_at,
                    expires_at,
                    signed.model_dump_json(),
                ),
            )
            self._event(
                conn,
                workflow_id,
                "ATTESTED",
                issued_at,
                {
                    "decision_id": id_,
                    "typed_data_hash": signed.typed_data_hash,
                    "expires_at": expires_at,
                    "nonce": nonce,
                },
            )
        return signed

    def transition(self, workflow_id, decision_id, expected, state, now, **details):
        with self.connection(write=True) as conn:
            cursor = conn.execute(
                "UPDATE attestations SET state=? WHERE decision_id=? AND state=?",
                (state, decision_id, expected),
            )
            if cursor.rowcount:
                self._event(conn, workflow_id, state, now, {"decision_id": decision_id, **details})
            return bool(cursor.rowcount)
