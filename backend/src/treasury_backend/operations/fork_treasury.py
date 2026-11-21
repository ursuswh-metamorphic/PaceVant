"""Shared isolated Fuji preparation for CLI verification and the judge adapter.

Only deployment/funding setup lives here. Authorization/proof/sign/relay uses the
existing TreasuryWorkflows and MvpExecution. No public wallet key is loaded.
"""

import json
import time
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlsplit

from eth_account import Account
from pydantic import SecretStr
from web3 import Web3

from treasury_backend.config.control import Settings as ControlSettings
from treasury_backend.config.execution import Settings
from treasury_backend.modules.execution.chain import artifact, contract
from treasury_backend.modules.execution.dex.lfj import LFJClient
from treasury_backend.modules.execution.mvp import MvpExecution
from treasury_backend.modules.execution.simulation.runner import fork_node, rpc
from treasury_backend.modules.oracle.chainlink import ChainlinkPriceProvider
from treasury_backend.modules.workflows.service import ControlPlane
from treasury_backend.modules.workflows.treasury import TreasuryWorkflows
from treasury_backend.operations.execution import send
from treasury_backend.paths import ROOT
from treasury_contracts.crypto import content_hash
from treasury_contracts.mvp import MvpManifest
from treasury_contracts.rpc import evm_web3


def require_isolated_fork(w3):
    if (urlsplit(w3.provider.endpoint_uri).hostname != "127.0.0.1"
            or not w3.client_version.lower().startswith("anvil") or w3.eth.chain_id != 43113):
        raise ValueError("ISOLATED_FORK_REQUIRED")


