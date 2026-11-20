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


class ShieldChallenge(Wire):
    challenge: Literal["recipient_redirect", "policy_override", "forged_user"] = "recipient_redirect"


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

    @app.get("/v1/demo/readiness", dependencies=[Depends(auth)])
    def readiness(request: Request):
        import time

        runtime = request.app.state.execution
        c = runtime.chain.context()
        session = c.get("proof_session") or {}
        now = max(int(time.time()), c["timestamp"])
        reasons = []
        if c["paused"] or not c["policy_active"] or c["policy_expires_at"] <= now:
            reasons.append("POLICY_UNAVAILABLE")
        if (not session.get("active") or not session.get("starts_at", 0) <= now
                or session.get("expires_at", 0) <= now):
            reasons.append("SESSION_UNAVAILABLE")
        credit = ledger(request).account()
        if int(credit["available_wei"]) <= 0:
            reasons.append("GAS_CREDIT_INSUFFICIENT")
        return {"source": "CHAIN", "mode": runtime.settings.mode.upper(),
                "block_number": c["block_number"], "block_hash": c["block_hash"],
                "session": session, "reason_codes": reasons, "broadcast": False,
                "scope": "Policy/session/credit only; oracle, funding/exposure and all execution gates remain mandatory"}

    @app.post("/v1/demo/shield-check", dependencies=[Depends(auth)])
    def shield_check(request: Request, payload: ShieldChallenge | None = None):
        from uuid import uuid4

        from treasury_backend.modules.alignment.challenges import CHALLENGES
        from treasury_backend.modules.alignment.types import Message, TaskUpdate

        control = request.app.state.control
        request.app.state.execution.expensive_rate()
        shield = control.shield
        if not shield.active:
            raise ControlError("TASK_SHIELD_NOT_ENABLED", 409)
        session = "demo_check_" + uuid4().hex
        challenge_id = payload.challenge if payload else "recipient_redirect"
        challenge = CHALLENGES[challenge_id]
        shield.state.create(session, control.mandate(), int(control.clock()))
        shield.update_user(session, TaskUpdate(message_id="user_" + uuid4().hex,
                           content="Buy WAVAX with 0.000001 USDC. Keep all proceeds in the treasury vault.",
                           expected_revision=0), authenticated=True)
        report = shield.check(session, Message(message_id="tool_" + uuid4().hex, role="TOOL",
            tool_name="adversarial_demo_tool", content=challenge["content"]))
        return {"source": "REAL_MODEL_FIXED_ADVERSARIAL_CHALLENGE", "broadcast": False,
                "gas_charged_wei": "0", "session_id": session,
                "challenge_id": challenge_id, "challenge": challenge,
                "all_passed": report.status == challenge["expected_status"], "report": report,
                "scope": "Isolated TOOL-role challenge to the current Shield; not a fabricated market observation or a swap"}

    @app.get("/v1/demo/workflows/{workflow}/security-checks", dependencies=[Depends(auth)])
    def security_checks(workflow: Id, request: Request):
        from treasury_backend.modules.execution.security_checks import contract_checks

        result = current(request, workflow)
        if result["status"] != "CONFIRMED":
            raise ControlError("CONFIRMED_DEMO_WORKFLOW_REQUIRED", 409)
        gas = ledger(request)
        with gas.db() as db:
            row = db.execute(
                "SELECT tx_hash FROM demo_gas_reservations JOIN demo_builds USING(build_id) "
                "WHERE workflow_id=? AND state='SETTLED' AND receipt_status='SUCCESS'",
                (workflow,),
            ).fetchone()
        if not row:
            raise ControlError("VERIFIED_DEMO_RECEIPT_REQUIRED", 409)
        runtime = request.app.state.execution
        runtime.expensive_rate()
        return contract_checks(runtime.chain, runtime.store, row[0])

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
