import re

from eth_utils import keccak

from app.models import Alignment, Mandate
from app.planner import requested_amount
from treasury_contracts.models import TransactionProposal

INJECTION = re.compile(
    r"ignore.{0,50}(?:policy|instructions)|bỏ qua.{0,50}(?:policy|chính sách)|"
    r"override.{0,50}policy|(?:send|transfer|gửi|chuyển).{0,65}0x[0-9a-f]{40}",
    re.IGNORECASE | re.DOTALL,
)


def check(
    mandate: Mandate, proposal: TransactionProposal, goal: str, tool_output: str = ""
) -> Alignment:
    evidence = [f"0x{keccak(text=tool_output).hex()}"] if tool_output else []
    reasons = []
    if (proposal.token_in, proposal.token_out) != (mandate.token_in, mandate.token_out):
        reasons.append("TOKEN_NOT_ALLOWED")
    if proposal.router != mandate.router:
        reasons.append("ROUTER_NOT_ALLOWED")
    if proposal.recipient != mandate.vault_address:
        reasons.append("BAD_RECIPIENT")
    if (
        (proposal.chain_id, proposal.vault_address, proposal.mandate_id, proposal.mandate_version)
        != (mandate.chain_id, mandate.vault_address, mandate.mandate_id, mandate.version)
        or proposal.slippage_bps > mandate.max_slippage_bps
        or INJECTION.search(tool_output)
    ):
        reasons.append("TASK_MISALIGNED")
    if reasons:
        return Alignment(
            verdict="MISALIGNED",
            reason_codes=[
                "TASK_MISALIGNED",
                *dict.fromkeys(reason for reason in reasons if reason != "TASK_MISALIGNED"),
            ],
            evidence_refs=evidence,
        )
    amount = requested_amount(goal)
    if amount is None:
        return Alignment(
            verdict="UNCERTAIN", reason_codes=["TASK_UNCERTAIN"], evidence_refs=evidence
        )
    if not 0 < int(proposal.amount_in_base_units) <= amount:
        return Alignment(
            verdict="MISALIGNED", reason_codes=["TASK_MISALIGNED"], evidence_refs=evidence
        )
    return Alignment(verdict="ALIGNED", reason_codes=[], evidence_refs=evidence)
