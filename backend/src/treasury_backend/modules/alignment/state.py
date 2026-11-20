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
            conn.execute(
                "INSERT INTO shield_events(session_id,kind,created_at,body) VALUES(?,?,?,?)",
                (
                    id_,
                    "MANDATE_PROTOCOL_SCHEMA",
                    now,
                    pack(
                        {
                            "mandate_hash": content_hash(mandate.model_dump()),
                            "chain_id": mandate.chain_id,
                            "vault": mandate.vault_address,
                            "configured_adapter": mandate.router,
                            "assets": [
                                {"address": mandate.token_in, "symbol": "USDC", "decimals": 6},
                                {"address": mandate.token_out, "symbol": "WAVAX", "decimals": 18},
                            ],
                            "authority": "Protocol metadata only; does not authorize additional actions",
                        }
                    ),
                ),
            )
        return self.session(id_)

    def create_evaluation(self, id_, protocol_schema, now):
        """Create an isolated offline session. This grants no wallet mandate or signing scope."""
        schema = {**protocol_schema, "authority": "OFFLINE_BENCHMARK_INPUT_ONLY"}
        with self.store.connection(write=True) as conn:
            conn.execute(
                "INSERT INTO shield_sessions VALUES(?,?,?,?,0,?)",
                (id_, None, "OFFLINE_BENCHMARK", content_hash(schema), now),
            )
            conn.execute(
                "INSERT INTO shield_events(session_id,kind,created_at,body) VALUES(?,?,?,?)",
                (id_, "MANDATE_PROTOCOL_SCHEMA", now, pack(schema)),
            )
        return self.session(id_)

    def create_operation(self, id_, manifest, now, workflow_id):
        """General fixed-operation schema; model output cannot authorize registry changes."""
        with self.store.connection(write=True) as conn:
            conn.execute("INSERT INTO shield_sessions VALUES(?,?,?,?,0,?)",
                         (id_, workflow_id, "treasury_v3", content_hash(manifest.model_dump(mode="json")), now))
            protocol = {"fixed_operations": True, "chain_id": manifest.chain_id, "vault": manifest.treasury, "configured_adapter": manifest.adapter,
                        "assets": [{"address": manifest.usdc, "symbol": "USDC", "decimals": 6},
                                   {"address": manifest.wavax, "symbol": "WAVAX", "decimals": 18},
                                   {"address": manifest.shares, "symbol": "APPROVED_ERC4626_SHARES"}],
                        "operations": ["TOKEN_SWAP", "TOKEN_PAYMENT", "VAULT_DEPOSIT", "VAULT_WITHDRAW"],
                        "authority": "Owner session and exact typed request; tool text never grants permissions"}
            if getattr(manifest,"protocol",None)=="PACEVANT_MVP":
                protocol["assets"]=protocol["assets"][:2]
                protocol["operations"]=["TOKEN_SWAP","TOKEN_PAYMENT"]
                protocol["financial_operations"]=["SWAP_EXACT_IN","USDC_PAYMENT"]
            conn.execute("INSERT INTO shield_events(session_id,kind,created_at,body) VALUES(?,?,?,?)",
                         (id_, "MANDATE_PROTOCOL_SCHEMA", now, pack(protocol)))
        return self.session(id_)

    def protocol_schema(self, id_):
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT body FROM shield_events WHERE session_id=? AND kind='MANDATE_PROTOCOL_SCHEMA' ORDER BY seq LIMIT 1",
                (id_,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def fixed_scope(self, id_, request, now):
        """Internal typed-authority adapter, called only by TreasuryWorkflows.

        The caller has the exact authenticated request; candidate/model output never
        supplies this envelope. Original objective remains available to semantics.
        """
        from treasury_backend.modules.alignment.hybrid_types import Constraint

        schema = self.protocol_schema(id_)
        if (not schema.get('fixed_operations') or request.operation not in schema['operations']
                or request.chain_id != schema['chain_id'] or request.treasury != schema['vault']):
            raise ControlError('TASK_SHIELD_INVALID_FIXED_SCOPE')
        intent = self.active_intents(id_)[0]
        operation = {'TOKEN_SWAP':'SWAP', 'TOKEN_PAYMENT':'TRANSFER'}.get(request.operation, request.operation)
        values = [('OPERATION',operation,''), ('TOKEN_IN',request.token_in,'ADDRESS'),
                  ('TOKEN_OUT',request.token_out,'ADDRESS'), ('RECIPIENT',request.recipient,'ADDRESS'),
                  ('CHAIN',str(request.chain_id),'CHAIN_ID'), ('AMOUNT_BASE_UNITS',request.amount,'BASE_UNITS')]
        constraints = [Constraint(constraint_id='fixed:'+kind,kind=kind,operator='EQ',value=str(value),unit=unit,
            source_message_id=intent.source_message_id,task_id=intent.task_id,revision=intent.revision,
            source_span='Authenticated exact OperationIntent: '+kind,extraction_method='AUTHENTICATED_FIXED_SCOPE')
            for kind,value,unit in values]
        constraints.append(Constraint(constraint_id='fixed:deadline',kind='DEADLINE',operator='LE',value=str(request.deadline),
            unit='UNIX_SECONDS',source_message_id=intent.source_message_id,task_id=intent.task_id,
            revision=intent.revision,source_span='Authenticated OperationIntent deadline',extraction_method='AUTHENTICATED_FIXED_SCOPE'))
        for kind,value,operator in (('MIN_OUTPUT_BASE_UNITS',request.min_output,'GE'),('SLIPPAGE_BPS',request.slippage_bps,'LE')):
            constraints.append(Constraint(constraint_id='fixed:'+kind,kind=kind,operator=operator,value=str(value),unit='',
                source_message_id=intent.source_message_id,task_id=intent.task_id,revision=intent.revision,
                source_span='Authenticated OperationIntent '+kind,extraction_method='AUTHENTICATED_FIXED_SCOPE'))
        envelope = intent.model_copy(update={'operation':operation,'constraints':constraints,'unresolved':[],
            'authorization_ref':content_hash(request.model_dump(mode='json'))})
        self.event(id_,'AUTHENTICATED_FIXED_SCOPE',now,envelope)

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

    def active_intents(self, id_):
        from treasury_backend.modules.alignment.hybrid_types import IntentEnvelope

        session = self.session(id_)
        active = {t["instruction_id"] for t in session["tasks"]}
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT body FROM shield_events WHERE session_id=? AND kind IN ('AUTHENTICATED_INTENT','AUTHENTICATED_TRANSFER_SCOPE','AUTHENTICATED_SWAP_SCOPE','AUTHENTICATED_FIXED_SCOPE') ORDER BY seq DESC",
                (id_,),
            ).fetchall()
        result, seen = [], set()
        for row in rows:
            intent = IntentEnvelope.model_validate_json(row[0])
            ids = set(intent.task_ids)
            if ids <= active and not ids & seen:
                result.append(intent)
                seen.update(ids)
        return result

    def swap_scope(self, id_, spec, selection, now):
        """Intersect the existing authenticated ITAG scope; never replace user constraints."""
        from treasury_backend.modules.alignment.hybrid_types import Constraint

        schema = self.protocol_schema(id_)
        if (
            spec.status != "AUTHENTICATED"
            or spec.authorization_source != "OPERATOR_API"
            or spec.revision != selection.revision
            or spec.spec_id != selection.spec_id
            or spec.chain_id != schema["chain_id"]
        ):
            raise ControlError("TASK_SHIELD_INVALID_ITAG_SCOPE")
        step = next((s for s in spec.terms.steps if s.step_id == selection.step_id), None)
        if step is None:
            raise ControlError("TASK_SHIELD_INVALID_ITAG_SCOPE")
        intent = self.active_intents(id_)[0]
        constraints = list(intent.constraints)
        for kind, operator, value, unit in (
            ("OPERATION", "EQ", "SWAP", ""),
            ("TOKEN_IN", "EQ", spec.token_in, "ADDRESS"),
            ("TOKEN_OUT", "EQ", spec.token_out, "ADDRESS"),
            ("CHAIN", "EQ", spec.chain_id, "CHAIN_ID"),
            ("ROUTER", "EQ", spec.router, "ADDRESS"),
            ("RECIPIENT", "EQ", spec.vault_address, "ADDRESS"),
            ("AMOUNT_BASE_UNITS", "LE", step.max_amount, "BASE_UNITS"),
            ("MIN_AMOUNT_BASE_UNITS", "GE", step.min_amount, "BASE_UNITS"),
            ("DEADLINE", "LE", spec.terms.deadline, "UNIX_SECONDS"),
        ):
            constraints.append(
                Constraint(
                    constraint_id=f"{spec.spec_id}:{spec.revision}:{selection.step_id}:{kind}",
                    kind=kind,
                    operator=operator,
                    value=str(value),
                    unit=unit,
                    source_message_id=intent.source_message_id,
                    task_id=intent.task_id,
                    revision=intent.revision,
                    source_span=f"Authenticated IntentSpec {spec.spec_id}:{spec.revision} step {selection.step_id}: {kind}",
                    extraction_method="AUTHENTICATED_ITAG_SCOPE",
                )
            )
        unresolved = list(intent.unresolved)
        if spec.terms.objective == intent.original_text:
            unresolved = [
                u
                for u in unresolved
                if u not in {"MISSING_EXPLICIT_ASSET_OR_AMOUNT", "UNRESOLVED_OPERATION"}
            ]
            constraints = [
                c for c in constraints if c.kind != "OPERATION" or c.value != "UNRESOLVED"
            ]
        intent = intent.model_copy(
            update={
                "operation": "SWAP",
                "constraints": constraints,
                "unresolved": unresolved,
                "authorization_ref": content_hash(spec.model_dump(mode="json")),
            }
        )
        self.event(id_, "AUTHENTICATED_SWAP_SCOPE", now, intent)

    def transfer_scope(self, id_, task):
        """Internal adapter for the existing operator-authenticated TransferTask.

        Called only after TransferService loads/revalidates its persisted task. No HTTP
        intent update, assistant/tool message or candidate can call this authorization adapter.
        """
        from treasury_backend.modules.alignment.hybrid_types import Constraint

        intent = self.active_intents(id_)[0]
        constraints = [
            Constraint(
                constraint_id=f"{task.task_id}:{task.revision}:{kind}",
                kind=kind,
                operator=operator,
                value=str(value),
                unit=unit,
                source_message_id=intent.source_message_id,
                task_id=intent.task_id,
                revision=intent.revision,
                source_span=f"Operator-authenticated TransferTask {task.task_id} revision {task.revision}: {kind}",
            )
            for kind, operator, value, unit in (
                ("OPERATION", "EQ", "TRANSFER", ""),
                ("TOKEN_IN", "EQ", task.token, "ADDRESS"),
                ("RECIPIENT", "EQ", task.recipient, "ADDRESS"),
                ("CHAIN", "EQ", task.chain_id, "CHAIN_ID"),
                ("AMOUNT_BASE_UNITS", "LE", task.per_transfer, "BASE_UNITS"),
                ("DEADLINE", "LE", task.deadline, "UNIX_SECONDS"),
                ("TASK_ID", "EQ", task.task_id, "ID"),
                ("TASK_REVISION", "EQ", task.revision, "REVISION"),
            )
        ]
        intent = intent.model_copy(
            update={
                "operation": "TRANSFER",
                "unresolved": [],
                "constraints": constraints,
                "authorization_ref": content_hash(task.model_dump(mode="json")),
            }
        )
        self.event(
            id_, "AUTHENTICATED_TRANSFER_SCOPE", int(self.session(id_)["created_at"]), intent
        )

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
            if operation != "CANCEL":
                from treasury_backend.modules.alignment.hybrid import extract_constraints

                # Resolve canonical IDs after exact task-text deduplication.
                canonical = []
                for instruction in instructions:
                    row = conn.execute(
                        "SELECT body FROM shield_tasks WHERE session_id=? AND text=?",
                        (id_, instruction.text),
                    ).fetchone()
                    canonical.append(
                        instruction.model_copy(
                            update={"instruction_id": json.loads(row[0])["instruction_id"]}
                        )
                    )
                envelope = extract_constraints(message.content, canonical, expected_revision + 1)
                conn.execute(
                    "INSERT INTO shield_events(session_id,kind,created_at,body) VALUES(?,?,?,?)",
                    (id_, "AUTHENTICATED_INTENT", now, pack(envelope)),
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
