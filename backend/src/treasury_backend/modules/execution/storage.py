"""SQLite WAL + content-addressed immutable artifacts; survives HTTP/process retries."""

import json
import sqlite3
from filelock import FileLock
from contextlib import contextmanager
from pathlib import Path
from treasury_backend.modules.execution.crypto import canonical, content_hash
from treasury_backend.modules.execution.errors import PlaneError


class Store:
    def __init__(self, root: Path):
        self.root = root
        (root / "artifacts").mkdir(parents=True, exist_ok=True)
        self.db_path = root / "state.sqlite3"
        self.lock = FileLock(str(root / "operations.lock"), timeout=120)
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, value TEXT, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS counters(id TEXT PRIMARY KEY, value INTEGER);
                CREATE TABLE IF NOT EXISTS idempotency(scope TEXT, key TEXT, hash TEXT, value TEXT, PRIMARY KEY(scope,key));
                CREATE TABLE IF NOT EXISTS submissions(build_id TEXT PRIMARY KEY, request_hash TEXT, tx_hash TEXT, raw_tx TEXT, value TEXT);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def put(self, kind: str, key: str, value):
        encoded = canonical(value).decode()
        with self.db() as db:
            old = db.execute(
                "SELECT value FROM records WHERE kind=? AND id=?", (kind, key)
            ).fetchone()
            if old and old[0] != encoded:
                raise PlaneError(
                    "HASH_MISMATCH", "Immutable record already exists", 409
                )
            db.execute(
                "INSERT OR IGNORE INTO records VALUES(?,?,?)", (kind, key, encoded)
            )

    def get(self, kind, key):
        with self.db() as db:
            row = db.execute(
                "SELECT value FROM records WHERE kind=? AND id=?", (kind, key)
            ).fetchone()
        if not row:
            raise PlaneError("NOT_FOUND", "Unknown resource", 404)
        return json.loads(row[0])

    def transaction_nonce(self, address, pending):
        """Allocate an EOA nonce across swap and transfer journals on this execution store."""
        key="relayer-eoa:"+address.lower()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT value FROM counters WHERE id=?", (key,)).fetchone()
            value=max(pending,int(row[0]) if row else pending)
            db.execute("INSERT INTO counters VALUES (?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",(key,value+1))
            return value

    def nonce(self, namespace):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO counters VALUES(?,1000)", (namespace,))
            db.execute("UPDATE counters SET value=value+1 WHERE id=?", (namespace,))
            return str(
                db.execute(
                    "SELECT value FROM counters WHERE id=?", (namespace,)
                ).fetchone()[0]
            )

    def artifact(self, value):
        h = content_hash(value)
        path = self.root / "artifacts" / f"{h[2:]}.json"
        data = canonical(value)
        # Content address makes concurrent identical writes harmless; atomic rename avoids partial reads.
        import os
        import tempfile

        fd, tmp = tempfile.mkstemp(dir=path.parent)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return {"ref": f"/v1/artifacts/{h[2:]}", "content_hash": h}

    def read_artifact(self, h):
        import re

        if not re.fullmatch(r"[0-9a-f]{64}", h):
            raise PlaneError("NOT_FOUND", "Invalid artifact", 404)
        path = self.root / "artifacts" / f"{h}.json"
        if not path.is_file():
            raise PlaneError("NOT_FOUND", "Unknown artifact", 404)
        data = path.read_bytes()
        from treasury_backend.modules.execution.crypto import keccak

        if keccak(data) != "0x" + h:
            raise PlaneError("HASH_MISMATCH", "Artifact corrupted", 409)
        return data

    def idempotent(self, scope, key, body, operation, refresh=False):
        # Caller holds the process-shared file lock. Submit also has a durable broadcast journal.
        h = content_hash(body)
        cached = None
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT hash,value FROM idempotency WHERE scope=? AND key=?",
                (scope, key),
            ).fetchone()
            if row:
                if row[0] != h:
                    raise PlaneError(
                        "IDEMPOTENCY_CONFLICT", "Key reused with different payload", 409
                    )
                cached = json.loads(row[1])
        if cached is not None:
            # Execute refreshes status / rebroadcasts journaled bytes after RPC loss.
            # The durable submission journal prevents creating another transaction.
            return operation() if refresh else cached
        result = operation()
        with self.db() as db:
            row = db.execute(
                "SELECT hash,value FROM idempotency WHERE scope=? AND key=?",
                (scope, key),
            ).fetchone()
            if row:
                if row[0] != h:
                    raise PlaneError(
                        "IDEMPOTENCY_CONFLICT", "Key reused with different payload", 409
                    )
                return json.loads(row[1])
            db.execute(
                "INSERT INTO idempotency VALUES(?,?,?,?)",
                (scope, key, h, canonical(result).decode()),
            )
        return result
