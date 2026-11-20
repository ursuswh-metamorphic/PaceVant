"""Hybrid assessment adapter used by the production TaskShield, not by benchmark labels."""

from uuid import uuid4

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.alignment import hybrid, prompts
from treasury_backend.modules.alignment.hybrid_types import (
    ConstraintResult,
    SemanticFinding,
    TaskBinding,
)
from treasury_backend.modules.alignment.provider import safe_value
from treasury_backend.modules.alignment.types import CheckReport, Feedback
from treasury_backend.modules.portfolio.observations import content_hash


def check(shield, session_id, message, tool):
    state, now = shield.state, int(shield.clock())
    session = state.session(session_id)
    candidate_hash = content_hash({"message": safe_value(message), "tool": safe_value(tool)})
    # Use an opaque catalog alias: credential redaction deliberately masks 0x256-bit
    # literals, so asking a model to echo a raw hash would invalidate every citation.
    action_ref = "action_" + candidate_hash[2:]
    stats = {"llm_calls": 0, "latency_ms": 0, "token_usage": {}}
    fields = dict(
        check_id="shield_" + uuid4().hex,
        session_id=session_id,
        revision=session["revision"],
        source=message.role,
        kind="TOOL_CALL" if tool else "CONTENT",
        candidate_hash=candidate_hash,
        config_hash=shield.config_hash,
        status="UNCERTAIN",
        algorithm="hybrid-v1",
        provider=shield.config.provider,
        model=shield.config.model,
        evaluation_scope=shield.provider.evaluation_scope,
        source_message_id=message.message_id,
        tool_call_id=message.tool_call_id,
        tool_name=message.tool_name,
        prompt_version=prompts.VERSION,
    )
    binding = TaskBinding(
        revision=session["revision"],
        action_ref=action_ref,
        verdict="UNRESOLVED",
        explanation="No verified binding yet.",
    )
    checks, findings = [], []
    try:
        schema = state.protocol_schema(session_id) or {}
        intents = state.active_intents(session_id)
        if not intents:
            raise ControlError("TASK_SHIELD_NO_ACTIVE_AUTHENTICATED_SCOPE")
        try:
            tx = hybrid.normalize(tool.get("arguments", {}), schema) if tool else None
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            tx = None
            checks.append(
                ConstraintResult(
                    constraint_id="technical",
                    constraint_type="ABI",
                    boundary="TECHNICAL",
                    expected="Valid canonical transaction",
                    observed=None,
                    status="FAIL",
                    violation_code="INVALID_TRANSACTION",
                    evidence_refs=[action_ref],
                    explanation=str(exc)[:200],
                )
            )
        if tx is not None:
            fields["action_input_hash"] = content_hash(safe_value(tool["arguments"]))
            binding, constraints = hybrid.bind(
                intents, tx, schema, now, action_ref, session["revision"], message.parent_task_id
            )
            checks.extend(constraints)
        else:
            matching = [
                i
                for i in intents
                if not message.parent_task_id or message.parent_task_id in i.task_ids
            ]
            if len(matching) == 1:
                intent = matching[0]
                binding = TaskBinding(
                    task_id=intent.task_id,
                    source_message_id=intent.source_message_id,
                    revision=session["revision"],
                    action_ref=action_ref,
                    verdict="VALID",
                    evidence_refs=[intent.source_message_id, action_ref],
                    explanation="Read-only/content assessment scoped to the unique authenticated objective.",
                )
            else:
                binding = binding.model_copy(
                    update={"verdict": "AMBIGUOUS" if matching else "UNAUTHORIZED"}
                )
            if tool and any(
                word in tool.get("tool_name", "").lower()
                for word in ("swap", "transfer", "execute", "sign", "attest")
            ):
                # Opaque execute/sign calls are separately committed/revalidated by the wallet.
                # They cannot establish a fresh financial action authorization here.
                checks.append(
                    ConstraintResult(
                        constraint_id="transaction-shape",
                        constraint_type="TRANSACTION_SHAPE",
                        boundary="TECHNICAL",
                        expected="Decoded proposal or previously verified wallet execution",
                        observed=None,
                        status="UNKNOWN",
                        violation_code="UNRESOLVED_TRANSACTION_SHAPE",
                        evidence_refs=[action_ref],
                        explanation="No canonical financial transaction was decoded.",
                    )
                )
        # Deterministic failures dominate even when inference is unavailable. Avoid unnecessary calls.
        if any(c.status == "FAIL" for c in checks) or binding.verdict == "UNAUTHORIZED":
            fields["status"] = "MISALIGNED"
        elif binding.verdict == "VALID":
            intent = next(i for i in intents if i.task_id == binding.task_id)
            history = state.history(session_id, min(8000, shield.config.context_chars // 3))
            catalog = {
                intent.source_message_id: {
                    "trust": "AUTHENTICATED_USER",
                    "text": intent.original_text,
                },
                action_ref: {
                    "trust": message.role,
                    "message": safe_value(message),
                    "tool": safe_value(tool),
                },
            }
            for index, item in enumerate(history):
                catalog[f"history:{index}"] = item

            def validate(raw):
                finding = SemanticFinding.model_validate(raw)
                refs = set(finding.evidence_refs)
                if (
                    finding.task_id != binding.task_id
                    or finding.action_ref != action_ref
                    or not refs <= set(catalog)
                    or not {intent.source_message_id, action_ref} <= refs
                    or finding.finding_type in {"GOAL_DRIFT", "PROMPT_INJECTION"}
                    and finding.verdict == "ALIGNED"
                ):
                    raise ValueError("Semantic evidence identity/context mismatch")
                return finding

            findings.append(
                shield._json(
                    prompts.HYBRID_SEMANTIC,
                    {
                        "bound_task_id": binding.task_id,
                        "action_ref": action_ref,
                        "authenticated_objective": intent.original_text,
                        "proposed_task_interpretations": [
                            t["text"]
                            for t in session["tasks"]
                            if t["instruction_id"] in intent.task_ids
                        ],
                        "candidate": safe_value(message),
                        "tool_call": safe_value(tool),
                        "deterministic_results": [c.model_dump(mode="json") for c in checks],
                        "evidence_catalog": catalog,
                    },
                    validate,
                    stats,
                )
            )
            fields["status"] = hybrid.fuse(binding, checks, findings)
    except ControlError as exc:
        fields["status"] = hybrid.fuse(binding, checks, [])
        fields["feedback"] = Feedback(code="TASK_SHIELD_UNAVAILABLE", explanation=exc.code)
    fields.update(binding=binding, constraints=checks, semantic_findings=findings)
    if fields["status"] != "ALIGNED" and not fields.get("feedback"):
        fields["feedback"] = Feedback(
            code="TASK_MISALIGNED"
            if fields["status"] == "MISALIGNED"
            else "TASK_SHIELD_UNAVAILABLE",
            explanation="; ".join(c.violation_code for c in checks if c.status != "PASS")
            or binding.explanation,
            provenance={"action_ref": action_ref, "binding": binding.model_dump(mode="json")},
        )
    report = CheckReport(**fields, **stats)
    state.report(report, now)
    return report
