"""Unsigned, persisted evidence for hybrid intent enforcement. Not signing authority."""

from typing import Literal

from pydantic import Field

from treasury_contracts.models import Wire


class Constraint(Wire):
    constraint_id: str
    kind: str
    operator: Literal["EQ", "LE", "GE", "BOUND", "UNKNOWN"]
    value: str
    unit: str
    source_message_id: str
    task_id: str
    revision: int
    source_span: str
    ambiguity: str | None = None
    mandatory: bool = True
    extraction_method: str = "SOURCE_ANCHORED_GRAMMAR"


class IntentEnvelope(Wire):
    task_id: str
    task_ids: list[str]
    source_message_id: str
    revision: int
    original_text: str
    operation: Literal["SWAP", "TRANSFER", "VAULT_DEPOSIT", "VAULT_WITHDRAW", "UNRESOLVED"]
    constraints: list[Constraint]
    unresolved: list[str] = Field(default_factory=list)
    authority: Literal["AUTHENTICATED_USER"] = "AUTHENTICATED_USER"
    authorization_ref: str | None = None


class ConstraintResult(Wire):
    constraint_id: str
    constraint_type: str
    boundary: Literal["USER_INTENT", "TECHNICAL", "METADATA"] = "USER_INTENT"
    expected: str
    observed: str | None
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    violation_code: str
    evidence_refs: list[str]
    explanation: str


class TaskBinding(Wire):
    task_id: str | None = None
    source_message_id: str | None = None
    revision: int
    action_ref: str
    verdict: Literal["VALID", "UNAUTHORIZED", "AMBIGUOUS", "UNRESOLVED"]
    evidence_refs: list[str] = Field(default_factory=list)
    explanation: str
    authorization_ref: str | None = None


class SemanticFinding(Wire):
    task_id: str
    action_ref: str
    finding_type: Literal["OBJECTIVE_ALIGNMENT", "GOAL_DRIFT", "PROMPT_INJECTION", "UNRESOLVED"]
    verdict: Literal["ALIGNED", "MISALIGNED", "UNCERTAIN"]
    evidence_refs: list[str] = Field(min_length=2, max_length=16)
    explanation: str = Field(min_length=1, max_length=2000)
