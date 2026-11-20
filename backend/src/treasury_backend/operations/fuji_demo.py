"""Small, resumable Fuji demonstration. Owner operations never run in the API."""

import json
import time
from decimal import Decimal

from web3 import Web3

from treasury_backend.core.errors import ControlError
from treasury_backend.modules.execution.dex.lfj import CIRCLE_USDC, ROUTER, WAVAX, LFJClient, call
from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
from treasury_contracts.oracle import CHAINLINK_SOURCE

from .contracts import deploy_v2, deployed
from .env import atomic_json, key_account
from .errors import OpsError
from .profiles import owner_config

BOOTSTRAP_WEI = 8_000_000_000_000_000  # 0.008 test AVAX; native value, excluding gas.
RELAYER_WEI = 2_000_000_000_000_000  # 0.002 test AVAX, retained by the user's relayer.


def wait_for_oracle_window(p, *, wait_seconds=300):
    """Wait before creating an intent; never restamp a round or relax its age policy."""
    if p.network != "fuji" or p.values.get("TREASURY_ORACLE_MODE") != "chainlink":
        return
    data = json.loads(p.deployment.read_text(encoding="utf-8"))
    provider = ChainlinkPriceProvider(p.rpc, data["vault_address"])
    required = min(300, int(p.values.get("TREASURY_APPROVAL_TTL_SECONDS", "30")))
    end = time.monotonic() + wait_seconds
    while True:
        try:
            value = provider.read()
            now = int(time.time())
            headroom = min(f.max_age_seconds - (now - f.updated_at) for f in value.oracle_feeds)
        except ControlError as error:
            if error.code != "STALE_OR_UNVERIFIED_CHAINLINK_PRICE":
                raise
            # A round can cross its age limit just before its replacement arrives.
            # No intent exists yet; wait only for a fully validated replacement.
            headroom = -1
        if headroom >= required:
            return
        remaining = end - time.monotonic()
        if remaining <= 0:
            raise OpsError("Chainlink round has insufficient remaining freshness for this demo; retry after a new round")
        print(json.dumps({"stage": "WAITING_FOR_FRESH_CHAINLINK_ROUND",
                          "remaining_feed_freshness_seconds": headroom,
                          "required_seconds": required}), flush=True)
        time.sleep(min(15, remaining))


def send_setup(p, account, label, tx):
    """Journal signed bytes before broadcast; resume a timed-out write by hash."""
    w3 = p.web3()
    folder = p.control_data / "fuji-setup"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (label + ".json")
    if path.exists():
        journal = json.loads(path.read_text())
        if journal["sender"].lower() != account.address.lower():
            raise OpsError("Setup journal sender mismatch")
    else:
        tx = dict(tx, **{"from": account.address, "to": Web3.to_checksum_address(tx["to"]), "chainId": 43113,
                       "nonce": w3.eth.get_transaction_count(account.address, "pending"),
                       "gasPrice": w3.eth.gas_price})
        tx["gas"] = w3.eth.estimate_gas(tx) * 12 // 10 + 10000
        if w3.eth.get_balance(account.address) < tx.get("value", 0) + tx["gas"] * tx["gasPrice"]:
            raise OpsError("Insufficient owner test AVAX for setup and gas")
        signed = account.sign_transaction(tx)
        journal = {"label": label, "sender": account.address, "chain_id": 43113,
                   "tx_hash": Web3.to_hex(signed.hash), "raw_tx": Web3.to_hex(signed.raw_transaction)}
        atomic_json(path, journal)
    try:
        w3.eth.get_transaction(journal["tx_hash"])
    except Exception:
        w3.eth.send_raw_transaction(Web3.to_bytes(hexstr=journal["raw_tx"]))
    receipt = w3.eth.wait_for_transaction_receipt(journal["tx_hash"], timeout=90)
    if receipt.status != 1:
        raise OpsError("Fuji setup reverted: " + label)
    public = {"label": label, "sender": account.address, "tx_hash": journal["tx_hash"],
              "block_number": receipt.blockNumber, "gas_used": receipt.gasUsed}
    atomic_json(path, journal | {"receipt": public})
    return public


