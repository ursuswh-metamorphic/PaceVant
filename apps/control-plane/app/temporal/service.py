import json
from collections import Counter
from time import monotonic
from uuid import uuid4

from app.errors import ControlError
from app.portfolio.observations import content_hash
from app.temporal import storage
from app.temporal.fusion import fuse
from app.temporal.graph_builder import build_graph
from app.temporal.intent_spec import make_spec
from app.temporal.models import HybridTemporalAssessment, IntentSpec
from app.temporal.semantic_evaluator import TemporalSemanticEvaluator
from app.temporal.verifier import verify


class TemporalService:
    def __init__(self, store, shield, mode, clock):
        self.store, self.shield, self.mode, self.clock = store, shield, mode, clock
        self.semantic = TemporalSemanticEvaluator(shield)

    def authorize(self, terms, mandate, *, spec_id=None, expected=0, proposed=False):
        if mandate.status != "ACTIVE":
            raise ControlError("ITAG_MANDATE_NOT_ACTIVE", 403)
        spec = make_spec(
            terms,
            mandate,
            self.mode,
            spec_id or "itag_" + uuid4().hex,
            expected + 1,
            self.clock(),
            "PROPOSED" if proposed else "AUTHENTICATED",
        )
        with self.store.connection(write=True) as conn:
            storage.add_revision(conn, spec, expected)
        return spec

    def cancel(self, spec_id, expected):
        with self.store.connection(write=True) as conn:
            prior = storage.current(conn, spec_id)
            if prior.mode != self.mode:
                raise ControlError("ITAG_INTENT_NOT_FOUND", 404)
            value = prior.model_copy(
                update={
                    "revision": expected + 1,
                    "status": "CANCELLED",
                    "recorded_at": self.clock(),
                }
            )
            storage.add_revision(conn, value, expected)
            return value

    def evaluate(self, workflow_id, mandate, proposal, built, sim, observation, aligned, runtime):
        started = monotonic()
        with self.store.connection() as conn:
            conn.execute("BEGIN")
            link = storage.binding(conn, workflow_id)
            if not link:
                return None, None
            spec = storage.current(conn, link["spec_id"])
            version, entries = storage.history(conn, spec)
            revisions = [
                IntentSpec.model_validate_json(r[0])
                for r in conn.execute(
                    "SELECT body FROM itag_intents WHERE spec_id=? AND revision<? ORDER BY revision",
                    (spec.spec_id, spec.revision),
                )
            ]
            reports, tasks, revision = [], [], 0
            messages, outputs = [], {}
            if runtime:
                session = conn.execute(
                    "SELECT revision FROM shield_sessions WHERE id=?", (runtime.session_id,)
                ).fetchone()
                revision = session[0]
                tasks = [
                    json.loads(r[0])
                    for r in conn.execute(
                        "SELECT body FROM shield_tasks WHERE session_id=? AND active=1 ORDER BY rowid",
                        (runtime.session_id,),
                    )
                ]
                reports = [
                    json.loads(r[0])
                    for r in conn.execute(
                        "SELECT body FROM shield_checks WHERE session_id=? ORDER BY rowid",
                        (runtime.session_id,),
                    )
                ]
                output_calls = Counter(
                    r.get("tool_call_id") for r in reports if r["source"] == "TOOL"
                )
                for row in conn.execute(
                    "SELECT body FROM shield_context WHERE session_id=? ORDER BY seq",
                    (runtime.session_id,),
                ):
                    record = json.loads(row[0])
                    if record.get("trust") == "AUTHENTICATED_USER":
                        messages.append(record["message"])
                    elif record.get("trust") == "UNTRUSTED_TOOL":
                        if record.get("check_id"):
                            outputs[record["check_id"]] = record["output"]
                        elif output_calls[record["tool_call_id"]] == 1:
                            outputs[record["tool_call_id"]] = record["output"]
        verifying = monotonic()
        verified = verify(spec, link, mandate, proposal, built, self.mode, self.clock(), entries)
        verified_ms = int((monotonic() - verifying) * 1000)
        step = next((s for s in spec.terms.steps if s.step_id == link["step_id"]), None)
        authorized = step.prerequisites if step and verified.verdict == "PASS" else None
        building = monotonic()
        check_ids = set(runtime.attempt_checks) if runtime else set()
        graph = build_graph(
            spec,
            mandate,
            proposal,
            built,
            sim,
            observation,
            entries,
            tasks,
            reports,
            revisions,
            authorized=authorized,
            step_id=link["step_id"],
            current_report_ids=check_ids,
            user_messages=messages,
            output_context=outputs,
        )
        if runtime:
            runtime.attempt_checks.clear()
        graph_ms = int((monotonic() - building) * 1000)
        failed_checks = {
            r["check_id"]
            for r in reports
            if r["check_id"] in check_ids and r["status"] != "ALIGNED"
        }
        feedback = bool(runtime and runtime.last_feedback)
        shield_blocked = feedback or (aligned.verdict != "ALIGNED" and bool(failed_checks))
        semantic = self.semantic.before_decision(
            graph,
            proposal.intent_id,
            aligned.verdict,
            shield_blocked=shield_blocked,
            expired=self.clock() >= proposal.deadline,
        )
        shield_verdict = aligned.verdict
        if feedback and shield_verdict == "ALIGNED":
            shield_verdict = "UNCERTAIN"
        verdict, reasons = fuse(semantic, verified, shield_verdict=shield_verdict)
        if self.clock() >= proposal.deadline:
            if "ITAG_CANDIDATE_EXPIRED" not in reasons:
                reasons.append("ITAG_CANDIDATE_EXPIRED")
            if verdict in {"PASS", "REPLAN"}:
                verdict = "ESCALATE"
        node_ids = [proposal.intent_id] if verdict != "PASS" else []
        evidence = {f"{spec.spec_id}:{spec.revision}", proposal.intent_id}
        evidence.update(n for v in verified.violations for n in v.node_ids)
        if shield_blocked:
            evidence.update(failed_checks)
        suggested = None
        if verdict == "REPLAN" and step:
            completed = {e["step_id"] for e in entries if e["state"] == "CONFIRMED"}
            protected = sum(
                int(s.min_amount)
                for s in spec.terms.steps
                if s.step_id != step.step_id and s.step_id not in completed
            )
            suggested = str(min(int(step.max_amount), int(verified.remaining) - protected))
        result = HybridTemporalAssessment(
            semantic=semantic,
            deterministic=verified,
            graph_hash=content_hash(graph.model_dump()),
            intent_hash=content_hash(spec.model_dump()),
            history_hash=content_hash(entries),
            task_revision=revision,
            history_version=version,
            candidate_action_id=proposal.intent_id,
            candidate_hash=content_hash(proposal.model_dump()),
            build_hash=content_hash(built.model_dump()) if built else None,
            build_id=built.build_id if built else None,
            evidence_refs=sorted(evidence),
            verdict=verdict,
            reason_codes=reasons,
            violating_node_ids=sorted(node_ids),
            violating_edge_ids=[
                e.edge_id
                for e in graph.edges
                if shield_blocked and e.source == proposal.intent_id and e.target in failed_checks
            ],
            suggested_amount=suggested,
            timing_ms={
                "graph": graph_ms,
                "deterministic": verified_ms,
                "semantic": semantic.latency_ms,
                "task_shield_reported": sum(r["latency_ms"] for r in reports),
                "itag_total": int((monotonic() - started) * 1000),
            },
        )
        with self.store.connection(write=True) as conn:
            digest = storage.save(conn, workflow_id, result, graph)
        return result, digest
