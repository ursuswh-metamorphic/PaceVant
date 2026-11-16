import re
from uuid import uuid4

from app.models import Mandate
from treasury_contracts.models import TransactionProposal

VERSION = "rules-v1"
GOAL = re.compile(
    r"(?:buy|mua) WAVAX (?:with|bằng) ((?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?) USDC",
    re.IGNORECASE,
)


def requested_amount(goal: str) -> int | None:
    match = GOAL.fullmatch(goal.strip())
    if not match:
        return None
    whole, _, fraction = match[1].partition(".")
    return int(whole) * 10**6 + int(fraction.ljust(6, "0"))


def propose(
    mandate: Mandate, amount: int, deadline: int, *, alternate_recipient: str | None = None
) -> TransactionProposal:
    return TransactionProposal(
        intent_id=f"intent_{uuid4().hex}",
        mandate_id=mandate.mandate_id,
        mandate_version=mandate.version,
        action="SWAP_EXACT_INPUT",
        chain_id=mandate.chain_id,
        vault_address=mandate.vault_address,
        router=mandate.router,
        token_in=mandate.token_in,
        token_out=mandate.token_out,
        amount_in_base_units=str(amount),
        slippage_bps=mandate.max_slippage_bps,
        recipient=alternate_recipient or mandate.vault_address,
        deadline=deadline,
        user_goal_reason="Rebalance test USDC into WAVAX within the owner's allocation limits",
    )
