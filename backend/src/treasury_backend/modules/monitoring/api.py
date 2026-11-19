"""Authenticated read-only history shared by the control plane and key-free observer."""

from typing import Annotated

from fastapi import Query, Request

from treasury_backend.core.domain import Address, Id
from treasury_backend.core.errors import ControlError


def install_history_routes(app, dependencies, *, mode, store, refresh):
    def scope(chain_id):
        expected = {31337, 43113} if mode == "MOCK" else {43113 if mode == "FUJI" else 31337}
        if chain_id not in expected:
            raise ControlError("CHAIN_MISMATCH", 400)

    @app.get("/v1/portfolio/current", dependencies=dependencies)
    def current(request: Request, chain_id: int, vault_address: Address):
        scope(chain_id)
        db = store(request)
        value = db.current_snapshot(mode, chain_id, vault_address)
        return {
            "portfolio": value,
            "history_version": db.history_version(chain_id, vault_address, mode),
            "cached_observation_only": True,
            "authorization_eligible": False,
        }

    @app.post("/v1/portfolio/observe", dependencies=dependencies)
    def observe(request: Request, chain_id: int, vault_address: Address):
        scope(chain_id)
        return refresh(request, vault_address)

    @app.get("/v1/portfolio/history", dependencies=dependencies)
    def history(
        request: Request,
        chain_id: int,
        vault_address: Address,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        before: Annotated[int | None, Query(ge=0)] = None,
    ):
        scope(chain_id)
        return {
            "snapshots": store(request).scoped_snapshots(
                mode, chain_id, vault_address, limit=limit, before=before
            )
        }

    @app.get("/v1/portfolio/snapshots/{snapshot_id}", dependencies=dependencies)
    def snapshot(request: Request, snapshot_id: Id):
        value = store(request).snapshot_record(snapshot_id)
        if value["snapshot"]["mode"] != mode:
            raise ControlError("SNAPSHOT_NOT_FOUND", 404)
        return value

    @app.get("/v1/history/transactions", dependencies=dependencies)
    def transactions(
        request: Request,
        chain_id: int,
        vault_address: Address,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        scope(chain_id)
        return {
            "transactions": store(request).outcome_history(mode, chain_id, vault_address, limit)
        }

    @app.get("/v1/reconciliations/{decision_id}", dependencies=dependencies)
    def reconciliation(
        request: Request, decision_id: Id, limit: Annotated[int, Query(ge=1, le=100)] = 50
    ):
        db = store(request)
        job = db.monitor_job(decision_id)
        if not job or job["mode"] != mode:
            raise ControlError("RECONCILIATION_NOT_FOUND", 404)
        return {
            "monitoring": {k: job[k] for k in ("state", "attempts", "next_at", "tx_hash")},
            "outcome": db.outcome_projection(decision_id),
            "observations": db.outcome_audit(decision_id, limit=limit),
        }
