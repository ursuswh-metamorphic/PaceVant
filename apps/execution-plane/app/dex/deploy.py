"""Fuji LFJ deployment defaults to read-only. Broadcasting requires two explicit opt-ins."""

import time
from eth_account import Account
from web3 import Web3

from ..chain import artifact
from ..crypto import content_hash, keccak
from ..errors import PlaneError
from .lfj import ADAPTER_VERSION, CHAIN_ID, LFJClient, ROUTER, USDC, WAVAX, call


def deploy_lfj(settings, *, broadcast=False, fund_amount=0):
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": settings.rpc_timeout}))
    if settings.mode != "fuji" or w3.eth.chain_id != CHAIN_ID:
        raise PlaneError("CHAIN_MISMATCH", "Fuji profile and chain 43113 required")
    preflight = LFJClient(w3).preflight()
    result = {
        "dry_run": not broadcast,
        "broadcast": False,
        "preflight": preflight,
        "required_roles": ["OWNER", "A_SDE_ATTESTOR", "RELAYER"],
        "deployment_file_exists": settings.deployment_file.exists(),
        "risk_status": "BLOCKED_ORACLE_TOKEN_IDENTITY_MISMATCH",
    }
    owner_key = settings.owner_private_key.get_secret_value()
    relayer_key = settings.relayer_private_key.get_secret_value()
    owner = Account.from_key(owner_key) if owner_key else None
    relayer = Account.from_key(relayer_key) if relayer_key else None
    result["funding_checks"] = {
        "owner": owner.address if owner else None,
        "relayer": relayer.address if relayer else None,
        "attestor": settings.attestor_address or None,
        "fund_amount_base_units": str(fund_amount),
    }
    for role, account in [("owner", owner), ("relayer", relayer)]:
        if account:
            result["funding_checks"][role + "_avax_wei"] = str(w3.eth.get_balance(account.address))
    if owner:
        result["funding_checks"]["owner_usdc_base_units"] = str(
            call(w3, USDC, "balanceOf(address)", ("address",), (owner.address,))[0]
        )
    if not broadcast:
        return result
    if not settings.fuji_broadcast_authorized:
        raise PlaneError(
            "BROADCAST_NOT_AUTHORIZED",
            "Set B_FUJI_BROADCAST_AUTHORIZED only after explicit user authorization",
            403,
        )
    if preflight["status"] != "QUOTE_VERIFIED_EXECUTION_NOT_YET_SIMULATED":
        raise PlaneError(preflight["status"], "LFJ route not verified", 409)
    if settings.deployment_file.exists():
        raise PlaneError(
            "DEPLOYMENT_EXISTS",
            "Refuse to overwrite an existing deployment; choose a new manifest path",
            409,
        )
    if not owner or not relayer or not Web3.is_address(settings.attestor_address):
        raise PlaneError(
            "CONFIGURATION_ERROR",
            "Configure separate owner, attestor(public) and relayer test wallets",
            503,
        )
    if (
        len({owner.address.lower(), relayer.address.lower(), settings.attestor_address.lower()})
        != 3
    ):
        raise PlaneError("CONFIGURATION_ERROR", "Owner, attestor and relayer must differ", 503)
    if min(w3.eth.get_balance(a.address) for a in (owner, relayer)) == 0:
        raise PlaneError("INSUFFICIENT_BALANCE", "Owner and relayer need Fuji test AVAX")
    if fund_amount < 0 or fund_amount > int(result["funding_checks"]["owner_usdc_base_units"]):
        raise PlaneError("INSUFFICIENT_BALANCE", "Owner lacks requested LFJ test USDC funding")
    from ..cli import send, save

    receipts = []

    def tx(fn):
        receipt = send(w3, owner, fn)
        receipts.append(
            {
                "tx_hash": Web3.to_hex(receipt.transactionHash),
                "block": receipt.blockNumber,
                "gas_used": str(receipt.gasUsed),
                "status": receipt.status,
            }
        )
        return receipt

    def create(name, args):
        item = artifact(name)
        receipt = tx(
            w3.eth.contract(abi=item["abi"], bytecode=item["bytecode"]["object"]).constructor(*args)
        )
        return w3.eth.contract(address=receipt.contractAddress, abi=item["abi"])

    vault = create("PolicyVault", [owner.address, settings.attestor_address, USDC, WAVAX])
    route = preflight["selected_route"]
    adapter = create("LFJSwapAdapter", [vault.address, ROUTER, route["pair"], USDC, WAVAX])
    tx(vault.functions.setRouter(adapter.address, True))
    tx(
        vault.functions.configurePolicy(
            content_hash(
                {
                    "mandate_id": "mandate_lfj_fuji",
                    "version": 1,
                    "testnet_only": True,
                    "oracle_identity_required": True,
                }
            ),
            500_000_000,
            1_000_000_000,
            100,
            int(time.time()) + 86400,
        )
    )
    token = w3.eth.contract(address=USDC, abi=artifact("IERC20Metadata")["abi"])
    if fund_amount:
        tx(token.functions.transfer(vault.address, fund_amount))
    manifest = {
        "schema_version": "1.1",
        "adapter_version": ADAPTER_VERSION,
        "mode": "fuji",
        "chain_id": CHAIN_ID,
        "vault_address": vault.address,
        "router": adapter.address,
        "token_in": USDC,
        "token_out": WAVAX,
        "owner": owner.address,
        "attestor": settings.attestor_address,
        "relayer": relayer.address,
        "policy_hash": Web3.to_hex(vault.functions.activePolicyHash().call()),
        "deployment_block": w3.eth.block_number,
        "lfj_route": route,
        "bytecode_hashes": {
            name: keccak(w3.eth.get_code(address))
            for name, address in [
                ("PolicyVault", vault.address),
                ("LFJSwapAdapter", adapter.address),
                ("USDC", USDC),
                ("WAVAX", WAVAX),
            ]
        },
        "transactions": receipts,
    }
    save(settings.deployment_file, manifest)
    mandate = {
        "mandate_id": "mandate_lfj_fuji",
        "version": 1,
        "chain_id": CHAIN_ID,
        "vault_address": vault.address,
        "owner": owner.address,
        "router": adapter.address,
        "token_in": USDC,
        "token_out": WAVAX,
        "policy_hash": manifest["policy_hash"],
        "max_usdc_per_swap_base_units": "500000000",
        "max_usdc_spend_per_day_base_units": "1000000000",
        "max_daily_execution_cost_usd_e8": "100000000",
        "max_avax_exposure_bps": 2500,
        "max_slippage_bps": 100,
        "max_replans": 2,
        "expires_at": vault.functions.policyExpiresAt().call(),
        "status": "ACTIVE",
        "required_stress": {
            "reserve_shift_mild": "SUCCESS_REQUIRED",
            "reserve_shift_adverse": "PROTECTED_REVERT_ALLOWED",
        },
    }
    save(settings.data_dir / "mandate-lfj.json", mandate)
    return {
        **result,
        "broadcast": True,
        "deployment": manifest,
        "mandate_file": str(settings.data_dir / "mandate-lfj.json"),
    }
