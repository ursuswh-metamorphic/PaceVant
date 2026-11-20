"""Explicit, capped owner top-up for a single tiny demo; never invoked by serving."""

import time

from eth_abi import encode
from web3 import Web3

from treasury_backend.modules.execution.chain import Chain
from treasury_backend.modules.execution.dex.lfj import CIRCLE_USDC, ROUTER, WAVAX, LFJClient, call
from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider

from .env import atomic_json, key_account
from .errors import OpsError
from .fuji_demo import send_setup


def fund_demo(p):
    """Keep the 25% exposure guard; buy only enough Circle USDC for the next 1-unit swap."""
    from treasury_backend.config.execution import Settings

    if p.network != "fuji" or p.web3().eth.chain_id != 43113:
        raise OpsError("Demo funding is restricted to Fuji")
    p.credentials(require_owner_key=True)
    chain = Chain(Settings(_env_file=None, mode="fuji", rpc_url=p.rpc,
                           deployment_file=p.deployment, data_dir=p.execution_data))
    if not chain.is_lfj:
        raise OpsError("Demo funding requires the verified live Circle/LFJ deployment")
    w3 = chain.w3
    vault = chain.vault.address
    owner = key_account(p.values, "B_FUJI_OWNER_PRIVATE_KEY")
    price = ChainlinkPriceProvider(p.rpc, vault).read()
    cash = int(chain.usdc.functions.balanceOf(vault).call())
    wavax = int(chain.wavax.functions.balanceOf(vault).call())
    n = w3.eth.block_number
    dex = LFJClient(w3, CIRCLE_USDC)
    route = dex.v1_route(n)
    out = int(dex.verified_quote(1, n, route)["amount_out_base_units"])
    # After the swap, cash reference value must be >= 3 * WAVAX reference value.
    numerator = 3 * (wavax + out) * int(price.price_wavax_usd_e8)
    denominator = 10**12 * int(price.price_usdc_usd_e8)
    required_cash = (numerator + denominator - 1) // denominator + 1
    needed = max(0, required_cash - cash)
    if not needed:
        return {"status": "ALREADY_FUNDED", "transactions": [], "broadcast": False}
    # A few base units of buffer; never buy for a large strategy or relax exposure.
    deposit = needed + 10
    available = int(call(w3, CIRCLE_USDC, "balanceOf(address)", ("address",), (owner.address,))[0])
    receipts = []
    if available < deposit:
        token_reserve, native_reserve = map(int, route["reserves"])
        if route["token0"].lower() != CIRCLE_USDC.lower():
            token_reserve, native_reserve = native_reserve, token_reserve
        target = (deposit - available) * 101 // 100 + 2
        if target >= token_reserve:
            raise OpsError("Pool cannot supply the demo top-up")
        value = (target * native_reserve * 1000 + 997 * (token_reserve - target) - 1) // (997 * (token_reserve - target))
        if not 0 < value <= 4_000_000_000_000_000:
            raise OpsError("Top-up exceeds 0.004 AVAX cap; obtain Circle faucet USDC instead")
        payload = Web3.keccak(text="swapExactNATIVEForTokens(uint256,(uint256[],uint8[],address[]),address,uint256)")[:4] + encode(
            ["uint256", "(uint256[],uint8[],address[])", "address", "uint256"],
            [deposit - available, ([0], [0], [WAVAX, CIRCLE_USDC]), owner.address, int(time.time()) + 300])
        # This one-time journal is intentionally not rotated automatically on repeat calls.
        receipts.append(send_setup(p, owner, "web-demo-circle-topup-v1", {
            "to": ROUTER, "value": value, "data": Web3.to_hex(payload)}))
    available = int(call(w3, CIRCLE_USDC, "balanceOf(address)", ("address",), (owner.address,))[0])
    if available < deposit:
        raise OpsError("One-time top-up already consumed or insufficient; use Circle faucet, not automatic rebuy")
    payload = Web3.keccak(text="transfer(address,uint256)")[:4] + encode(
        ["address", "uint256"], [vault, deposit])
    receipts.append(send_setup(p, owner, "web-demo-vault-deposit-v1", {
        "to": CIRCLE_USDC, "data": Web3.to_hex(payload)}))
    if int(chain.usdc.functions.balanceOf(vault).call()) < required_cash:
        raise OpsError("One-time journal was already consumed; obtain Circle faucet USDC for further demos")
    result = {"status": "TOPUP_CONFIRMED", "chain_id": 43113, "vault": vault,
              "deposit_usdc_base_units": str(deposit), "native_purchase_cap_wei": "4000000000000000",
              "gas_additional": True, "transactions": receipts, "policy_changed": False}
    atomic_json(p.control_data / "web-demo-funding.json", result)
    return result
