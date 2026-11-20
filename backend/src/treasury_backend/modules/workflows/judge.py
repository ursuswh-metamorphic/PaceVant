"""Bounded asynchronous adapter around the existing fork workflow; no signer here."""

import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from filelock import FileLock

from treasury_backend.core.errors import ControlError
from treasury_backend.paths import ROOT

SCENARIOS = [
    {"id":"payment", "title":"Secure USDC Payment", "description":"An approved payment, verified down to the actual recipient receipt.",
     "operation":"USDC_PAYMENT", "amount":"10000", "input_decimals":6, "token_in":"USDC", "token_out":"USDC", "recipient_label":"Owner-approved isolated fork EOA"},
    {"id":"swap", "title":"Secure Token Swap", "description":"Oracle-protected USDC to WAVAX through the approved LFJ V1 pool.",
     "operation":"SWAP_EXACT_IN", "amount":"1", "input_decimals":6, "token_in":"USDC", "token_out":"WAVAX", "recipient_label":"Isolated PolicyVault"},
    {"id":"guard", "title":"Unsafe Transaction Rejected", "description":"Evaluate a reverse route or unapproved recipient against the real security gates.",
     "operation":"SWAP_EXACT_IN", "amount":"50000000000000", "input_decimals":18, "token_in":"WAVAX", "token_out":"USDC", "recipient_label":"Fixed server-selected security case"},
]
ACTIVE = {"QUEUED", "RUNNING"}


def code(error):
    value = getattr(error, "code", str(error) if isinstance(error, ValueError) else "DEMO_DEPENDENCY_UNAVAILABLE")
    return value if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value) else "DEMO_DEPENDENCY_UNAVAILABLE"


