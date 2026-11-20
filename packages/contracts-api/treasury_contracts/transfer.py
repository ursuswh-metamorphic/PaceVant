"""Transfer wire types and action-separated EIP-712 encoding."""

from typing import Literal

from eth_account.messages import encode_typed_data
from pydantic import Field, model_validator

from .wire import Address, UInt, Wire

TRANSFER_FIELDS = [
    ("intentHash", "bytes32"),
    ("taskHash", "bytes32"),
    ("policyHash", "bytes32"),
    ("evidenceRoot", "bytes32"),
    ("proofContextHash", "bytes32"),
    ("sessionId", "bytes32"),
    ("transferPolicyVersion", "uint256"),
    ("taskBudget", "uint256"),
    ("riskDebitUsdE8", "uint256"),
    ("nonce", "uint256"),
    ("deadline", "uint256"),
    ("token", "address"),
    ("recipient", "address"),
    ("amount", "uint256"),
]


class TransferTask(Wire):
    task_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1)
    chain_id: int = Field(gt=0)
    vault_address: Address
    token: Address
    recipient: Address
    objective: str = Field(min_length=1, max_length=1200)
    total_budget: UInt
    per_transfer: UInt
    deadline: int = Field(gt=0, le=2**53 - 1)
    one_shot: bool = True

    @model_validator(mode="after")
    def positive_limits(self):
        if not 0 < int(self.per_transfer) <= int(self.total_budget):
            raise ValueError("Invalid transfer limits")
        if int(self.recipient, 16) == 0 or self.recipient.lower() == self.vault_address.lower():
            raise ValueError("Invalid transfer recipient")
        return self


class TransferProposal(Wire):
    action: Literal["TRANSFER_ERC20"] = "TRANSFER_ERC20"
    intent_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1)
    chain_id: int = Field(gt=0)
    vault_address: Address
    token: Address
    recipient: Address
    amount_base_units: UInt
    deadline: int = Field(gt=0, le=2**53 - 1)
    user_goal_reason: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def positive_amount(self):
        if int(self.amount_base_units) == 0 or int(self.recipient, 16) == 0:
            raise ValueError("Positive amount and nonzero recipient required")
        return self


class TransferRequest(Wire):
    task_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=1200)
    amount_base_units: UInt | None = None


def transfer_message(chain_id, vault, approval):
    return encode_typed_data(
        full_message={
            "types": {
                "EIP712Domain": [
                    {"name": n, "type": t}
                    for n, t in [
                        ("name", "string"),
                        ("version", "string"),
                        ("chainId", "uint256"),
                        ("verifyingContract", "address"),
                    ]
                ],
                "TransferApprovalV2": [{"name": n, "type": t} for n, t in TRANSFER_FIELDS],
            },
            "primaryType": "TransferApprovalV2",
            "domain": {
                "name": "TreasuryPolicyVault",
                "version": "transfer-2",
                "chainId": chain_id,
                "verifyingContract": vault,
            },
            "message": approval,
        }
    )


def transfer_tuple(approval):
    return tuple(approval[n] for n, _ in TRANSFER_FIELDS)
