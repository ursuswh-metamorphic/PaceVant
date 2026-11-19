from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Query, Request
from pydantic import Field

from treasury_backend.core.domain import Id
from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment.types import Message, TaskUpdate, Text
from treasury_contracts.models import Wire


class SessionRequest(Wire):
    mandate_id: Id
    content: Text


class InspectRequest(Wire):
    source: Literal["ASSISTANT", "TOOL"]
    content: Text
    tool_name: Id | None = None
    tool_call_id: Id | None = None


class ToolRequest(Wire):
    tool_name: Id
    arguments: dict = Field(default_factory=dict)
    related_content: str = Field(default="", max_length=4000)


def install_shield_routes(app, dependencies):
    def engine(request):
        shield = request.app.state.control.shield
        if not shield.active:
            raise ControlError("TASK_SHIELD_NOT_ENABLED", 409)
        return shield

    @app.post("/v1/task-shield/sessions", dependencies=dependencies)
    def create(payload: SessionRequest, request: Request):
        shield = engine(request)
        mandate = request.app.state.control.mandate(payload.mandate_id)
        id_ = "session_" + uuid4().hex
        shield.state.create(id_, mandate, int(shield.clock()))
        return shield.update_user(
            id_,
            TaskUpdate(
                message_id="user_" + uuid4().hex, content=payload.content, expected_revision=0
            ),
            authenticated=True,
        )

    @app.post("/v1/task-shield/sessions/{id_}/user-messages", dependencies=dependencies)
    def update(id_: Id, payload: TaskUpdate, request: Request):
        return engine(request).update_user(id_, payload, authenticated=True)

    @app.get("/v1/task-shield/sessions/{id_}", dependencies=dependencies)
    def session(id_: Id, request: Request):
        return engine(request).state.session(id_)

    @app.get("/v1/task-shield/sessions/{id_}/audit", dependencies=dependencies)
    def audit(id_: Id, request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50):
        return engine(request).state.audit(id_, limit)

    @app.post("/v1/task-shield/sessions/{id_}/check-content", dependencies=dependencies)
    def content(id_: Id, payload: InspectRequest, request: Request):
        # Inspection can never add objectives. Source USER is not accepted on this route.
        return engine(request).check(
            id_,
            Message(
                message_id="inspect_" + uuid4().hex,
                role=payload.source,
                content=payload.content,
                tool_name=payload.tool_name,
                tool_call_id=payload.tool_call_id,
            ),
        )

    @app.post("/v1/task-shield/sessions/{id_}/check-tool", dependencies=dependencies)
    def tool(id_: Id, payload: ToolRequest, request: Request):
        return engine(request).check(
            id_,
            Message(
                message_id="inspect_" + uuid4().hex,
                role="ASSISTANT",
                content=payload.related_content or payload.tool_name,
                tool_name=payload.tool_name,
            ),
            tool=payload.model_dump(),
        )
