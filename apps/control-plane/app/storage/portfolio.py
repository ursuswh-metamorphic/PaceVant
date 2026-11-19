"""Additive SQLite v2: immutable observations plus rebuildable scoped projections."""

import json

from app.errors import ControlError
from app.portfolio.observations import content_hash, verify_snapshot_hash

SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS portfolio_snapshots(
 snapshot_id TEXT PRIMARY KEY, mode TEXT NOT NULL, chain_id INTEGER NOT NULL, vault TEXT NOT NULL,
 block_number INTEGER NOT NULL, block_hash TEXT NOT NULL, observed_at INTEGER NOT NULL,
 content_hash TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS portfolio_scope ON portfolio_snapshots(mode,chain_id,vault,block_number,observed_at);
CREATE TABLE IF NOT EXISTS portfolio_links(
 id TEXT PRIMARY KEY,snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id),
 workflow_id TEXT,decision_id TEXT,build_id TEXT,tx_hash TEXT,phase TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS portfolio_status_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id),
 state TEXT NOT NULL,at INTEGER NOT NULL,reason TEXT NOT NULL,dedup TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS treasury_versions(mode TEXT NOT NULL,chain_id INTEGER NOT NULL,vault TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(mode,chain_id,vault));
CREATE TABLE IF NOT EXISTS monitor_jobs(decision_id TEXT PRIMARY KEY,workflow_id TEXT NOT NULL,mode TEXT NOT NULL,
 chain_id INTEGER NOT NULL,vault TEXT NOT NULL,tx_hash TEXT,state TEXT NOT NULL,next_at INTEGER NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0,lease TEXT,lease_until INTEGER NOT NULL DEFAULT 0,body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS monitor_due ON monitor_jobs(next_at,lease_until);
CREATE TABLE IF NOT EXISTS outcome_observations(id TEXT PRIMARY KEY,decision_id TEXT NOT NULL,
 at INTEGER NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcome_projections(decision_id TEXT PRIMARY KEY,mode TEXT NOT NULL,
 chain_id INTEGER NOT NULL,vault TEXT NOT NULL,tx_hash TEXT,semantic_hash TEXT NOT NULL,body TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS outcome_transaction_scope ON outcome_projections(mode,chain_id,vault,tx_hash) WHERE tx_hash IS NOT NULL;
CREATE TABLE IF NOT EXISTS state_schema_versions(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO state_schema_versions VALUES(2);
"""
for _table in (
    "portfolio_snapshots",
    "portfolio_links",
    "portfolio_status_events",
    "outcome_observations",
):
    for _action in ("UPDATE", "DELETE"):
        SCHEMA_V2 += f"CREATE TRIGGER IF NOT EXISTS {_table}_no_{_action.lower()} BEFORE {_action} ON {_table} BEGIN SELECT RAISE(ABORT,'immutable portfolio/outcome evidence'); END;\n"


def pack(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class PortfolioStore:
    @staticmethod
    def _snapshot_event(conn, id_, state, now, reason="", ref=""):
        dedup = content_hash({"snapshot": id_, "state": state, "reason": reason, "ref": ref})
        conn.execute(
            "INSERT OR IGNORE INTO portfolio_status_events(snapshot_id,state,at,reason,dedup) VALUES(?,?,?,?,?)",
            (id_, state, now, reason, dedup),
        )

    @staticmethod
    def _link(
        conn, snapshot_id, phase, workflow_id=None, decision_id=None, build_id=None, tx_hash=None
    ):
        fields = dict(
            snapshot_id=snapshot_id,
            phase=phase,
            workflow_id=workflow_id,
            decision_id=decision_id,
            build_id=build_id,
            tx_hash=tx_hash,
        )
        conn.execute(
            "INSERT OR IGNORE INTO portfolio_links VALUES(?,?,?,?,?,?,?)",
            (content_hash(fields), snapshot_id, workflow_id, decision_id, build_id, tx_hash, phase),
        )

    def save_snapshot(
        self,
        snapshot,
        *,
        phase="OBSERVED",
        workflow_id=None,
        decision_id=None,
        build_id=None,
        tx_hash=None,
    ):
        if not verify_snapshot_hash(snapshot):
            raise ControlError("SNAPSHOT_HASH_MISMATCH")
        body = pack(snapshot.model_dump())
        with self.connection(write=True) as conn:
            row = conn.execute(
                "SELECT body FROM portfolio_snapshots WHERE snapshot_id=?", (snapshot.snapshot_id,)
            ).fetchone()
            if row and row[0] != body:
                raise ControlError("IMMUTABLE_SNAPSHOT_CONFLICT")
            conn.execute(
                "INSERT OR IGNORE INTO portfolio_snapshots VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    snapshot.snapshot_id,
                    snapshot.mode,
                    snapshot.chain_id,
                    snapshot.vault_address,
                    snapshot.block_number,
                    snapshot.block_hash,
                    snapshot.observed_at,
                    snapshot.content_hash,
                    body,
                ),
            )
            self._snapshot_event(conn, snapshot.snapshot_id, "OBSERVED", snapshot.observed_at)
            if snapshot.verification_status == "VERIFIED":
                self._snapshot_event(conn, snapshot.snapshot_id, "VERIFIED", snapshot.observed_at)
            self._link(
                conn, snapshot.snapshot_id, phase, workflow_id, decision_id, build_id, tx_hash
            )
        return snapshot.snapshot_id

    def snapshot_record(self, id_):
        with self.connection() as conn:
            row = conn.execute(
                "SELECT body FROM portfolio_snapshots WHERE snapshot_id=?", (id_,)
            ).fetchone()
            if not row:
                raise ControlError("SNAPSHOT_NOT_FOUND", 404)
            events = conn.execute(
                "SELECT state,at,reason FROM portfolio_status_events WHERE snapshot_id=? ORDER BY sequence",
                (id_,),
            ).fetchall()
            links = conn.execute(
                "SELECT workflow_id,decision_id,build_id,tx_hash,phase FROM portfolio_links WHERE snapshot_id=? ORDER BY id",
                (id_,),
            ).fetchall()
        return {
            "snapshot": json.loads(row[0]),
            "lifecycle": [dict(r) for r in events],
            "links": [dict(r) for r in links],
            "state": events[-1]["state"] if events else "OBSERVED",
        }

    def scoped_snapshots(self, mode, chain_id, vault, *, limit=50, before=None):
        limit = max(1, min(100, limit))
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT snapshot_id FROM portfolio_snapshots WHERE mode=? AND chain_id=? AND vault=? AND observed_at<=? ORDER BY block_number DESC,observed_at DESC,snapshot_id DESC LIMIT ?",
                (mode, chain_id, vault.lower(), before if before is not None else 2**53 - 1, limit),
            ).fetchall()
        return [self.snapshot_record(row[0]) for row in rows]

    def current_snapshot(self, mode, chain_id, vault):
        with self.connection() as conn:
            row = conn.execute(
                """SELECT p.snapshot_id FROM portfolio_snapshots p
             WHERE p.mode=? AND p.chain_id=? AND p.vault=? AND NOT EXISTS(
                SELECT 1 FROM portfolio_status_events s WHERE s.snapshot_id=p.snapshot_id AND s.state='INVALIDATED')
             ORDER BY p.block_number DESC,p.observed_at DESC,p.snapshot_id DESC LIMIT 1""",
                (mode, chain_id, vault.lower()),
            ).fetchone()
        return self.snapshot_record(row[0]) if row else None

    def invalidate_snapshot(self, id_, now, reason="REORG_DETECTED"):
        with self.connection(write=True) as conn:
            self._snapshot_event(conn, id_, "INVALIDATED", now, reason)

    def track_execution(self, workflow_id, decision_id, mode, built, now, tx_hash=None):
        with self.connection(write=True) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO monitor_jobs(decision_id,workflow_id,mode,chain_id,vault,tx_hash,state,next_at,body) VALUES(?,?,?,?,?,?, 'QUEUED',?,?)",
                (
                    decision_id,
                    workflow_id,
                    mode,
                    built.chain_id,
                    built.vault_address.lower(),
                    tx_hash,
                    now,
                    pack({"build_id": built.build_id}),
                ),
            )
            if tx_hash:
                old = conn.execute(
                    "SELECT tx_hash FROM monitor_jobs WHERE decision_id=?", (decision_id,)
                ).fetchone()[0]
                if old and old != tx_hash:
                    raise ControlError("MONITORED_TRANSACTION_CONFLICT")
                conn.execute(
                    "UPDATE monitor_jobs SET tx_hash=? WHERE decision_id=?", (tx_hash, decision_id)
                )

    def claim_monitor(self, id_, owner, now, *, force=False):
        with self.connection(write=True) as conn:
            row = conn.execute("SELECT * FROM monitor_jobs WHERE decision_id=?", (id_,)).fetchone()
            if not row or row["lease_until"] > now or (not force and row["next_at"] > now):
                return None
            conn.execute(
                "UPDATE monitor_jobs SET lease=?,lease_until=? WHERE decision_id=?",
                (owner, now + 300, id_),
            )
            return dict(row)

    def due_monitors(self, mode, now, limit=20):
        with self.connection() as conn:
            return [
                row[0]
                for row in conn.execute(
                    "SELECT decision_id FROM monitor_jobs WHERE mode=? AND next_at<=? AND lease_until<=? ORDER BY next_at,decision_id LIMIT ?",
                    (mode, now, now, max(1, min(limit, 50))),
                )
            ]

    def monitor_job(self, id_):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM monitor_jobs WHERE decision_id=?", (id_,)).fetchone()
        return dict(row) if row else None

    def release_monitor(self, id_, owner, now, state, details):
        with self.connection(write=True) as conn:
            row = conn.execute(
                "SELECT attempts FROM monitor_jobs WHERE decision_id=? AND lease=?", (id_, owner)
            ).fetchone()
            if not row:
                return
            attempts = row[0] + 1
            delay = 30 if state in {"CONFIRMED", "REVERTED"} else min(60, 2 ** min(attempts, 6))
            conn.execute(
                "UPDATE monitor_jobs SET state=?,attempts=?,next_at=?,lease=NULL,lease_until=0,body=? WHERE decision_id=? AND lease=?",
                (state, attempts, now + delay, pack(details), id_, owner),
            )

    def outcome_projection(self, id_):
        with self.connection() as conn:
            row = conn.execute(
                "SELECT body FROM outcome_projections WHERE decision_id=?", (id_,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def outcome_history(self, mode, chain_id, vault, limit=50):
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT decision_id,body FROM outcome_projections WHERE mode=? AND chain_id=? AND vault=? ORDER BY rowid DESC LIMIT ?",
                (mode, chain_id, vault.lower(), max(1, min(100, limit))),
            ).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def outcome_audit(self, id_, limit=50):
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id,at,body FROM outcome_observations WHERE decision_id=? ORDER BY rowid DESC LIMIT ?",
                (id_, max(1, min(100, limit))),
            ).fetchall()
        return [{"observation_id": r["id"], "at": r["at"], **json.loads(r["body"])} for r in rows]

    def record_poll(self, job, now, value):
        with self.connection(write=True) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO outcome_observations VALUES(?,?,?,?)",
                (content_hash(value), job["decision_id"], now, pack(value)),
            )

    def commit_outcome(
        self, job, owner, now, value, public_state, *, pre_id=None, post_id=None, invalidate=False
    ):
        observation_id = content_hash(value)
        report = value["verification"]
        semantic = content_hash(
            {
                "tx": job["tx_hash"],
                "block": report.get("block_hash"),
                "status": public_state,
                "canonical": report.get("canonical"),
                "verification": report["verification_status"],
                "attribution": value.get("attribution_status"),
                "gas_verified": report.get("gas_verified"),
                "gas_cost_wei": report.get("gas_cost_wei"),
                "token_in_delta": report.get("token_in_delta_base_units"),
                "token_out_delta": report.get("token_out_delta_base_units"),
            }
        )
        with self.connection(write=True) as conn:
            lease = conn.execute(
                "SELECT lease FROM monitor_jobs WHERE decision_id=?", (job["decision_id"],)
            ).fetchone()
            if not lease or lease[0] != owner:
                return False
            conn.execute(
                "INSERT OR IGNORE INTO outcome_observations VALUES(?,?,?,?)",
                (observation_id, job["decision_id"], now, pack(value)),
            )
            old = conn.execute(
                "SELECT semantic_hash,body FROM outcome_projections WHERE decision_id=?",
                (job["decision_id"],),
            ).fetchone()
            if invalidate and old:
                previous = json.loads(old["body"])
                if previous.get("post_snapshot_id"):
                    self._snapshot_event(
                        conn,
                        previous["post_snapshot_id"],
                        "INVALIDATED",
                        now,
                        "REORG_DETECTED",
                        observation_id,
                    )
            conn.execute(
                "INSERT INTO outcome_projections VALUES(?,?,?,?,?,?,?) ON CONFLICT(decision_id) DO UPDATE SET semantic_hash=excluded.semantic_hash,body=excluded.body,tx_hash=excluded.tx_hash",
                (
                    job["decision_id"],
                    job["mode"],
                    job["chain_id"],
                    job["vault"],
                    job["tx_hash"],
                    semantic,
                    pack(value),
                ),
            )
            if not old or old[0] != semantic:
                conn.execute(
                    "INSERT INTO treasury_versions VALUES(?,?,?,1) ON CONFLICT(mode,chain_id,vault) DO UPDATE SET version=version+1",
                    (job["mode"], job["chain_id"], job["vault"]),
                )
            if pre_id:
                self._link(
                    conn,
                    pre_id,
                    "PRE",
                    job["workflow_id"],
                    job["decision_id"],
                    value["build_id"],
                    job["tx_hash"],
                )
            if post_id:
                self._link(
                    conn,
                    post_id,
                    "POST",
                    job["workflow_id"],
                    job["decision_id"],
                    value["build_id"],
                    job["tx_hash"],
                )
                if public_state in {"CONFIRMED", "REVERTED"}:
                    self._snapshot_event(conn, post_id, "RECONCILED", now, "", semantic)
                if public_state in {"CONFIRMED", "REVERTED"} and pre_id and pre_id != post_id:
                    self._snapshot_event(
                        conn, pre_id, "SUPERSEDED", now, "POST_EXECUTION_OBSERVED", semantic
                    )
            attestation = conn.execute(
                "SELECT state FROM attestations WHERE decision_id=?", (job["decision_id"],)
            ).fetchone()
            if attestation and attestation[0] != public_state:
                conn.execute(
                    "UPDATE attestations SET state=? WHERE decision_id=?",
                    (public_state, job["decision_id"]),
                )
                details = {
                    "decision_id": job["decision_id"],
                    "receipt": value.get("receipt"),
                    "reconciliation_id": observation_id,
                    "pre_snapshot_id": pre_id,
                    "post_snapshot_id": post_id,
                    "reason_codes": value.get("reason_codes", []),
                }
                if report.get("gas_verified") and report.get("canonical"):
                    details["execution_fee"] = {
                        "chain_id": job["chain_id"],
                        "vault_address": job["vault"],
                        "tx_hash": job["tx_hash"],
                        "utc_day": report["block_timestamp"] // 86400,
                        "gas_cost_wei": report["gas_cost_wei"],
                        "payer_role": "RELAYER",
                    }
                if value.get("post_execution_balances"):
                    details["post_execution_balances"] = value["post_execution_balances"]
                self._event(conn, job["workflow_id"], public_state, now, details)
            return True
