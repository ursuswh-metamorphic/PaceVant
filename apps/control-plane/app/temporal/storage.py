import json
from collections.abc import Mapping

from app.errors import ControlError
from app.portfolio.observations import content_hash
from app.temporal.models import IntentSpec

SCHEMA = """
CREATE TABLE IF NOT EXISTS itag_intents (
 spec_id TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
 PRIMARY KEY(spec_id, revision));
CREATE TABLE IF NOT EXISTS itag_workflows (
 workflow_id TEXT PRIMARY KEY REFERENCES workflows(id),
 spec_id TEXT NOT NULL, revision INTEGER NOT NULL, step_id TEXT NOT NULL,
 FOREIGN KEY(spec_id, revision) REFERENCES itag_intents(spec_id, revision));
CREATE INDEX IF NOT EXISTS itag_scope ON itag_workflows(spec_id);
CREATE TABLE IF NOT EXISTS itag_assessments (
 assessment_hash TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES itag_workflows(workflow_id),
 candidate_id TEXT NOT NULL UNIQUE, body TEXT NOT NULL, graph TEXT NOT NULL);
"""
for table in ("itag_intents", "itag_workflows", "itag_assessments"):
    for op in ("UPDATE", "DELETE"):
        SCHEMA += f"""
        CREATE TRIGGER IF NOT EXISTS {table}_{op.lower()} BEFORE {op} ON {table}
        BEGIN SELECT RAISE(ABORT, 'immutable ITAG evidence'); END;
        """


def current(conn, spec_id):
    row = conn.execute(
        "SELECT body FROM itag_intents WHERE spec_id=? ORDER BY revision DESC LIMIT 1", (spec_id,)
    ).fetchone()
    if row is None:
        raise ControlError("ITAG_INTENT_NOT_FOUND", 404)
    return IntentSpec.model_validate_json(row[0])


def binding(conn, workflow_id):
    return conn.execute(
        "SELECT * FROM itag_workflows WHERE workflow_id=?", (workflow_id,)
    ).fetchone()


def add_revision(conn, spec, expected):
    if expected:
        prior = current(conn, spec.spec_id)
        if prior.revision != expected or prior.status == "CANCELLED":
            raise ControlError("ITAG_STALE_OR_CANCELLED_INTENT")
        if prior.mode != spec.mode:
            raise ControlError("ITAG_REVISION_SCOPE_CHANGED")
        if prior.status == "AUTHENTICATED" and (
            prior.terms.kind != spec.terms.kind
            or [s.step_id for s in prior.terms.steps] != [s.step_id for s in spec.terms.steps]
            or prior.mandate_hash != spec.mandate_hash
        ):
            raise ControlError("ITAG_REVISION_SCOPE_CHANGED")
    conn.execute(
        "INSERT INTO itag_intents VALUES (?,?,?)",
        (spec.spec_id, spec.revision, spec.model_dump_json()),
    )


def stable_outcome(outcome):
    if not outcome:
        return None
    proof = outcome["verification"]
    return {
        **{
            key: outcome.get(key)
            for key in (
                "state",
                "decision_id",
                "build_id",
                "policy_hash",
                "pre_snapshot_id",
                "post_snapshot_id",
                "attribution_status",
                "reason_codes",
            )
        },
        "verification": {
            key: proof.get(key)
            for key in (
                "chain_id",
                "vault_address",
                "build_id",
                "decision_id",
                "tx_hash",
                "canonical",
                "block_hash",
                "block_number",
                "receipt_status",
                "verification_status",
                "token_in_delta_base_units",
                "token_out_delta_base_units",
            )
        },
    }


