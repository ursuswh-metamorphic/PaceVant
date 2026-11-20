import json
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import Field

from treasury_backend.config.control import DASHBOARD
from treasury_backend.core.domain import Id
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.temporal import storage
from treasury_backend.modules.temporal.explainer import explain
from treasury_backend.modules.temporal.models import Graph, HybridTemporalAssessment, IntentTerms
from treasury_contracts.models import Hash, Wire


class Revision(Wire):
    expected_revision: int = Field(ge=1)


class Replacement(Revision):
    terms: IntentTerms


def install_itag_routes(app, operator, *, serve_frontend=True):
    auth = [Depends(operator)]

    def service(request):
        return request.app.state.control

    @app.post("/v1/itag/intents", dependencies=auth)
    def create(terms: IntentTerms, request: Request, proposed: bool = False):
        control = service(request)
        return control.temporal.authorize(
            terms, control.mandate(terms.mandate_id), proposed=proposed
        )

    @app.put("/v1/itag/intents/{spec_id}", dependencies=auth)
    def revise(spec_id: Id, change: Replacement, request: Request):
        control = service(request)
        return control.temporal.authorize(
            change.terms,
            control.mandate(change.terms.mandate_id),
            spec_id=spec_id,
            expected=change.expected_revision,
        )

    @app.post("/v1/itag/intents/{spec_id}/cancel", dependencies=auth)
    def cancel(spec_id: Id, change: Revision, request: Request):
        return service(request).temporal.cancel(spec_id, change.expected_revision)

    @app.get("/v1/itag/intents/{spec_id}", dependencies=auth)
    def intent(spec_id: Id, request: Request):
        control = service(request)
        with control.store.connection() as conn:
            current = storage.current(conn, spec_id)
            if current.mode != control.settings.mode:
                raise ControlError("ITAG_INTENT_NOT_FOUND", 404)
            history = [
                json.loads(r[0]) | {"effective_status": "SUPERSEDED"}
                for r in conn.execute(
                    "SELECT body FROM itag_intents WHERE spec_id=? AND revision<? ORDER BY revision",
                    (spec_id, current.revision),
                )
            ]
        return {"intent": current, "superseded": history}

    @app.get("/v1/itag/intents/{spec_id}/history", dependencies=auth)
    def history(spec_id: Id, request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 30):
        control = service(request)
        with control.store.connection() as conn:
            spec = storage.current(conn, spec_id)
            if spec.mode != control.settings.mode:
                raise ControlError("ITAG_INTENT_NOT_FOUND", 404)
            version, ledger = storage.history(conn, spec)
            rows = conn.execute(
                """SELECT a.assessment_hash,a.candidate_id,a.workflow_id,json_extract(a.body,'$.verdict') AS verdict
                FROM itag_assessments a JOIN itag_workflows w USING(workflow_id)
                WHERE w.spec_id=? ORDER BY a.rowid DESC LIMIT ?""",
                (spec_id, limit),
            ).fetchall()
        return {
            "history_version": version,
            "ledger": ledger,
            "assessments": [dict(r) for r in rows],
        }

    @app.get("/v1/itag/assessments/{digest}", dependencies=auth)
    def assessment(digest: Hash, request: Request):
        control = service(request)
        with control.store.connection() as conn:
            row, body, graph_data = storage.load(conn, digest)
            spec = storage.current(conn, storage.binding(conn, row["workflow_id"])["spec_id"])
            if spec.mode != control.settings.mode:
                raise ControlError("ITAG_ASSESSMENT_NOT_FOUND", 404)
            record = conn.execute(
                "SELECT id,body FROM decisions WHERE intent_id=?", (row["candidate_id"],)
            ).fetchone()
            decision = json.loads(record["body"])["decision"] if record else None
            outcome = (
                conn.execute(
                    "SELECT body FROM outcome_projections WHERE decision_id=?", (record["id"],)
                ).fetchone()
                if record
                else None
            )
        graph = Graph.model_validate(graph_data)
        result = explain(HybridTemporalAssessment.model_validate(body), graph)
        return {
            "graph": graph,
            "explanation": result,
            "decision": decision,
            "latest_outcome": storage.stable_outcome(json.loads(outcome[0])) if outcome else None,
        }

    @app.get("/v1/itag/assessments/{digest}/nodes/{node_id}", dependencies=auth)
    def node(digest: Hash, node_id: str, request: Request):
        result = assessment(digest, request)
        graph = result["graph"]
        focus = next((n for n in graph.nodes if n.node_id == node_id), None)
        if not focus:
            raise ControlError("ITAG_NODE_NOT_FOUND", 404)
        # Traverse only immediate recorded provenance for this node.
        edges = [e for e in graph.edges if node_id in (e.source, e.target)]
        related = {e.target for e in edges if e.kind == "EVALUATED_BY"}
        semantic = result["explanation"].assessment.semantic
        return {
            "node": focus,
            "provenance": edges,
            "shield_reports": [
                n.data
                for n in graph.nodes
                if n.node_id in related and n.kind == "SEMANTIC_ASSESSMENT"
            ],
            "violations": [
                v for v in result["explanation"].temporal_violations if node_id in v.node_ids
            ],
            "trajectory_finding": semantic.finding
            if semantic.finding and node_id in semantic.finding.referenced_graph_node_ids
            else None,
            "recovery": result["explanation"].recovery,
        }

    if not serve_frontend:
        return

    @app.get("/itag", include_in_schema=False)
    def viewer():
        return FileResponse(
            DASHBOARD / "itag.html",
            headers={
                "Content-Security-Policy": "default-src 'self'; style-src 'self'; frame-ancestors 'none'",
            },
        )

    @app.get("/itag-viewer.js", include_in_schema=False)
    def viewer_script():
        return FileResponse(DASHBOARD / "itag-viewer.js", media_type="application/javascript")

    @app.get("/itag-viewer.css", include_in_schema=False)
    def viewer_style():
        return FileResponse(DASHBOARD / "itag-viewer.css", media_type="text/css")
