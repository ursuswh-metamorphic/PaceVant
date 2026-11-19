"""Model order flow with a preceding guarded swap on isolated Anvil."""

from urllib.parse import urlsplit

from web3 import Web3

from ..crypto import keccak
from ..dex.lfj import LFJClient, CIRCLE_USDC, ROUTER, WAVAX, call
from ..errors import PlaneError


def prepare_ordered_swap(w3, vault, adapter, usdc, built, context, signer, relayer, scenario_id):
    from .runner import exploratory_call, rpc

    endpoint = urlsplit(w3.provider.endpoint_uri)
    if endpoint.hostname != "127.0.0.1" or not w3.client_version.lower().startswith("anvil"):
        raise PlaneError("SIMULATION_INCOMPLETE", "LFJ stress requires isolated loopback Anvil")
    timestamp = context["timestamp"]

    client = LFJClient(w3, usdc.address)
    route = client.v1_route(w3.eth.block_number)
    reserves = list(map(int, route["reserves"]))
    reserve_in = reserves[0] if route["token0"].lower() == usdc.address.lower() else reserves[1]
    # Approximate a 20/200-bps subsequent quote shift using a genuine preceding swap.
    impact_bps = 20 if scenario_id == "reserve_shift_mild" else 200
    amount = max(1, reserve_in * impact_bps // 20_000)
    initial_quote = adapter.functions.quote(
        built.token_in, built.token_out, int(built.amount_in_base_units)
    ).call()
    if usdc.address == CIRCLE_USDC:
        return external_circle_swap(w3, usdc, adapter, built, amount, impact_bps, initial_quote, timestamp)
    balance = usdc.functions.balanceOf(built.vault_address).call()
    day = timestamp // 86400
    budget = vault.functions.maxSpendPerDay().call() - vault.functions.dailySpentUsdc(day).call()
    if amount > vault.functions.maxPerSwap().call() or amount + int(
        built.amount_in_base_units
    ) > min(balance, budget):
        return {
            "kind": "FORK_PRECEDING_GUARDED_SWAP",
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
    _, encoded = exploratory_call(vault, earlier, context, signer)
    rpc(w3, "evm_setNextBlockTimestamp", [timestamp + 1])
    tx = {
        "to": built.vault_address,
        "data": encoded,
        "from": relayer.address,
        "chainId": built.chain_id,
        "nonce": w3.eth.get_transaction_count(relayer.address),
        "gas": 1_500_000,
        "gasPrice": w3.eth.gas_price,
    }
    signed = relayer.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction), timeout=30
    )
    after_quote = adapter.functions.quote(
        built.token_in, built.token_out, int(built.amount_in_base_units)
    ).call()
    achieved = max(0, (initial_quote - after_quote) * 10000 // initial_quote)
    return {
        "kind": "FORK_PRECEDING_GUARDED_SWAP",
        "status": "READY"
        if receipt.status == 1 and achieved >= impact_bps * 9 // 10
        else "INCONCLUSIVE",
        "tx_hash": Web3.to_hex(receipt.transactionHash),
        "amount_base_units": str(amount),
        "target_quote_shift_bps": impact_bps,
        "achieved_quote_shift_bps": achieved,
        "before_quote": str(initial_quote),
        "after_quote": str(after_quote),
        "note": "Earlier swap used the ephemeral fork attestor and the treasury's pinned token balance.",
    }


def external_circle_swap(w3, usdc, adapter, built, amount, impact_bps, initial_quote, timestamp):
    """Counterfactual external order flow, ONLY on the isolated Anvil fork.

    Circle's existing mint functions provision the scenario actor. Historical vault
    balances, policy/session counters, feed rounds and DEX bytecode stay untouched.
    This setup is hypothetical stress input, never baseline/live funding evidence.
    """
    from eth_abi import encode
    from eth_account import Account
    from .runner import rpc

    # Recheck at this mutation boundary; never impersonate on a public source RPC.
    endpoint = urlsplit(w3.provider.endpoint_uri)
    if endpoint.hostname != "127.0.0.1" or not w3.client_version.lower().startswith("anvil"):
        raise PlaneError("SIMULATION_INCOMPLETE", "External actor requires isolated Anvil")
    actor = Account.create().address
    master = Web3.to_checksum_address(call(w3, usdc.address, "masterMinter()", returns=("address",))[0])
    vault_before = usdc.functions.balanceOf(built.vault_address).call()
    transactions = []

    def transact(sender, target, signature, types, values):
        data = Web3.keccak(text=signature)[:4] + encode(types, values)
        tx = rpc(w3, "eth_sendTransaction", [{"from": sender, "to": target,
                 "data": Web3.to_hex(data), "gas": hex(1_000_000)}])
        receipt = w3.eth.wait_for_transaction_receipt(tx, timeout=15)
        if receipt.status != 1:
            raise PlaneError("SIMULATION_INCOMPLETE", "Counterfactual external trade failed")
        transactions.append(Web3.to_hex(receipt.transactionHash))

    for address in (master, actor):
        rpc(w3, "anvil_setBalance", [address, hex(10**18)])
        rpc(w3, "anvil_impersonateAccount", [address])
    try:
        # Same logical second for setup, followed by guarded execution at pinned t+2.
        rpc(w3, "anvil_setBlockTimestampInterval", [0])
        rpc(w3, "evm_setNextBlockTimestamp", [timestamp + 1])
        transact(master, usdc.address, "configureMinter(address,uint256)", ("address", "uint256"), (actor, amount))
        transact(actor, usdc.address, "mint(address,uint256)", ("address", "uint256"), (actor, amount))
        transact(actor, usdc.address, "approve(address,uint256)", ("address", "uint256"), (ROUTER, amount))
        path = ([0], [0], [usdc.address, WAVAX])
        transact(actor, ROUTER, "swapExactTokensForTokens(uint256,uint256,(uint256[],uint8[],address[]),address,uint256)",
                 ("uint256", "uint256", "(uint256[],uint8[],address[])", "address", "uint256"),
                 (amount, 1, path, actor, built.deadline))
    finally:
        for address in (master, actor):
            rpc(w3, "anvil_stopImpersonatingAccount", [address])
    if usdc.functions.balanceOf(built.vault_address).call() != vault_before:
        raise PlaneError("SIMULATION_INCOMPLETE", "Stress setup mutated vault balance")
    after_quote = adapter.functions.quote(built.token_in, built.token_out, int(built.amount_in_base_units)).call()
    achieved = max(0, (initial_quote - after_quote) * 10000 // initial_quote)
    return {
        "kind": "COUNTERFACTUAL_EXTERNAL_MARKET_SWAP", "source_writes": False,
        "status": "READY" if achieved >= impact_bps * 9 // 10 else "INCONCLUSIVE",
        "amount_base_units": str(amount), "target_quote_shift_bps": impact_bps,
        "achieved_quote_shift_bps": achieved, "before_quote": str(initial_quote),
        "after_quote": str(after_quote), "transactions": transactions,
        "actor": actor, "hypothetical_actor_funding": "CIRCLE_MINTER_IMPERSONATION_ON_ANVIL_ONLY",
        "vault_balance_modified_by_setup": False,
    }
