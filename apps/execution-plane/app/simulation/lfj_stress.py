"""Real order-flow on an isolated fork, not storage-edited pools or a claim of real MEV."""

from eth_account import Account
from web3 import Web3

from ..crypto import approval_for, approval_tuple, content_hash, domain_for, keccak, message
from ..dex.lfj import LFJClient, USDC
from ..errors import PlaneError


def prepare_ordered_swap(w3, vault, adapter, usdc, built, signer, relayer, scenario_id, timestamp):
    from .runner import rpc

    client = LFJClient(w3)
    route = client.v1_route(w3.eth.block_number)
    reserves = list(map(int, route["reserves"]))
    reserve_in = reserves[0] if route["token0"].lower() == USDC.lower() else reserves[1]
    # Approximate a 20/200-bps subsequent quote shift using a genuine preceding swap.
    impact_bps = 20 if scenario_id == "reserve_shift_mild" else 200
    amount = max(1, reserve_in * impact_bps // 20_000)
    initial_quote = adapter.functions.quote(
        built.token_in, built.token_out, int(built.amount_in_base_units)
    ).call()
    balance = usdc.functions.balanceOf(built.vault_address).call()
    day = timestamp // 86400
    budget = vault.functions.maxSpendPerDay().call() - vault.functions.dailySpentUsdc(day).call()
    if amount > vault.functions.maxPerSwap().call() or amount + int(
        built.amount_in_base_units
    ) > min(balance, budget):
        return {
            "kind": "FORK_PRECEDING_AUTHORIZED_VAULT_SWAP",
            "status": "INCONCLUSIVE",
            "reason": "INSUFFICIENT_UNMODIFIED_TREASURY_FOR_STRESS",
            "amount_base_units": str(amount),
            "target_quote_shift_bps": impact_bps,
        }
    quoted = adapter.functions.quote(built.token_in, built.token_out, amount).call()
    minimum = max(1, quoted * 9990 // 10000)
    nonce = int(built.nonce) + (1_000_000 if impact_bps == 20 else 2_000_000)
    if vault.functions.usedNonce(nonce).call():
        raise PlaneError("SIMULATION_INCOMPLETE", "Stress nonce already used", 409)
    data = adapter.encode_abi(
        "exactInput", args=[built.token_in, built.token_out, amount, minimum, built.vault_address]
    )
    earlier = built.model_copy(
        update={
            "amount_in_base_units": str(amount),
            "min_amount_out_base_units": str(minimum),
            "nonce": str(nonce),
            "router_calldata": data,
            "calldata_hash": keccak(Web3.to_bytes(hexstr=data)),
        }
    )
    approval = approval_for(earlier, content_hash({"fork_stress_only": scenario_id}))
    signature = Account.sign_message(message(domain_for(earlier), approval), signer.key).signature
    rpc(w3, "evm_setNextBlockTimestamp", [timestamp + 1])
    fn = vault.functions.executeApprovedSwap(approval_tuple(approval), data, signature)
    tx = fn.build_transaction(
        {
            "from": relayer.address,
            "chainId": built.chain_id,
            "nonce": w3.eth.get_transaction_count(relayer.address),
            "gas": 1_500_000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = relayer.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction), timeout=30
    )
    after_quote = adapter.functions.quote(
        built.token_in, built.token_out, int(built.amount_in_base_units)
    ).call()
    achieved = max(0, (initial_quote - after_quote) * 10000 // initial_quote)
    return {
        "kind": "FORK_PRECEDING_AUTHORIZED_VAULT_SWAP",
        "status": "READY"
        if receipt.status == 1 and achieved >= impact_bps * 9 // 10
        else "INCONCLUSIVE",
        "tx_hash": Web3.to_hex(receipt.transactionHash),
        "amount_base_units": str(amount),
        "target_quote_shift_bps": impact_bps,
        "achieved_quote_shift_bps": achieved,
        "before_quote": str(initial_quote),
        "after_quote": str(after_quote),
        "note": "Earlier transaction by this treasury, signed by fork-only attestor. No external actor or real MEV claim; no pool/token storage edits.",
    }
