"""Interception in the existing orchestration, with feedback delivered to its planner."""

import json
from uuid import uuid4

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment.provider import safe_value
from treasury_backend.modules.alignment.serialization import semantic_value
from treasury_backend.modules.alignment.types import Message


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
        self.attempt_checks = []
        self.pending_outputs = []

    def defer_data(self, name, arguments, value):
        # Inspect the returned data, not a replay of our already-authorized call.
        # Preserve call arguments separately as an immutable operational audit event.
        self.shield.state.event(
            self.session_id,
            "PIPELINE_DATA_OPERATION",
            int(self.shield.clock()),
            {"tool_name": name, "arguments": semantic_value(arguments)},
        )
        self.pending_outputs.append({"tool_name": name, "output": semantic_value(value)})

    def flush_data(self):
        pending = list(self.pending_outputs)
        group = []
        for record in pending:
            if group and len(json.dumps(group + [record], ensure_ascii=False)) > 14000:
                self._data_group(group)
                del self.pending_outputs[: len(group)]
                group = []
            group.append(record)
        if group:
            self._data_group(group)
            del self.pending_outputs[: len(group)]

    def _data_group(self, records):
        call_id = "data_batch_" + uuid4().hex
        self.output(
            "verified_execution_evidence",
            call_id,
            {
                "tool_name": "verified_execution_evidence",
                "arguments": {"source_tools": [r["tool_name"] for r in records]},
            },
            {"type": "UNTRUSTED_READ_ONLY_EVIDENCE_BATCH", "records": records},
        )

    def _require(self, report):
        self.attempt_checks.append(report.check_id)
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
            "arguments": semantic_value(arguments),
            "related_content": related_content,
        }
        report = self.shield.check(self.session_id, message, tool=tool)
        self._require(report)
        return call_id, tool, report

    def output(self, name, call_id, tool, value):
        safe = semantic_value(value)
        encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > self.shield.config.max_output_chars:
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
                "check_id": report.check_id,
                "trust": "UNTRUSTED_TOOL",
                "feedback": report.feedback.model_dump(mode="json") if report.feedback else None,
            },
        )
        if report.status in {"UNAVAILABLE", "UNCERTAIN"} or self.shield.config.mode in {
            "wallet_hardened",
            "wallet_pipeline",
        }:
            self._require(report)
            return report
        if report.feedback:
            self.last_feedback = report.feedback
            self.shield.state.event(
                self.session_id,
                "INPUT_FEEDBACK",
                int(self.shield.clock()),
                report.feedback.model_dump(mode="json"),
            )
        self.attempt_checks.append(report.check_id)
        return report

    def invoke(self, name, arguments, execute, related_content=""):
        call_id, tool, _ = self.before(name, arguments, related_content)
        value = execute()
        self.output(name, call_id, tool, value)
        return value

    def proof(self, proposal):
        if self.pending_outputs:
            raise ControlError("TASK_SHIELD_UNINSPECTED_EVIDENCE")
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
