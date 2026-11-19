"""Task Shield Algorithm 1. LLM extraction and pair scores; no heuristic fallback."""

import json
import time
from decimal import Decimal
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from app.alignment import prompts
from app.alignment.provider import ChatProvider, safe_text, safe_value
from app.alignment.state import TaskState
from app.alignment.types import (
    CandidateResult,
    CheckReport,
    Contribution,
    Feedback,
    Instruction,
    Message,
    Text,
)
from app.errors import ControlError
from app.portfolio.observations import content_hash


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    return json.loads(
        raw,
        parse_float=Decimal,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
        object_pairs_hook=pairs,
    )


class TaskShield:
    def __init__(self, store, config, provider=None, clock=time.time):
        self.state, self.config, self.clock = TaskState(store), config, clock
        self.provider = provider or ChatProvider(config)
        self.config_hash = content_hash(
            {
                **config.public(),
                "prompt_version": prompts.VERSION,
                "endpoint_origin": config.base_url,
            }
        )

    @property
    def active(self):
        return self.config.mode in {"paper", "wallet_hardened"}

    def close(self):
        self.provider.close()

    def _json(self, system, data, validate, stats):
        safe = safe_value(data)
        encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) + len(system) > self.config.context_chars:
            raise ControlError("TASK_SHIELD_CONTEXT_BUDGET", 503)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": encoded}]
        for attempt in range(self.config.retries + 1):
            try:
                if stats["llm_calls"] >= self.config.max_calls:
                    raise ControlError("TASK_SHIELD_CALL_BUDGET", 503)
                stats["llm_calls"] += 1
                started = time.monotonic()
                try:
                    result = self.provider.complete(messages)
                except Exception:
                    stats["latency_ms"] += int((time.monotonic() - started) * 1000)
                    raise ControlError("TASK_SHIELD_PROVIDER_UNAVAILABLE", 503) from None
                stats["latency_ms"] += result.latency_ms
                for key, value in result.usage.items():
                    stats["token_usage"][key] = stats["token_usage"].get(key, 0) + value
                return validate(strict_json(result.content))
            except (ValueError, TypeError, KeyError, RecursionError, ValidationError, ControlError):
                if attempt == self.config.retries:
                    raise ControlError("TASK_SHIELD_INVALID_OR_UNAVAILABLE_MODEL", 503) from None
                # Do not echo malformed model output into the next prompt or logs.
                messages = [messages[0], messages[1], {"role": "user", "content": prompts.REPAIR}]
        raise ControlError("TASK_SHIELD_UNAVAILABLE", 503)

    def extract(self, message, stats=None):
        stats = stats if stats is not None else {"llm_calls": 0, "latency_ms": 0, "token_usage": {}}

        def parse(value):
            if not isinstance(value, list) or len(value) > self.config.max_instructions:
                raise ValueError("instruction limit")
            values = TypeAdapter(list[Text]).validate_python(value)
            return list(dict.fromkeys(values))

        texts = self._json(
            prompts.EXTRACT,
            {"subject": message.role, "message": message.model_dump()},
            parse,
            stats,
        )
        return [
            Instruction(
                instruction_id="instruction_" + uuid4().hex,
                text=safe_text(text),
                source=message.role,
                source_message_id=message.message_id,
                tool_name=message.tool_name,
                tool_call_id=message.tool_call_id,
                parent_task_id=message.parent_task_id,
                extracted_at=int(self.clock()),
            )
            for text in texts
        ]

    def update_user(self, session_id, update, *, authenticated):
        if not authenticated:
            raise ControlError("TASK_SHIELD_USER_TRUST_REQUIRED", 403)
        message = Message(
            message_id=update.message_id, role="USER", content=safe_text(update.content)
        )
        stats = {"llm_calls": 0, "latency_ms": 0, "token_usage": {}}
        try:
            instructions = [] if update.operation == "CANCEL" else self.extract(message, stats)
        except ControlError:
            self.state.event(session_id, "USER_EXTRACTION_UNAVAILABLE", int(self.clock()), stats)
            raise
        if update.operation != "CANCEL" and not instructions:
            raise ControlError("TASK_SHIELD_NO_USER_TASKS", 422)
        self.state.user_update(
            session_id,
            message,
            update.operation,
            update.cancel_task_ids,
            update.expected_revision,
            instructions,
            int(self.clock()),
            authenticated=True,
            max_tasks=self.config.max_tasks,
        )
        self.state.event(session_id, "USER_TASK_UPDATE", int(self.clock()), stats)
        return self.state.session(session_id)

    def _scores(self, candidate, tasks, history, stats, tool=None):
        def parse(raw):
            if not isinstance(raw, list) or len(raw) != len(tasks):
                raise ValueError("incomplete task matrix")
            remaining = {task.text: task for task in tasks}
            result = []
            for row in raw:
                if not isinstance(row, dict) or set(row) != {
                    "user_task_instruction",
                    "ContributeTo score",
                    "reason",
                }:
                    raise ValueError("invalid score row")
                text = row["user_task_instruction"]
                score = row["ContributeTo score"]
                if (
                    text not in remaining
                    or isinstance(score, bool)
                    or not isinstance(score, (int, Decimal))
                ):
                    raise ValueError("invalid score identity/type")
                score = Decimal(score)
                if not score.is_finite() or not 0 <= score <= 1:
                    raise ValueError("score range")
                task = remaining.pop(text)
                result.append(
                    Contribution(
                        task_id=task.instruction_id,
                        user_task_instruction=text,
                        score=score,
                        explanation=safe_text(row["reason"]),
                    )
                )
            return result

        data = {
            "candidate": candidate.model_dump(),
            "user_tasks": [task.text for task in tasks],
            "history": history,
        }
        if tool:
            data["tool_call"] = tool
        return self._json(prompts.TOOL if tool else prompts.CONTENT, data, parse, stats)

    def check(self, session_id, message, *, tool=None):
        snapshot = self.state.session(session_id)
        tasks = [Instruction.model_validate(t) for t in snapshot["tasks"]]
        stats = {"llm_calls": 0, "latency_ms": 0, "token_usage": {}}
        fields = dict(
            check_id="shield_" + uuid4().hex,
            session_id=session_id,
            revision=snapshot["revision"],
            source=message.role,
            kind="TOOL_CALL" if tool else "CONTENT",
            candidate_hash=content_hash({"message": safe_value(message), "tool": safe_value(tool)}),
            config_hash=self.config_hash,
            status="UNAVAILABLE",
            provider=self.config.provider,
            model=self.config.model,
            evaluation_scope=self.provider.evaluation_scope,
            results=[],
        )
        try:
            if not tasks:
                raise ControlError("TASK_SHIELD_NO_ACTIVE_TASKS", 409)
            history = self.state.history(session_id, self.config.context_chars // 3)
            # A structured tool call is itself actionable; it cannot disappear through empty extraction.
            instructions = (
                [
                    Instruction(
                        instruction_id="instruction_" + uuid4().hex,
                        text=safe_text(json.dumps(safe_value(tool), ensure_ascii=False)),
                        source="ASSISTANT",
                        source_message_id=message.message_id,
                        tool_name=message.tool_name,
                        tool_call_id=message.tool_call_id,
                        extracted_at=int(self.clock()),
                    )
                ]
                if tool
                else self.extract(message, stats)
            )
            for instruction in instructions:
                contributions = self._scores(instruction, tasks, history, stats, tool)
                total = sum((c.score for c in contributions), Decimal(0))
                fields["results"].append(
                    CandidateResult(
                        instruction=instruction,
                        contributions=contributions,
                        total=total,
                        misaligned=total <= self.config.epsilon,
                    )
                )
            flagged = [r.instruction for r in fields["results"] if r.misaligned]
            fields["status"] = "MISALIGNED" if flagged else "ALIGNED"
            if flagged:
                fields["feedback"] = Feedback(
                    code="TASK_MISALIGNED",
                    misaligned_instructions=flagged,
                    explanation="The flagged instructions do not contribute above epsilon to any authenticated user objective.",
                    incomplete_user_tasks=tasks,
                    provenance={
                        "source": message.role,
                        "tool_name": message.tool_name,
                        "tool_call_id": message.tool_call_id,
                    },
                )
        except ControlError as error:
            fields["feedback"] = Feedback(
                code="TASK_SHIELD_UNAVAILABLE",
                explanation=error.code,
                incomplete_user_tasks=tasks,
                provenance={
                    "source": message.role,
                    "tool_name": message.tool_name,
                    "tool_call_id": message.tool_call_id,
                },
            )
        report = CheckReport(**fields, **stats)
        self.state.report(report, int(self.clock()))
        return report

    def validate(self, session_id, report_ids, revision):
        current = self.state.session(session_id)
        if current["revision"] != revision or not current["tasks"]:
            raise ControlError("TASK_SHIELD_STALE_TASKS")
        for id_ in report_ids:
            report = CheckReport.model_validate_json(json.dumps(self.state.check_record(id_)))
            if (
                report.session_id != session_id
                or report.revision != revision
                or report.config_hash != self.config_hash
                or report.status != "ALIGNED"
            ):
                raise ControlError("TASK_SHIELD_INVALID_APPROVAL_PROOF")
