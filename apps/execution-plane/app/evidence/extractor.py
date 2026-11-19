from web3 import Web3

TRANSFER = Web3.to_hex(Web3.keccak(text="Transfer(address,address,uint256)"))
APPROVAL = Web3.to_hex(Web3.keccak(text="Approval(address,address,uint256)"))


def token_facts(receipt, vault, router, usdc, wavax, amount, min_out, dex_route=None):
    """Parse all receipt logs; unfamiliar transfer/approval effects fail closed."""
    incoming, outgoing, unexpected, unauthorized = 0, 0, False, False
    transfers, approvals = [], []
    vault, router, usdc, wavax = [a.lower() for a in (vault, router, usdc, wavax)]
    # A fixed, verified single-hop LFJ path. Downstream effects are allowlisted exactly.
    downstream_in = 0
    pair = dex_route["pair"].lower() if dex_route else None
    dex_router = dex_route["lfj_router"].lower() if dex_route else None
    for log in receipt["logs"]:
        topics = [Web3.to_hex(x) for x in log["topics"]]
        if not topics or topics[0] not in {TRANSFER, APPROVAL}:
            continue
        if len(topics) != 3 or any(len(t) != 66 for t in topics):
            unexpected = True
            continue
        sender, recipient = ["0x" + x[-40:] for x in topics[1:]]
        if len(log["data"]) != 32 or any(int(x[2:26], 16) != 0 for x in topics[1:]):
            unexpected = True
            continue
        value = int.from_bytes(log["data"], "big")
        token = log["address"].lower()
        fact = {"token": token, "from": sender, "to": recipient, "value": str(value)}
        if topics[0] == TRANSFER:
            transfers.append(fact)
            if (token, sender, recipient) == (usdc, vault, router):
                outgoing += value
            elif (token, sender, recipient) == (wavax, pair if dex_route else router, vault):
                incoming += value
            elif dex_route and (token, sender, recipient) == (usdc, router, pair):
                downstream_in += value
            else:
                unexpected = True
        else:
            approvals.append(fact)
            allowed_edge = (sender, recipient) == (vault, router) or (
                dex_route and (sender, recipient) == (router, dex_router)
            )
            if token != usdc or not allowed_edge or value not in {0, amount}:
                unauthorized = True
    if dex_route and receipt["status"] == 1 and downstream_in != amount:
        unexpected = True
    if receipt["status"] == 1 and (outgoing != amount or incoming < min_out):
        unexpected = True
    return {
        "token_in_delta_base_units": str(-outgoing),
        "token_out_delta_base_units": str(incoming),
        "unexpected_transfer": unexpected,
        "unauthorized_approval": unauthorized,
        "transfers": transfers,
        "approvals": approvals,
    }


def assess(receipt, trace, before, after, facts, amount, min_out):
    di = int(after["usdc_base_units"]) - int(before["usdc_base_units"])
    do = int(after["wavax_base_units"]) - int(before["wavax_base_units"])
    safe = (
        receipt["status"] == 1
        and di == -amount
        and do >= min_out
        and str(di) == facts["token_in_delta_base_units"]
        and str(do) == facts["token_out_delta_base_units"]
        and after["allowance_base_units"] == "0"
        and not facts["unexpected_transfer"]
        and not facts["unauthorized_approval"]
    )
    rollback = receipt["status"] == 0 and before == after
    return safe, rollback
