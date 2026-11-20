"""Transfer SDE gate. Explicit independent financial and semantic prerequisites."""


def decide_transfer(proposal, evidence):
    required = (
        evidence["shield"]["status"] == "ALIGNED",
        evidence["semantic"]["verdict"] == "ALIGNED",
        evidence["temporal"]["verdict"] == "PASS",
        evidence["risk"]["result"] == "PASS",
        evidence["proof"]["status"] == "VERIFIED",
        evidence["simulation"]["source"] == "ISOLATED_ANVIL_FORK",
        proposal.action == "TRANSFER_ERC20",
    )
    return {
        "verdict": "APPROVE" if all(required) else "ESCALATE",
        "reason_codes": [] if all(required) else ["TRANSFER_INCOMPLETE_SECURITY_EVIDENCE"],
        "action": "TRANSFER_ERC20",
        "intent_id": proposal.intent_id,
    }
