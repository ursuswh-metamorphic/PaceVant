"""Restricted single-account adapter; delegates to the unchanged security pipeline."""

from typing import Annotated, Literal

from fastapi import Depends, Header, Request
from pydantic import StringConstraints

from treasury_backend.core.domain import Id
from treasury_backend.core.errors import ControlError
from treasury_backend.core.models import Goal, IntentSelection, WorkflowRequest
from treasury_backend.modules.gas_credit import CreditError
from treasury_backend.modules.planning import requested_amount, reverse_goal
from treasury_backend.modules.temporal.models import IntentTerms, Step
from treasury_contracts.models import Wire

from .demo_auth import issue_demo_session, valid_demo_session

RequestKey = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{8,100}$")]


class DemoGoal(Wire):
    goal: Goal


class DemoSelection(Wire):
    account_id: Literal["demo"]


def install_demo_routes(app, config):
    def auth(request: Request):
        if not config.enabled:
            raise ControlError("DEMO_DISABLED", 404)
        supplied = request.headers.get("Authorization", "")
        if not supplied.startswith("Bearer ") or not valid_demo_session(supplied[7:], config.access_token):
            raise ControlError("DEMO_ACCESS_REQUIRED", 401)

    @app.post("/v1/demo/select")
    def select_account(payload: DemoSelection):
        if not config.enabled:
            raise ControlError("DEMO_DISABLED", 404)
        token, expires_at = issue_demo_session(config.access_token)
        return {"account_id": payload.account_id, "access_token": token, "expires_at": expires_at,
                "scope": "demo", "token_type": "Bearer"}

    @app.get("/v1/demo/config")
    def public_config():
        return {
            "enabled": config.enabled,
            "accounts": [
                {"id": "demo", "label": "PaceVant - Demo User", "wallet_address": config.address}
            ]
            if config.enabled
            else [],
        }

    def ledger(request):
        return request.app.state.gas_credit

    def current(request, workflow):
        gas = ledger(request)
        if not gas.owns(workflow):
            raise ControlError("WORKFLOW_NOT_FOUND", 404)
        control = request.app.state.control
        try:
            result = control.workflow(workflow)
        except ControlError as exc:
            if exc.code != "WORKFLOW_NOT_FOUND":
                raise
            return {
                "workflow_id": workflow,
                "status": "STARTING_OR_REVIEW_REQUIRED",
                "timeline": [],
            }
        if result["status"] in {
            "CONFIRMED",
            "REVERTED",
            "REJECTED",
            "ESCALATED",
            "FAILED_TO_SUBMIT",
            "EXPIRED",
            "REPLAN_REQUIRED",
        }:
            gas.finish_request(workflow, result["status"])
        return result

    @app.get("/v1/demo/account", dependencies=[Depends(auth)])
    def account(request: Request):
        # Worker can complete a submission after the original HTTP call ends.
        # Refresh durable request state without starting/retrying a workflow.
        gas = ledger(request)
        with gas.db() as db:
            active = db.execute(
                "SELECT workflow_id FROM demo_requests WHERE state='RUNNING'"
            ).fetchall()
        for row in active:
            try:
                state = request.app.state.control.store.workflow(row[0])["status"]
            except ControlError:
                continue
            if state in {
                "CONFIRMED",
                "REVERTED",
                "REJECTED",
                "ESCALATED",
                "FAILED_TO_SUBMIT",
                "EXPIRED",
                "REPLAN_REQUIRED",
            }:
                gas.finish_request(row[0], state)
        result = ledger(request).account()
        result["wallet_avax_balance_wei"] = None
        result["wallet_balance_status"] = "UNAVAILABLE"
        try:
            chain = request.app.state.execution.chain
            from web3 import Web3

            result["wallet_avax_balance_wei"] = str(
                chain.w3.eth.get_balance(Web3.to_checksum_address(config.address))
            )
            result["wallet_balance_status"] = "ONCHAIN"
        except Exception:
            pass
        return result

    @app.get("/v1/demo/treasury", dependencies=[Depends(auth)])
    def treasury(request: Request):
        return request.app.state.control.treasury("demo_read")

    @app.get("/v1/demo/workflows/{workflow}", dependencies=[Depends(auth)])
    def workflow(workflow: Id, request: Request):
        return current(request, workflow)

    @app.get("/v1/demo/requests/{key}", dependencies=[Depends(auth)])
    def resume(key: RequestKey, request: Request):
        gas = ledger(request)
        with gas.db() as db:
            row = db.execute(
                "SELECT workflow_id FROM demo_requests WHERE request_key=?", (key,)
            ).fetchone()
        if not row:
            raise ControlError("DEMO_REQUEST_NOT_FOUND", 404)
        return current(request, row[0])

    @app.post("/v1/demo/workflows", dependencies=[Depends(auth)])
    def start(
        payload: DemoGoal, request: Request, idempotency_key: Annotated[RequestKey, Header()]
    ):
        gas = ledger(request)
        amount = requested_amount(payload.goal)
        if not amount or reverse_goal(payload.goal):
            raise ControlError("DEMO_EXACT_USDC_SWAP_REQUIRED", 422)
        control = request.app.state.control
        mandate = control.mandate()
        if amount > int(mandate.max_usdc_per_swap_base_units):
            raise ControlError("TRADE_SIZE_LIMIT", 422)
        # Fast refusal avoids expensive model/fork calls when no credit remains.
        # Exact fee reservation remains mandatory inside the relayer send journal.
        row, fresh = gas.begin_request(idempotency_key, payload.goal)
        if not fresh:
            return current(request, row["workflow_id"])
        workflow_id = row["workflow_id"]
        try:
            spec = control.temporal.authorize(
                IntentTerms(
                    kind="ONE_SHOT_SWAP",
                    mandate_id=mandate.mandate_id,
                    objective=payload.goal,
                    deadline=min(control.clock() + 1800, mandate.expires_at),
                    total_budget=str(amount),
                    steps=[Step(step_id="swap", min_amount=str(amount), max_amount=str(amount))],
                ),
                mandate,
            )
            control.run(
                WorkflowRequest(
                    goal=payload.goal,
                    mandate_id=mandate.mandate_id,
                    temporal_intent=IntentSelection(
                        spec_id=spec.spec_id, revision=spec.revision, step_id="swap"
                    ),
                ),
                workflow_id=workflow_id,
            )
            return current(request, workflow_id)
        except Exception:
            # Never automatically replay a failed/unknown mutation. Inspect the
            # SAME durable request/workflow via GET; RUNNING remains conservative.
            raise ControlError("DEMO_REQUEST_REVIEW_REQUIRED", 409) from None

    @app.exception_handler(CreditError)
    async def credit_error(request, exc):
        from treasury_backend.api.control import error_response

        return error_response(request, exc.code, 409)
