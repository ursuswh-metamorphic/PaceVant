from typing import Annotated, Literal

from pydantic import Field

from treasury_backend.core.domain import Id
from treasury_backend.core.models import IntentSelection as IntentSelection
from treasury_contracts.models import Address, Hash, UInt, Wire

IntentKind = Literal["ONE_SHOT_SWAP", "BOUNDED_SWAP", "ORDERED_TASK"]
IntentStatus = Literal["PROPOSED", "AUTHENTICATED", "CANCELLED", "SUPERSEDED"]
Text = Annotated[str, Field(min_length=1, max_length=1200)]
NodeKind = Literal[
    "MANDATE",
    "AUTHENTICATED_USER_INTENT",
    "AGENT_ACTION",
    "TOOL_OBSERVATION",
    "SEMANTIC_ASSESSMENT",
    "SECURITY_DECISION",
    "TRANSACTION_OUTCOME",
    "PORTFOLIO_STATE",
]
EdgeKind = Literal[
    "AUTHORIZES",
    "DERIVED_FROM",
    "EVALUATED_BY",
    "CONTRIBUTES_TO",
    "DEPENDS_ON",
    "PRECEDES",
    "EXECUTED_AS",
    "PRODUCED_OUTCOME",
    "UPDATED_STATE",
    "SUPERSEDES",
]


class Step(Wire):
    step_id: Id
    min_amount: UInt
    max_amount: UInt
    prerequisites: Annotated[list[Id], Field(max_length=8)] = Field(default_factory=list)


class IntentTerms(Wire):
    kind: IntentKind
    mandate_id: Id
    objective: Text | None = None
    deadline: int = Field(gt=0, le=2**53 - 1)
    total_budget: UInt
    steps: Annotated[list[Step], Field(min_length=1, max_length=12)]


class IntentSpec(Wire):
    schema_version: Literal["1.0"] = "1.0"
    spec_id: Id
    revision: int = Field(ge=1)
    status: IntentStatus
    terms: IntentTerms
    mode: Literal["MOCK", "LOCAL", "FUJI"]
    chain_id: Literal[31337, 43113]
    vault_address: Address
    token_in: Address
    token_out: Address
    router: Address
    mandate_hash: Hash
    policy_hash: Hash
    authorization_source: Literal["OPERATOR_API", "PROPOSAL_ONLY"]
    recorded_at: int
    completion: Literal["ALL_STEPS_VERIFIED", "BUDGET_SPENT"]




class GraphNode(Wire):
    node_id: str
    kind: NodeKind
    trust: Literal["AUTHENTICATED", "VERIFIED_RECORD", "UNTRUSTED", "MODEL_JUDGMENT", "UNVERIFIED"]
    evidence_refs: list[str]
    data: dict


class GraphEdge(Wire):
    edge_id: str
    source: str
    target: str
    kind: EdgeKind
    provenance: Literal["AUTHORIZATION_RECORD", "SYSTEM_RECORD", "MODEL_INFERENCE"]
    evidence_refs: list[str]


class Graph(Wire):
    schema_version: Literal["1.0"] = "1.0"
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class SemanticContribution(Wire):
    task_id: Id
    relationship: Literal["DIRECT", "INDIRECT", "IRRELEVANT", "CONTRADICTORY", "UNCERTAIN"]
    explanation: Text


class SemanticFinding(Wire):
    candidate_action_id: str
    referenced_task_ids: Annotated[list[Id], Field(max_length=32)]
    referenced_graph_node_ids: Annotated[list[str], Field(max_length=32)]
    semantic_verdict: Literal["ALIGNED", "MISALIGNED", "UNCERTAIN"]
    contribution_assessments: Annotated[list[SemanticContribution], Field(max_length=32)]
    detected_goal_drift: bool
    claimed_instruction_source: Literal["USER", "ASSISTANT", "TOOL", "UNCERTAIN"]
    reasoning_summary: Text
    supporting_evidence_refs: Annotated[list[str], Field(max_length=48)]
    uncertainty_reasons: Annotated[list[Text], Field(max_length=8)]


class SemanticAssessment(Wire):
    verdict: Literal["ALIGNED", "MISALIGNED", "UNCERTAIN", "UNAVAILABLE"]
    finding: SemanticFinding | None = None
    reason_codes: list[str]
    provider_metadata: dict
    latency_ms: int
    token_usage: dict[str, int]


class Violation(Wire):
    policy: str
    code: str
    verdict: Literal["REJECT", "REPLAN", "ESCALATE"]
    node_ids: list[str]
    detail: Text


class ConstraintAssessment(Wire):
    verdict: Literal["PASS", "REJECT", "REPLAN", "ESCALATE"]
    violations: list[Violation]
    spent: UInt
    reserved: UInt
    remaining: UInt


class HybridTemporalAssessment(Wire):
    semantic: SemanticAssessment
    deterministic: ConstraintAssessment
    graph_hash: Hash
    intent_hash: Hash
    history_hash: Hash
    task_revision: int
    history_version: int
    candidate_action_id: str
    candidate_hash: Hash
    build_hash: Hash | None
    build_id: str | None
    evidence_refs: list[str]
    verdict: Literal["PASS", "REJECT", "REPLAN", "ESCALATE"]
    reason_codes: list[str]
    violating_node_ids: list[str]
    violating_edge_ids: list[str]
    suggested_amount: UInt | None = None
    timing_ms: dict[str, int]


class ExplainableTemporalAssessment(Wire):
    assessment: HybridTemporalAssessment
    decision_summary: str
    semantic_deviation: str
    temporal_violations: list[Violation]
    evidence_path: list[GraphEdge]
    source_trust: dict[str, str]
    recovery: str
    uncertainty: list[str]