def stop_tree(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"), "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def worker_environment(settings):
    # Anvil and this process never inherit live wallet keys, tokens, or root .env.
    from treasury_contracts.toolchain import native_tool_environment

    allowed = {k:v for k, v in os.environ.items() if k.startswith(("PACEVANT_SHIELD_", "GROQ_", "GEMINI_", "XINGCHI_", "DEEPSEEK_"))}
    allowed.update(PYTHONPATH=os.pathsep.join((str(ROOT / "backend/src"), str(ROOT / "packages/contracts-api"))),
        PACEVANT_JUDGE_RPC_URL=settings.rpc_url, PACEVANT_JUDGE_ORACLE_WAIT_SECONDS=str(settings.wait_oracle_seconds))
    return native_tool_environment() | allowed


class JudgeController:
    def __init__(self, settings, *, runner=None, clock=time.time):
        self.settings, self.clock = settings, clock
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = settings.data_dir / "judge.sqlite3"
        self.instance = FileLock(settings.data_dir / "judge-instance.lock", timeout=0)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="isolated-judge")
        self.runner = runner or self.run_worker
        self.process = None
        self.closing = False
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS judge_jobs(
                  id TEXT PRIMARY KEY, visitor TEXT NOT NULL, ip_hash TEXT NOT NULL, request_key TEXT NOT NULL,
                  scenario TEXT NOT NULL, state TEXT NOT NULL, created_at INTEGER NOT NULL, body TEXT NOT NULL,
                  UNIQUE(visitor,request_key));
                CREATE INDEX IF NOT EXISTS judge_created ON judge_jobs(created_at);
                CREATE TABLE IF NOT EXISTS judge_migrations(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO judge_migrations VALUES(1);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def start(self):
        self.instance.acquire()
        with self.db() as db:
            for row in db.execute("SELECT * FROM judge_jobs WHERE state IN ('QUEUED','RUNNING')").fetchall():
                result = json.loads(row["body"])
                result.update(status="INTERRUPTED", reason_code="FORK_RUN_INTERRUPTED", terminal=True)
                db.execute("UPDATE judge_jobs SET state='INTERRUPTED',body=? WHERE id=?", (json.dumps(result), row["id"]))
        self.cleanup()

    def cleanup(self):
        # Completed evidence is already in SQLite; only expire disposable run
        # directories older than seven days, never journals/records themselves.
        root = (self.settings.data_dir / "runs").resolve()
        with self.db() as db:
            rows = db.execute("SELECT id FROM judge_jobs WHERE created_at<? AND state NOT IN ('QUEUED','RUNNING') LIMIT 100", (int(self.clock())-7*86400,)).fetchall()
        for row in rows:
            target = (root / row[0]).resolve()
            if target.parent == root and target.name.startswith("judge_") and target.is_dir():
                shutil.rmtree(target)

    def close(self):
        self.closing = True
        if self.process:
            stop_tree(self.process)
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.instance.release()

    def configured(self):
        return self.settings.configured()

    def busy(self):
        with self.db() as db:
            return db.execute("SELECT COUNT(*) FROM judge_jobs WHERE state IN ('QUEUED','RUNNING')").fetchone()[0] > 0

    def remaining(self, visitor):
        day = int(self.clock()) // 86400 * 86400
        with self.db() as db:
            count = db.execute("SELECT COUNT(*) FROM judge_jobs WHERE visitor=? AND created_at>=?", (visitor, day)).fetchone()[0]
        return max(0, self.settings.daily_limit - count)

    def create(self, visitor, ip, scenario, key):
        if scenario not in {s["id"] for s in SCENARIOS} or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key or ""):
            raise ControlError("INVALID_REQUEST", 400)
        now = int(self.clock())
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM judge_jobs WHERE visitor=? AND request_key=?", (visitor, key)).fetchone()
            if previous:
                if previous["scenario"] != scenario:
                    raise ControlError("IDEMPOTENCY_CONFLICT", 409)
                return self.read(previous)
            if not self.configured() or self.closing:
                raise ControlError("DEMO_NOT_CONFIGURED", 503)
            if db.execute("SELECT COUNT(*) FROM judge_jobs WHERE state IN ('QUEUED','RUNNING')").fetchone()[0]:
                raise ControlError("DEMO_BUSY", 429)
            since = now // 86400 * 86400
            if db.execute("SELECT COUNT(*) FROM judge_jobs WHERE visitor=? AND created_at>=?", (visitor, since)).fetchone()[0] >= self.settings.daily_limit:
                raise ControlError("DEMO_RATE_LIMIT", 429)
            if db.execute("SELECT COUNT(*) FROM judge_jobs WHERE ip_hash=? AND created_at>?", (ip_hash, now-3600)).fetchone()[0] >= self.settings.ip_hourly_limit:
                raise ControlError("DEMO_RATE_LIMIT", 429)
            if db.execute("SELECT COUNT(*) FROM judge_jobs WHERE created_at>=?", (since,)).fetchone()[0] >= self.settings.global_daily_limit:
                raise ControlError("DEMO_DAILY_LIMIT", 429)
            if shutil.disk_usage(self.settings.data_dir).free < 512 * 1024**2:
                raise ControlError("DEMO_STORAGE_LOW", 503)
            id_ = "judge_" + uuid4().hex
            value = {"job_id":id_, "scenario":scenario, "status":"QUEUED", "created_at":now, "environment":"ANVIL_FORK",
                "phase":"QUEUED", "public_chain_broadcast":False, "terminal":False, "semantic_scope":"REAL_CONFIGURED_PROVIDER"}
            db.execute("INSERT INTO judge_jobs VALUES(?,?,?,?,?,?,?,?)", (id_, visitor, ip_hash, key, scenario, "QUEUED", now, json.dumps(value)))
        self.pool.submit(self.execute, id_, scenario)
        return value

    def update(self, id_, **values):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM judge_jobs WHERE id=?", (id_,)).fetchone()
            body = json.loads(row["body"]) | values
            db.execute("UPDATE judge_jobs SET state=?,body=? WHERE id=?", (body["status"], json.dumps(body), id_))

    def execute(self, id_, scenario):
        self.update(id_, status="RUNNING", phase="PREPARING_FORK")
        try:
            result = self.runner(id_, scenario)
            self.update(id_, **(result | {"terminal":True}))
        except Exception as error:
            self.update(id_, status="UNAVAILABLE", reason_code=code(error), terminal=True)

    def run_worker(self, id_, scenario):
        if self.closing:
            raise ValueError("FORK_RUN_INTERRUPTED")
        directory = self.settings.data_dir / "runs" / id_
        directory.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, "-m", "treasury_backend.operations.judge_worker", "--scenario", scenario, "--directory", str(directory)]
        options = {"creationflags":subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session":True}
        proc = subprocess.Popen(command, cwd=ROOT, env=worker_environment(self.settings), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        self.process = proc
        if self.closing:
            stop_tree(proc)
        try:
            try:
                proc.wait(timeout=self.settings.timeout_seconds)
            except subprocess.TimeoutExpired:
                stop_tree(proc)
                raise ValueError("DEMO_TIMEOUT") from None
            result_path = directory / "result.json"
            if not result_path.exists():
                raise ValueError("FORK_RUN_INTERRUPTED")
            result = json.loads(result_path.read_text())
            if result.get("environment") != "ANVIL_FORK" or result.get("public_chain_broadcast") is not False:
                raise ValueError("ISOLATION_EVIDENCE_INVALID")
            return result
        finally:
            stop_tree(proc)
            self.process = None

    def read(self, row):
        value = json.loads(row["body"])
        if value["status"] in ACTIVE:
            path = self.settings.data_dir / "runs" / value["job_id"] / "progress.json"
            if path.exists():
                try:
                    progress = json.loads(path.read_text())
                    value.update({k:progress[k] for k in ("workflow", "phase", "active_stage", "source_block", "semantic_scope") if k in progress})
                except (OSError, ValueError):
                    pass
        return value

    def get(self, visitor, id_=None, key=None):
        with self.db() as db:
            row = db.execute("SELECT * FROM judge_jobs WHERE visitor=? AND " + ("id=?" if id_ else "request_key=?"), (visitor, id_ or key)).fetchone()
        if not row:
            raise ControlError("JUDGE_REQUEST_NOT_FOUND", 404)
        return self.read(row)

    def history(self, visitor):
        with self.db() as db:
            rows = db.execute("SELECT * FROM judge_jobs WHERE visitor=? ORDER BY created_at DESC,rowid DESC LIMIT 30", (visitor,)).fetchall()
        return [self.read(row) for row in rows]
