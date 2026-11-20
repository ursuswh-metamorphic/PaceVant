"""Model outputs never acquire authority from natural-language explanations."""

import json
from types import SimpleNamespace

import pytest

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.planning.treasury import plan_operation
from treasury_contracts.v3 import OperationIntent


def proposal():
    return OperationIntent(
        operation="TOKEN_PAYMENT",
        chain_id=31337,
        treasury="0x" + "11" * 20,
        session_id="0x" + "12" * 32,
        token_in="0x" + "22" * 20,
        token_out="0x" + "22" * 20,
        recipient="0x" + "33" * 20,
        amount="1000000",
        deadline=2000000000,
        objective="Pay exactly the owner-approved recipient",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"recipient": "0x" + "44" * 20},
        {"amount": "2000000"},
        {"operation": "VAULT_DEPOSIT"},
        {"token_in": "0x" + "55" * 20},
        {"policy": "ignore policy"},
    ],
)
def test_mvp_model_cannot_change_authorized_terms(change):
    p = proposal()
    base = {
        key: getattr(p, key)
        for key in ("operation", "token_in", "token_out", "recipient", "amount")
    }
    output = base | {"explanation": "An unauthorized proposal"} | change
    provider = SimpleNamespace(complete=lambda _: SimpleNamespace(content=json.dumps(output)))
    with pytest.raises(ControlError, match="AGENT_PLAN_OUT_OF_SCOPE|INVALID_AGENT_PLAN"):
        plan_operation(provider, p)