@contextmanager
def prepared_fork(rpc_url, data, shield, *, provider=None, wait_seconds=0, progress=None, guard_funding=False):
    parsed = urlsplit(rpc_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("PUBLIC_SOURCE_RPC_CONFIGURATION_INVALID")
    progress = progress or (lambda **_: None)
    cfg = json.loads((ROOT / "fixtures/mvp/OWNER_REVIEW_REQUIRED.json").read_text())
    old = json.loads((ROOT / "deployments/treasury-fuji-v2.json").read_text())
    source = Settings(_env_file=None, mode="fuji", rpc_url=rpc_url)
    public = evm_web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout":15}))
    if public.eth.chain_id != 43113:
        raise ValueError("CHAIN_MISMATCH")
    until = time.monotonic() + wait_seconds
    while True:
        height = public.eth.block_number
        observation = {"observed_at": int(time.time()), "source_block": height, "required_remaining_seconds": 90}
        try:
            prices = ChainlinkPriceProvider(rpc_url, old["vault_address"]).read(height)
            avax = next(f for f in prices.oracle_feeds if f.asset == old["token_out"].lower())
            remaining = avax.updated_at + 300 - int(time.time())
            observation.update(updated_at=avax.updated_at, oracle_valid_until=avax.updated_at + 300,
                               remaining_seconds=remaining, source="CHAINLINK_FUJI")
        except Exception:
            remaining = 0
        if remaining >= 90:
            break
        if time.monotonic() >= until:
            raise ValueError("FRESH_CHAINLINK_SIGNING_WINDOW_UNAVAILABLE")
        progress(phase="WAITING_FOR_ORACLE", source_block=height, oracle_observation=observation)
        time.sleep(5)
    source_hash = Web3.to_hex(public.eth.get_block(height).hash)
    progress(phase="PREPARING_FORK", source_block=height, source_block_hash=source_hash)
    data.mkdir(parents=True, exist_ok=True)
    with fork_node(source, height, 43113) as w3:
        require_isolated_fork(w3)
        rpc(w3, "anvil_setBlockTimestampInterval", [0])
        owner, attestor, relayer = (Account.create() for _ in range(3))
        setup = []
        for role, account in (("owner", owner), ("relayer", relayer)):
            rpc(w3, "anvil_setBalance", [account.address, hex(public.eth.get_balance(old[role], height))])

        def tx(fn):
            receipt = send(w3, owner, fn)
            setup.append({"gas_used":str(receipt.gasUsed), "actual_fee_wei":str(receipt.gasUsed * receipt.effectiveGasPrice)})
            return receipt

        def deploy(name, *params):
            compiled = artifact(name)
            factory = w3.eth.contract(abi=compiled["abi"], bytecode=compiled["bytecode"]["object"])
            return w3.eth.contract(address=tx(factory.constructor(*params)).contractAddress, abi=compiled["abi"])

        usdc = contract(w3, "MockUSDC", old["token_in"])
        wavax = contract(w3, "MockWAVAX", old["token_out"])
        vault = deploy("PolicyVaultMVP", owner.address, attestor.address, usdc.address, wavax.address)
        route = LFJClient(w3, usdc.address).v1_route(height)
        adapter = deploy("LFJSwapAdapterV3", vault.address, route["lfj_router"], route["pair"], usdc.address, wavax.address)
        tx(vault.functions.setRouter(adapter.address, True))
        previous = contract(w3, "PolicyVault", old["vault_address"])
        proof = list(previous.functions.proofPolicy().call())
        proof[0] = int(cfg["max_wavax_per_swap"])
        tx(vault.functions.configureProofPolicy(adapter.address, tuple(proof)))
        tx(vault.functions.setApprovalTtl(300))
        tx(vault.functions.configureMVP(int(cfg["max_swap_usd_e8"]), int(cfg["daily_swap_usd_e8"]),
            int(cfg["max_payment_usdc"]), int(cfg["daily_payment_usdc"]), cfg["max_wavax_exposure_bps"]))
        tx(vault.functions.setMvpPayee(owner.address, int(cfg["max_payment_usdc"]),
            int(cfg["recipient_session_usdc"]), int(cfg["recipient_daily_usdc"])))
        now = w3.eth.get_block("latest").timestamp
        tx(vault.functions.configurePolicy(content_hash({"FORK_MVP":vault.address}), int(cfg["max_per_swap_usdc"]),
            int(cfg["max_usdc_daily_outflow"]), previous.functions.maxSlippageBps().call(), now + cfg["policy_duration_seconds"]))
        session = content_hash({"FORK_SESSION":vault.address})
        tx(vault.functions.createSession(session, now, now + cfg["session_duration_seconds"], proof[6]))
        tx(vault.functions.authorizeMvpSession(session, 3, int(cfg["session_swap_usd_e8"]),
            int(cfg["session_payment_usdc"]), cfg["max_actions"], 0))
        donor = Web3.to_checksum_address(old["owner"])
        rpc(w3, "anvil_impersonateAccount", [donor])
        receipt = w3.eth.wait_for_transaction_receipt(usdc.functions.transfer(vault.address, 5 * 10**6).transact({"from":donor}))
        if receipt.status != 1:
            raise ValueError("FORK_FUNDING_FAILED")
        rpc(w3, "anvil_stopImpersonatingAccount", [donor])
        if guard_funding:
            holder = Web3.to_checksum_address(old["vault_address"])
            if wavax.functions.balanceOf(holder).call() >= 5 * 10**13:
                rpc(w3, "anvil_impersonateAccount", [holder])
                rpc(w3, "anvil_setBalance", [holder, hex(10**18)])
                receipt = w3.eth.wait_for_transaction_receipt(wavax.functions.transfer(vault.address, 5 * 10**13).transact({"from":holder}))
                if receipt.status != 1:
                    raise ValueError("FORK_GUARD_FUNDING_FAILED")
                rpc(w3, "anvil_stopImpersonatingAccount", [holder])
        identities = {"treasury":vault.address, "adapter":adapter.address, "usdc":usdc.address, "wavax":wavax.address}
        manifest = MvpManifest(environment="ANVIL_FORK", chain_id=43113, **identities, owner=owner.address,
            attestor=attestor.address, relayer=relayer.address, default_session_id=session, payee_candidates=(owner.address,),
            code_hashes={name:Web3.to_hex(Web3.keccak(w3.eth.get_code(address))) for name, address in identities.items()})
        manifest = manifest.model_copy(update={"owner_signature":Web3.to_hex(owner.sign_message(manifest.signing_message()).signature)})
        settings = source.model_copy(update={"rpc_url":w3.provider.endpoint_uri, "fork_rpc_url":w3.provider.endpoint_uri,
            "data_dir":data / "execution", "relayer_private_key":SecretStr(relayer.key.hex()), "max_ttl":300, "required_confirmations":1})
        execution = MvpExecution(settings, manifest)
        control_settings = replace(ControlSettings(), mode="FUJI", db=data / "control.sqlite3", require_itag=True,
            shield=shield, attestor_key=attestor.key.hex(), chain_rpc_url=settings.rpc_url, relayer_address=manifest.relayer)
        control = ControlPlane(control_settings, client_factory=lambda *_:None, shield_provider=provider)
        try:
            yield SimpleNamespace(workflows=TreasuryWorkflows(control, execution), execution=execution, manifest=manifest,
                source_block=height, source_block_hash=source_hash, setup=setup)
        finally:
            control.close()
