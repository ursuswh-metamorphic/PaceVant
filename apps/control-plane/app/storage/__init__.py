import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.errors import ControlError
from app.storage.portfolio import SCHEMA_V2, PortfolioStore
from app.temporal import storage as temporal

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
"""


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store(PortfolioStore):
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            conn.executescript(SCHEMA_V2)
            conn.executescript(temporal.SCHEMA)

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

    def start(self, id_, metadata, temporal_intent=None):
        with self.connection(write=True) as conn:
            conn.execute("INSERT INTO workflows VALUES (?, 'STARTED', ?)", (id_, dump(metadata)))
            if temporal_intent:
                conn.execute(
                    "INSERT INTO itag_workflows VALUES (?,?,?,?)",
                    (
                        id_,
                        temporal_intent.spec_id,
                        temporal_intent.revision,
                        temporal_intent.step_id,
                    ),
                )

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

    def execution_gas_spent(
        self, chain_id: int, vault_address: str, utc_day: int, mode=None
    ) -> int:
        # One active canonical projection per transaction; legacy events stay auditable.
        with self.connection() as conn:
            projected = conn.execute(
                "SELECT tx_hash,body FROM outcome_projections WHERE chain_id=? AND vault=?"
                + (" AND mode=?" if mode else ""),
                (chain_id, vault_address.lower(), mode)
                if mode
                else (chain_id, vault_address.lower()),
            ).fetchall()
            legacy = conn.execute(
                "SELECT e.sequence,e.body FROM events e JOIN workflows w ON w.id=e.workflow_id WHERE e.stage IN ('CONFIRMED','REVERTED')"
                + (" AND json_extract(w.body,'$.mode')=?" if mode else ""),
                (mode,) if mode else (),
            ).fetchall()
        covered = {r["tx_hash"] for r in projected if r["tx_hash"]}
        total = 0
        for row in projected:
            report = json.loads(row["body"])["verification"]
            if (
                report.get("canonical")
                and report.get("gas_verified")
                and report.get("block_timestamp", 0) // 86400 == utc_day
            ):
                total += int(report["gas_cost_wei"])
        seen = set()
        for row in legacy:
            event = json.loads(row["body"])
            fee = event.get("execution_fee")
            if not fee or (
                fee.get("chain_id"),
                fee.get("vault_address", "").lower(),
                fee.get("utc_day"),
            ) != (chain_id, vault_address.lower(), utc_day):
                continue
            tx = (
                fee.get("tx_hash")
                or (event.get("receipt") or {}).get("tx_hash")
                or str(row["sequence"])
            )
            if tx not in covered and tx not in seen:
                total += int(fee["gas_cost_wei"])
                seen.add(tx)
        return total

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
            if stage == "REPLAN_REQUIRED" and suggested_amount:
                event_data["suggested_amount_base_units"] = str(suggested_amount)
            if evaluation:
                self._event(conn, workflow_id, "EVALUATED", decision.created_at, evaluation)
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

    def history_version(self, chain_id=None, vault_address=None, mode=None):
        with self.connection() as conn:
            if chain_id is not None and vault_address is not None:
                row = conn.execute(
                    "SELECT version FROM treasury_versions WHERE mode=? AND chain_id=? AND vault=?",
                    (mode or "FUJI", chain_id, vault_address.lower()),
                ).fetchone()
                return row[0] if row else 0
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
            temporal.check_approval(conn, workflow_id, id_, now)
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
            # Linearize task cancellation against the transition that starts a financial submission.
            if state == "SUBMITTING" and expected == "ATTESTED":
                temporal.check_approval(conn, workflow_id, decision_id, now, submitting=True)
                record = conn.execute(
                    "SELECT body FROM decisions WHERE id=?", (decision_id,)
                ).fetchone()
                proof = json.loads(record[0]).get("task_shield_proof") if record else None
                if proof:
                    session = conn.execute(
                        "SELECT revision FROM shield_sessions WHERE id=?", (proof["session_id"],)
                    ).fetchone()
                    if not session or session[0] != proof["revision"]:
                        raise ControlError("TASK_SHIELD_STALE_TASKS")
            cursor = conn.execute(
                "UPDATE attestations SET state=? WHERE decision_id=? AND state=?",
                (state, decision_id, expected),
            )
            if cursor.rowcount:
                self._event(conn, workflow_id, state, now, {"decision_id": decision_id, **details})
            return bool(cursor.rowcount)
