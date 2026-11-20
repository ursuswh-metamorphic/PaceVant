"""One prepaid demo allowance in the existing execution DB. No chain writes."""

import json
import sqlite3
import time
from contextlib import contextmanager
from uuid import uuid4


class CreditError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_account(
 id INTEGER PRIMARY KEY CHECK(id=1), address TEXT, chain_id INTEGER, vault TEXT, relayer TEXT,
 credit_wei TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS demo_requests(
 request_key TEXT PRIMARY KEY, goal TEXT NOT NULL, workflow_id TEXT UNIQUE NOT NULL,
 state TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS demo_builds(build_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS demo_gas_reservations(
 tx_hash TEXT PRIMARY KEY, build_id TEXT UNIQUE NOT NULL, max_cost_wei TEXT NOT NULL,
 state TEXT NOT NULL, actual_cost_wei TEXT NOT NULL, block_hash TEXT, receipt_status TEXT,
 gas_used TEXT, effective_gas_price_wei TEXT);
CREATE TABLE IF NOT EXISTS demo_gas_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT UNIQUE NOT NULL,
 tx_hash TEXT, kind TEXT NOT NULL, delta_wei TEXT NOT NULL, at INTEGER NOT NULL, body TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS demo_gas_events_no_update BEFORE UPDATE ON demo_gas_events
BEGIN SELECT RAISE(ABORT, 'immutable gas ledger'); END;
CREATE TRIGGER IF NOT EXISTS demo_gas_events_no_delete BEFORE DELETE ON demo_gas_events
BEGIN SELECT RAISE(ABORT, 'immutable gas ledger'); END;
"""


class GasCreditLedger:
    def __init__(self, path, config, *, chain_id, vault, relayer, confirmations=2):
        self.path, self.config = path, config
        self.chain_id, self.vault, self.relayer = chain_id, vault.lower(), relayer.lower()
        self.confirmations = confirmations
        with self.db() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO demo_account VALUES(1,?,?,?,?,?)",
                (
                    config.address.lower(),
                    chain_id,
                    self.vault,
                    self.relayer,
                    str(config.initial_credit_wei),
                ),
            )
            row = db.execute(
                "SELECT address,chain_id,vault,relayer FROM demo_account WHERE id=1"
            ).fetchone()
            if tuple(row) != (config.address.lower(), chain_id, self.vault, self.relayer):
                raise CreditError("DEMO_ACCOUNT_SCOPE_CHANGED")
            credit = int(db.execute("SELECT credit_wei FROM demo_account WHERE id=1").fetchone()[0])
            self.event(
                db,
                "allocation",
                None,
                "SPONSOR_ALLOCATION",
                credit,
                {"meaning": "Off-chain demo allowance, not an on-chain user deposit"},
            )

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def event(db, key, tx, kind, delta, body):
        db.execute(
            "INSERT OR IGNORE INTO demo_gas_events(event_key,tx_hash,kind,delta_wei,at,body) VALUES(?,?,?,?,?,?)",
            (key, tx, kind, str(delta), int(time.time()), json.dumps(body)),
        )

    @staticmethod
    def amounts(db):
        credit = int(db.execute("SELECT credit_wei FROM demo_account WHERE id=1").fetchone()[0])
        rows = db.execute(
            "SELECT max_cost_wei,actual_cost_wei,state FROM demo_gas_reservations"
        ).fetchall()
        spent = sum(int(r[1]) for r in rows if r[2] == "SETTLED")
        reserved = sum(int(r[0]) for r in rows if r[2] != "SETTLED")
        return credit, spent, reserved

    def account(self):
        with self.db() as db:
            credit, spent, reserved = self.amounts(db)
            txs = db.execute(
                "SELECT r.*,b.workflow_id FROM demo_gas_reservations r JOIN demo_builds b USING(build_id) ORDER BY r.rowid DESC LIMIT 50"
            ).fetchall()
            events = db.execute(
                "SELECT * FROM demo_gas_events ORDER BY sequence DESC LIMIT 100"
            ).fetchall()
            requests = db.execute(
                "SELECT workflow_id,state,created_at FROM demo_requests ORDER BY rowid DESC LIMIT 50"
            ).fetchall()
        return {
            "account_id": "demo",
            "label": "PaceVant - Demo User",
            "wallet_address": self.config.address,
            "chain_id": self.chain_id,
            "vault_address": self.vault,
            "relayer_address": self.relayer,
            "credit_kind": "SPONSOR_ALLOCATED_OFFCHAIN_DEMO_CREDIT",
            "credit_is_wallet_balance": False,
            "allocated_wei": str(credit),
            "spent_wei": str(spent),
            "reserved_wei": str(reserved),
            "available_wei": str(credit - spent - reserved),
            "max_transaction_fee_wei": str(self.config.max_transaction_fee_wei),
            "transactions": [dict(r) for r in txs],
            "requests": [dict(r) for r in requests],
            "ledger": [{**dict(r), "body": json.loads(r["body"])} for r in events],
        }

    def begin_request(self, key, goal):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM demo_requests WHERE request_key=?", (key,)).fetchone()
            if row:
                if row["goal"] != goal:
                    raise CreditError("DEMO_IDEMPOTENCY_CONFLICT")
                return dict(row), False
            if db.execute("SELECT 1 FROM demo_requests WHERE state='RUNNING'").fetchone():
                raise CreditError("DEMO_REQUEST_IN_PROGRESS")
            _, spent, held = self.amounts(db)
            total = int(db.execute("SELECT credit_wei FROM demo_account").fetchone()[0])
            if total - spent - held <= 0:
                raise CreditError("GAS_CREDIT_INSUFFICIENT")
            workflow = "workflow_" + uuid4().hex
            db.execute(
                "INSERT INTO demo_requests VALUES(?,?,?,'RUNNING',?)",
                (key, goal, workflow, int(time.time())),
            )
            return {"workflow_id": workflow, "state": "RUNNING"}, True

    def finish_request(self, workflow, state):
        with self.db() as db:
            db.execute("UPDATE demo_requests SET state=? WHERE workflow_id=?", (state, workflow))

    def owns(self, workflow):
        with self.db() as db:
            return (
                db.execute(
                    "SELECT 1 FROM demo_requests WHERE workflow_id=?", (workflow,)
                ).fetchone()
                is not None
            )

    def bind_build(self, workflow, build):
        if self.owns(workflow):
            with self.db() as db:
                db.execute("INSERT OR IGNORE INTO demo_builds VALUES(?,?)", (build, workflow))
                if (
                    db.execute(
                        "SELECT workflow_id FROM demo_builds WHERE build_id=?", (build,)
                    ).fetchone()[0]
                    != workflow
                ):
                    raise CreditError("DEMO_BUILD_SCOPE_MISMATCH")

    def billed(self, build):
        with self.db() as db:
            return (
                db.execute("SELECT 1 FROM demo_builds WHERE build_id=?", (build,)).fetchone()
                is not None
            )

    def reserve(self, db, build, tx, maximum, relayer_balance):
        """Caller inserts the raw submission in this SAME DB transaction before sending."""
        credit, spent, held = self.amounts(db)
        if maximum <= 0 or maximum > self.config.max_transaction_fee_wei:
            raise CreditError("DEMO_TRANSACTION_FEE_LIMIT")
        if credit - spent - held < maximum:
            raise CreditError("GAS_CREDIT_INSUFFICIENT")
        if relayer_balance - held < maximum:
            raise CreditError("RELAYER_GAS_INSUFFICIENT")
        db.execute(
            "INSERT INTO demo_gas_reservations VALUES(?,?,?,'RESERVED','0',NULL,NULL,NULL,NULL)",
            (tx, build, str(maximum)),
        )
        self.event(db, "reserve:" + tx, tx, "RESERVE", 0, {"reserved_wei": str(maximum)})

    def reconcile(self, report, *, invalidated=False):
        """Consume the existing verifier's facts; unavailable is never zero gas."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM demo_gas_reservations WHERE tx_hash=?", (report.tx_hash,)
            ).fetchone()
            if not row:
                return
            invalidated = invalidated or report.verification_status == "REORGED"
            if invalidated:
                if row["state"] == "SETTLED":
                    self.event(
                        db,
                        "reverse:" + uuid4().hex,
                        report.tx_hash,
                        "REORG_REVERSAL",
                        int(row["actual_cost_wei"]),
                        {"block_hash": row["block_hash"]},
                    )
                db.execute(
                    "UPDATE demo_gas_reservations SET state='REORG_HOLD',actual_cost_wei='0' WHERE tx_hash=?",
                    (report.tx_hash,),
                )
                return
            if (
                not report.canonical
                or not report.gas_verified
                or report.confirmations < self.confirmations
                or report.receipt_status not in {"SUCCESS", "REVERTED"}
                or report.verification_status not in {"VERIFIED", "MISMATCH"}
            ):
                return
            if (
                report.chain_id != self.chain_id
                or report.vault_address.lower() != self.vault
                or (report.gas_payer or "").lower() != self.relayer
                or report.build_id != row["build_id"]
            ):
                raise CreditError("GAS_RECEIPT_SCOPE_MISMATCH")
            cost = int(report.gas_used) * int(report.effective_gas_price_wei)
            if (
                cost != int(report.gas_cost_wei)
                or not 0 <= cost <= int(row["max_cost_wei"])
                or not report.block_hash
            ):
                raise CreditError("GAS_RECEIPT_COST_MISMATCH")
            if row["state"] == "SETTLED":
                if row["block_hash"] == report.block_hash and int(row["actual_cost_wei"]) == cost:
                    return
                if row["block_hash"] == report.block_hash:
                    raise CreditError("GAS_RECEIPT_COST_MISMATCH")
                # A new canonical inclusion supersedes the previous charge, preserving audit history.
                self.event(
                    db,
                    "reverse:" + uuid4().hex,
                    report.tx_hash,
                    "REORG_REVERSAL",
                    int(row["actual_cost_wei"]),
                    {"block_hash": row["block_hash"]},
                )
            self.event(
                db,
                "settle:" + uuid4().hex,
                report.tx_hash,
                "GAS_DEBIT",
                -cost,
                {
                    "gas_used": report.gas_used,
                    "effective_gas_price_wei": report.effective_gas_price_wei,
                    "receipt_status": report.receipt_status,
                    "block_hash": report.block_hash,
                },
            )
            db.execute(
                "UPDATE demo_gas_reservations SET state='SETTLED',actual_cost_wei=?,block_hash=?,receipt_status=?,gas_used=?,effective_gas_price_wei=? WHERE tx_hash=?",
                (
                    str(cost),
                    report.block_hash,
                    report.receipt_status,
                    report.gas_used,
                    report.effective_gas_price_wei,
                    report.tx_hash,
                ),
            )
