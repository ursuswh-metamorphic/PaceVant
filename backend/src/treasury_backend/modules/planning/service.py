import re
from uuid import uuid4

from treasury_backend.core.models import Mandate
from treasury_contracts.models import TransactionProposal

VERSION = "rules-v1"
GOAL = re.compile(
    r"(?:buy|mua) WAVAX (?:with|bằng) ((?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?) USDC",
    re.IGNORECASE,
)
REVERSE_GOAL = re.compile(
    r"(?:sell|bán) ((?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,18})?) WAVAX (?:for|lấy) USDC", re.IGNORECASE
)


def reverse_goal(goal):
    return REVERSE_GOAL.fullmatch(goal.strip()) is not None


def requested_amount(goal: str) -> int | None:
    reverse = reverse_goal(goal)
    match = REVERSE_GOAL.fullmatch(goal.strip()) if reverse else GOAL.fullmatch(goal.strip())
    if not match:
        return None
    whole, _, fraction = match[1].partition(".")
    decimals = 18 if reverse else 6
    return int(whole) * 10**decimals + int(fraction.ljust(decimals, "0"))


def propose(
    mandate: Mandate,
    amount: int,
    deadline: int,
    *,
    alternate_recipient: str | None = None,
    reverse=False,
) -> TransactionProposal:
    return TransactionProposal(
        intent_id=f"intent_{uuid4().hex}",
        mandate_id=mandate.mandate_id,
        mandate_version=mandate.version,
        action="SWAP_EXACT_INPUT",
        chain_id=mandate.chain_id,
        vault_address=mandate.vault_address,
        router=mandate.router,
        token_in=mandate.token_out if reverse else mandate.token_in,
        token_out=mandate.token_in if reverse else mandate.token_out,
        amount_in_base_units=str(amount),
        slippage_bps=mandate.max_slippage_bps,
        recipient=alternate_recipient or mandate.vault_address,
        deadline=deadline,
        user_goal_reason=("Rebalance WAVAX into USDC within the owner's allocation limits" if reverse
                          else "Rebalance USDC into WAVAX within the owner's allocation limits"),
    )


def revise(mandate, amount, deadline, feedback, *, reverse=False):
    """Existing rules planner receives shield feedback; reissues a mandate-bound proposal.

    It cannot invent new user tasks or arbitrary tool names/arguments. General natural-language
    replanning requires a future planner implementation, not a separate verification agent.
    """
    if feedback.code not in {"TASK_MISALIGNED", "TASK_SHIELD_UNAVAILABLE"}:
        raise ValueError("Unsupported planner feedback")
    return propose(mandate, amount, deadline, reverse=reverse)