def history(conn, spec, exclude=None):
    version_row = conn.execute(
        "SELECT version FROM treasury_versions WHERE mode=? AND chain_id=? AND vault=?",
        (spec.mode, spec.chain_id, spec.vault_address.lower()),
    ).fetchone()
    rows = conn.execute(
        """
        SELECT a.decision_id,a.state,a.issued_at,a.expires_at,w.workflow_id,w.step_id,
               w.revision,d.body AS decision,o.body AS outcome,j.tx_hash
        FROM itag_workflows w JOIN decisions d ON d.workflow_id=w.workflow_id
        JOIN attestations a ON a.decision_id=d.id
        LEFT JOIN outcome_projections o ON o.decision_id=a.decision_id
        LEFT JOIN monitor_jobs j ON j.decision_id=a.decision_id
        WHERE w.spec_id=? AND a.decision_id IS NOT ? ORDER BY a.rowid LIMIT 257
        """,
        (spec.spec_id, exclude),
    ).fetchall()
    if len(rows) > 256:
        raise ControlError("ITAG_HISTORY_LIMIT", 409)
    entries = []
    for row in rows:
        record = dict(row)
        decision = json.loads(record.pop("decision"))
        record["build"] = decision.get("build")
        record["proposal"] = decision.get("proposal")
        record["assessment_hash"] = decision.get("itag_assessment_hash")
        record["outcome"] = (
            stable_outcome(json.loads(record["outcome"])) if record["outcome"] else None
        )
        record["invalidated"] = False
        if record["outcome"]:
            ids = (record["outcome"]["pre_snapshot_id"], record["outcome"]["post_snapshot_id"])
            record["invalidated"] = bool(
                conn.execute(
                    """SELECT 1 FROM portfolio_status_events
                WHERE snapshot_id IN (?,?) AND state='INVALIDATED' LIMIT 1""",
                    ids,
                ).fetchone()
            )
            record["snapshots"] = {
                snapshot_id: snapshot_hash[0]
                for snapshot_id in ids
                if snapshot_id
                and (
                    snapshot_hash := conn.execute(
                        "SELECT content_hash FROM portfolio_snapshots WHERE snapshot_id=? AND mode=? AND chain_id=? AND vault=?",
                        (snapshot_id, spec.mode, spec.chain_id, spec.vault_address.lower()),
                    ).fetchone()
                )
                is not None
            }
        entries.append(record)
    return (version_row[0] if version_row else 0), entries


def save(conn, workflow_id, assessment, graph):
    body = assessment.model_dump(mode="json")
    digest = content_hash(body)
    conn.execute(
        "INSERT INTO itag_assessments VALUES (?,?,?,?,?)",
        (
            digest,
            workflow_id,
            assessment.candidate_action_id,
            json.dumps(body),
            graph.model_dump_json(),
        ),
    )
    return digest


def load(conn, digest):
    row = conn.execute(
        "SELECT * FROM itag_assessments WHERE assessment_hash=?", (digest,)
    ).fetchone()
    if not row:
        raise ControlError("ITAG_ASSESSMENT_NOT_FOUND", 404)
    return row, json.loads(row["body"]), json.loads(row["graph"])


def check_approval(conn, workflow_id, decision_id, now, *, submitting=False):
    link = binding(conn, workflow_id)
    if link is None:
        return
    row = conn.execute(
        "SELECT body FROM decisions WHERE id=? AND workflow_id=?", (decision_id, workflow_id)
    ).fetchone()
    decision = json.loads(row[0]) if row else {}
    digest = decision.get("itag_assessment_hash")
    if not digest:
        raise ControlError("ITAG_APPROVAL_PROOF_REQUIRED")
    stored, proof, graph = load(conn, digest)
    spec = current(conn, link["spec_id"])
    version, entries = history(conn, spec, decision_id if submitting else None)
    candidate = decision.get("proposal")
    built = decision.get("build")
    simulation = decision.get("simulation")
    graph_nodes = {node["node_id"] for node in graph["nodes"]}
    if (
        stored["workflow_id"] != workflow_id
        or proof["verdict"] != "PASS"
        or digest != content_hash(proof)
        or proof["graph_hash"] != content_hash(graph)
        or proof["intent_hash"] != content_hash(spec.model_dump())
        or spec.status != "AUTHENTICATED"
        or spec.revision != link["revision"]
        or now >= spec.terms.deadline
        or proof["history_version"] != version
        or proof["history_hash"] != content_hash(entries)
        or not isinstance(candidate, Mapping)
        or not isinstance(built, Mapping)
        or proof["candidate_hash"] != content_hash(candidate)
        or proof["candidate_action_id"] != candidate["intent_id"]
        or proof["build_hash"] != content_hash(built)
        or proof["build_id"] != built["build_id"]
        or not isinstance(simulation, Mapping)
        or "simulation:" + simulation["evidence_root"] not in graph_nodes
        or decision.get("pre_snapshot_id") not in graph_nodes
    ):
        raise ControlError("ITAG_STALE_OR_MISMATCHED_EVIDENCE")
    shield = decision.get("task_shield_proof")
    if not shield:
        raise ControlError("ITAG_SHIELD_PROOF_REQUIRED")
    session = conn.execute(
        "SELECT workflow_id,revision FROM shield_sessions WHERE id=?", (shield["session_id"],)
    ).fetchone()
    if (
        not session
        or session["workflow_id"] != workflow_id
        or session["revision"] != proof["task_revision"]
        or session["revision"] != shield["revision"]
    ):
        raise ControlError("ITAG_STALE_TASK_REVISION")
