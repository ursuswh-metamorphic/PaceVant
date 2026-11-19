"""Interception in the existing orchestration, with feedback delivered to its planner."""

import json
from uuid import uuid4

from app.alignment.provider import safe_value
from app.alignment.types import Message
from app.errors import ControlError


class ShieldBlocked(ControlError):
    def __init__(self, report):
        super().__init__(
            "TASK_MISALIGNED" if report.status == "MISALIGNED" else "TASK_SHIELD_UNAVAILABLE"
        )
        self.report = report


class ShieldRuntime:
    def __init__(self, shield, session_id):
        self.shield, self.session_id = shield, session_id
        self.last_feedback = None
        self.reports = []

    def _require(self, report):
        if report.status != "ALIGNED":
            self.last_feedback = report.feedback
            raise ShieldBlocked(report)
        self.reports.append(report.check_id)

    def assistant(self, content):
        message = Message(message_id="assistant_" + uuid4().hex, role="ASSISTANT", content=content)
        report = self.shield.check(self.session_id, message)
        self._require(report)
        self.shield.state.context(
            self.session_id,
            {"message": safe_value(message), "trust": "ASSISTANT_NOT_AUTHORIZATION"},
        )
        return report

    def before(self, name, arguments, related_content=""):
        call_id = "call_" + uuid4().hex
        message = Message(
            message_id=call_id,
            role="ASSISTANT",
            content=related_content or name,
            tool_name=name,
            tool_call_id=call_id,
        )
        tool = {
            "tool_name": name,
            "arguments": safe_value(arguments),
            "related_content": related_content,
        }
        report = self.shield.check(self.session_id, message, tool=tool)
        self._require(report)
        return call_id, tool, report

    def output(self, name, call_id, tool, value):
        safe = safe_value(value)
        encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 16000:
            # Never truncate away a trailing injection and claim the complete response was checked.
            self.shield.state.event(
                self.session_id,
                "OUTPUT_BUDGET_EXCEEDED",
                int(self.shield.clock()),
                {"tool_name": name, "tool_call_id": call_id},
            )
            raise ControlError("TASK_SHIELD_OUTPUT_BUDGET", 503)
        message = Message(
            message_id="output_" + uuid4().hex,
            role="TOOL",
            content=encoded,
            tool_name=name,
            tool_call_id=call_id,
        )
        report = self.shield.check(self.session_id, message)
        self.shield.state.context(
            self.session_id,
            {
                "call": tool,
                "tool_call_id": call_id,
                "output": safe,
                "trust": "UNTRUSTED_TOOL",
                "feedback": report.feedback.model_dump(mode="json") if report.feedback else None,
            },
        )
        if report.status == "UNAVAILABLE" or (
            report.status == "MISALIGNED" and self.shield.config.mode == "wallet_hardened"
        ):
            self._require(report)
        if report.feedback:
            self.last_feedback = report.feedback
            self.shield.state.event(
                self.session_id,
                "INPUT_FEEDBACK",
                int(self.shield.clock()),
                report.feedback.model_dump(mode="json"),
            )
        return report

    def invoke(self, name, arguments, execute, related_content=""):
        call_id, tool, _ = self.before(name, arguments, related_content)
        value = execute()
        self.output(name, call_id, tool, value)
        return value

    def proof(self, proposal):
        session = self.shield.state.session(self.session_id)
        return {
            "session_id": self.session_id,
            "revision": session["revision"],
            "config_hash": self.shield.config_hash,
            "check_ids": list(self.reports),
            "proposal": safe_value(proposal),
            "unresolved_feedback": self.last_feedback.model_dump(mode="json")
            if self.last_feedback
            else None,
        }