def bootstrap(p):
    if p.network != "fuji" or p.chain_id != p.web3().eth.chain_id:
        raise OpsError("Fuji bootstrap requires chain 43113")
    p.credentials(require_owner_key=True)
    if p.values.get("TREASURY_ORACLE_MODE") != "chainlink" or p.values.get("TREASURY_ORACLE_SOURCE_ID") != CHAINLINK_SOURCE:
        raise OpsError("Fuji live demo requires TREASURY_ORACLE_MODE=chainlink and reviewed source ID")
    owner_config(p.values)
    owner = key_account(p.values, "B_FUJI_OWNER_PRIVATE_KEY")
    relayer = key_account(p.values, "B_FUJI_RELAYER_PRIVATE_KEY")
    w3 = p.web3()
    # Fail before any writes if exact feeds/route are unavailable or stale.
    ChainlinkPriceProvider(p.rpc, owner.address).read()
    dex = LFJClient(w3, CIRCLE_USDC)
    route = dex.v1_route(w3.eth.block_number)
    receipts = []
    if not p.deployment.exists():
        deploy_v2(p, adapter="lfj")
    data, w3, _ = deployed(p)
    if (data["token_in"], data["token_out"]) != (CIRCLE_USDC, WAVAX):
        raise OpsError("Existing deployment is not the Circle USDC/WAVAX live route")
    # Deployment and independently verified adapter must be valid before token funding.
    from treasury_backend.config.execution import Settings
    from treasury_backend.modules.execution.chain import Chain
    Chain(Settings(_env_file=None, mode="fuji", rpc_url=p.rpc, deployment_file=p.deployment, data_dir=p.execution_data))
    if w3.eth.get_balance(relayer.address) < RELAYER_WEI // 2:
        receipts.append(send_setup(p, owner, "relayer-gas-v1", {"to": relayer.address, "value": RELAYER_WEI}))
    vault = Web3.to_checksum_address(data["vault_address"])
    amount = call(w3, CIRCLE_USDC, "balanceOf(address)", ("address",), (vault,))[0]
    if amount == 0:
        available = call(w3, CIRCLE_USDC, "balanceOf(address)", ("address",), (owner.address,))[0]
        if available == 0:
            n = w3.eth.block_number
            route = dex.v1_route(n)
            ri, ro = map(int, route["reserves"])
            if route["token0"].lower() == CIRCLE_USDC.lower():
                ri, ro = ro, ri
            quote = BOOTSTRAP_WEI * 997 * ro // (ri * 1000 + BOOTSTRAP_WEI * 997)
            if quote < 10:
                raise OpsError("Pool cannot bootstrap enough tokens inside 0.008 test AVAX; obtain Circle faucet USDC")
            from eth_abi import encode
            signature = "swapExactNATIVEForTokens(uint256,(uint256[],uint8[],address[]),address,uint256)"
            payload = Web3.keccak(text=signature)[:4] + encode(
                ["uint256", "(uint256[],uint8[],address[])", "address", "uint256"],
                [max(1, quote * 9900 // 10000), ([0], [0], [WAVAX, CIRCLE_USDC]), owner.address, int(time.time()) + 300],
            )
            receipts.append(send_setup(p, owner, "bootstrap-circle-v1", {"to": ROUTER, "value": BOOTSTRAP_WEI, "data": Web3.to_hex(payload)}))
            available = call(w3, CIRCLE_USDC, "balanceOf(address)", ("address",), (owner.address,))[0]
        from eth_abi import encode
        amount = min(available, 10000)
        payload = Web3.keccak(text="transfer(address,uint256)")[:4] + encode(["address", "uint256"], [vault, amount])
        receipts.append(send_setup(p, owner, "vault-deposit-" + vault.lower(), {"to": CIRCLE_USDC, "data": Web3.to_hex(payload)}))
    result = {"chain_id": 43113, "vault": vault, "setup_transactions": receipts,
              "vault_usdc_base_units": str(amount), "native_bootstrap_cap_wei": str(BOOTSTRAP_WEI),
              "relayer_transfer_cap_wei": str(RELAYER_WEI), "gas_is_additional": True}
    atomic_json(p.control_data / "fuji-setup-summary.json", result)
    return result


def select_goal(p):
    """Pick a genuine small trade within owner exposure limits, not a fixed 200 USDC."""
    data, w3, _ = deployed(p)
    vault = Web3.to_checksum_address(data["vault_address"])
    value = ChainlinkPriceProvider(p.rpc, vault).read()
    balance = call(w3, CIRCLE_USDC, "balanceOf(address)", ("address",), (vault,))[0]
    wavax = call(w3, WAVAX, "balanceOf(address)", ("address",), (vault,))[0]
    dex = LFJClient(w3, CIRCLE_USDC)
    n = w3.eth.block_number
    route = dex.v1_route(n)
    for amount in (1,):
        if amount > balance:
            continue
        quoted = int(dex.verified_quote(amount, n, route)["amount_out_base_units"])
        avax_value = (wavax + quoted) * int(value.price_wavax_usd_e8)
        cash_value = (balance - amount) * 10**12 * int(value.price_usdc_usd_e8)
        if avax_value * 10000 <= 2500 * (avax_value + cash_value):
            return "Buy WAVAX with " + format(Decimal(amount) / 10**6, "f") + " USDC"
    raise OpsError("Vault needs more Circle test USDC to keep WAVAX exposure <=25%; use Circle faucet or fund the vault. No policy bypass attempted.")
