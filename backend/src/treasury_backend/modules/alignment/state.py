"""Persistent, session-scoped tasks. Only authenticated USER updates mutate objectives."""

import json

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.portfolio.observations import content_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS shield_sessions(
 id TEXT PRIMARY KEY,workflow_id TEXT UNIQUE,mandate_id TEXT NOT NULL,mandate_hash TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS shield_messages(
 session_id TEXT NOT NULL,message_id TEXT NOT NULL,revision INTEGER NOT NULL,role TEXT NOT NULL,
 operation TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(session_id,message_id));
CREATE TABLE IF NOT EXISTS shield_tasks(
 session_id TEXT NOT NULL,task_id TEXT NOT NULL,text TEXT NOT NULL,body TEXT NOT NULL,
 active INTEGER NOT NULL,PRIMARY KEY(session_id,task_id),UNIQUE(session_id,text));
CREATE TABLE IF NOT EXISTS shield_context(
 seq INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shield_checks(
 check_id TEXT PRIMARY KEY,session_id TEXT NOT NULL,revision INTEGER NOT NULL,created_at INTEGER NOT NULL,body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS shield_checks_session ON shield_checks(session_id,created_at);
CREATE TABLE IF NOT EXISTS shield_events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,kind TEXT NOT NULL,created_at INTEGER NOT NULL,body TEXT NOT NULL);
"""
for table in ("shield_messages", "shield_context", "shield_checks", "shield_events"):
    for action in ("UPDATE", "DELETE"):
        SCHEMA += f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable shield evidence'); END;"


def pack(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class TaskState:
    def __init__(self, store):
        self.store = store
        with store.connection() as conn:
            conn.executescript(SCHEMA)

    def create(self, id_, mandate, now, workflow_id=None):
        with self.store.connection(write=True) as conn:
            conn.execute(
                "INSERT INTO shield_sessions VALUES(?,?,?,?,0,?)",
                (id_, workflow_id, mandate.mandate_id, content_hash(mandate.model_dump()), now),
            )
        return self.session(id_)

    def session(self, id_):
        with self.store.connection() as conn:
            row = conn.execute("SELECT * FROM shield_sessions WHERE id=?", (id_,)).fetchone()
            if not row:
                raise ControlError("TASK_SHIELD_SESSION_NOT_FOUND", 404)
            tasks = conn.execute(
                "SELECT body FROM shield_tasks WHERE session_id=? AND active=1 ORDER BY rowid",
                (id_,),
            ).fetchall()
        return {**dict(row), "tasks": [json.loads(r[0]) for r in tasks]}

    def for_workflow(self, workflow_id):
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT id FROM shield_sessions WHERE workflow_id=?", (workflow_id,)
            ).fetchone()
        return self.session(row[0]) if row else None

    def user_update(
        self,
        id_,
        message,
        operation,
        cancel_ids,
        expected_revision,
        instructions,
        now,
        *,
        authenticated,
        max_tasks,
    ):
        if (
            not authenticated
            or message.role != "USER"
            or any(
                i.source != "USER" or i.source_message_id != message.message_id
                for i in instructions
            )
        ):
            raise ControlError("TASK_SHIELD_USER_TRUST_REQUIRED", 403)
        body = {
            "message": message.model_dump(),
            "operation": operation,
            "cancel_task_ids": cancel_ids,
        }
        with self.store.connection(write=True) as conn:
            old = conn.execute(
                "SELECT body FROM shield_messages WHERE session_id=? AND message_id=?",
                (id_, message.message_id),
            ).fetchone()
            if old:
                if old[0] != pack(body):
                    raise ControlError("TASK_SHIELD_MESSAGE_CONFLICT")
                return False
            row = conn.execute("SELECT revision FROM shield_sessions WHERE id=?", (id_,)).fetchone()
            if not row or row[0] != expected_revision:
                raise ControlError("TASK_SHIELD_STALE_TASKS")
            if operation == "CANCEL":
                if not cancel_ids:
                    raise ControlError("TASK_SHIELD_CANCEL_TARGET_REQUIRED", 400)
                known = {
                    r[0]
                    for r in conn.execute(
                        "SELECT task_id FROM shield_tasks WHERE session_id=? AND active=1", (id_,)
                    )
                }
                if not set(cancel_ids) <= known:
                    raise ControlError("TASK_SHIELD_TASK_NOT_FOUND", 404)
                for task_id in cancel_ids:
                    conn.execute(
                        "UPDATE shield_tasks SET active=0 WHERE session_id=? AND task_id=?",
                        (id_, task_id),
                    )
            else:
                if operation == "REPLACE":
                    conn.execute("UPDATE shield_tasks SET active=0 WHERE session_id=?", (id_,))
                for instruction in instructions:
                    # Text deduplication is exact after extraction, not embedding/semantic matching.
                    existing = conn.execute(
                        "SELECT task_id FROM shield_tasks WHERE session_id=? AND text=?",
                        (id_, instruction.text),
                    ).fetchone()
                    if existing:
                        conn.execute(
                            "UPDATE shield_tasks SET active=1 WHERE session_id=? AND task_id=?",
                            (id_, existing[0]),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO shield_tasks VALUES(?,?,?,?,1)",
                            (id_, instruction.instruction_id, instruction.text, pack(instruction)),
                        )
                if (
                    conn.execute(
                        "SELECT COUNT(*) FROM shield_tasks WHERE session_id=? AND active=1", (id_,)
                    ).fetchone()[0]
                    > max_tasks
                ):
                    raise ControlError("TASK_SHIELD_TASK_LIMIT", 400)
            conn.execute("UPDATE shield_sessions SET revision=revision+1 WHERE id=?", (id_,))
            conn.execute(
                "INSERT INTO shield_messages VALUES(?,?,?,?,?,?)",
                (id_, message.message_id, expected_revision + 1, "USER", operation, pack(body)),
            )
            conn.execute(
                "INSERT INTO shield_context(session_id,body) VALUES(?,?)",
                (
                    id_,
                    pack(
                        {
                            "message": message.model_dump(),
                            "revision": expected_revision + 1,
                            "trust": "AUTHENTICATED_USER",
                        }
                    ),
                ),
            )
        return True

    def history(self, id_, budget):
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT body FROM shield_context WHERE session_id=? ORDER BY seq DESC LIMIT 50",
                (id_,),
            ).fetchall()
        # Each context record is a whole message or an atomic call/output pair. Never split pairs.
        result = []
        size = 0
        for row in rows:
            if size + len(row[0]) > budget:
                break
            result.append(json.loads(row[0]))
            size += len(row[0])
        return list(reversed(result))

    def context(self, id_, body):
        with self.store.connection(write=True) as conn:
            conn.execute(
                "INSERT INTO shield_context(session_id,body) VALUES(?,?)", (id_, pack(body))
            )

    def report(self, value, now):
        with self.store.connection(write=True) as conn:
            row = conn.execute(
                "SELECT revision FROM shield_sessions WHERE id=?", (value.session_id,)
            ).fetchone()
            if not row or row[0] != value.revision:
                raise ControlError("TASK_SHIELD_STALE_TASKS")
            conn.execute(
                "INSERT INTO shield_checks VALUES(?,?,?,?,?)",
                (value.check_id, value.session_id, value.revision, now, pack(value)),
            )

    def check_record(self, id_):
        with self.store.connection() as conn:
            row = conn.execute("SELECT body FROM shield_checks WHERE check_id=?", (id_,)).fetchone()
        if not row:
            raise ControlError("TASK_SHIELD_CHECK_NOT_FOUND", 404)
        return json.loads(row[0])

    def event(self, id_, kind, now, body):
        with self.store.connection(write=True) as conn:
            conn.execute(
                "INSERT INTO shield_events(session_id,kind,created_at,body) VALUES(?,?,?,?)",
                (id_, kind, now, pack(body)),
            )

    def audit(self, id_, limit=50):
        self.session(id_)
        with self.store.connection() as conn:
            checks = conn.execute(
                "SELECT body FROM shield_checks WHERE session_id=? ORDER BY rowid DESC LIMIT ?",
                (id_, max(1, min(limit, 100))),
            ).fetchall()
            events = conn.execute(
                "SELECT kind,created_at,body FROM shield_events WHERE session_id=? ORDER BY seq DESC LIMIT ?",
                (id_, max(1, min(limit, 100))),
            ).fetchall()
        return {
            "checks": [json.loads(r[0]) for r in checks],
            "events": [{**dict(r), "body": json.loads(r["body"])} for r in events],
        }
