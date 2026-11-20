"""Explicit disposable V3 bootstrap. Only loopback Anvil chain 31337; no .env access."""

from pathlib import Path
from urllib.parse import urlsplit

from eth_account import Account
from web3 import Web3

from treasury_backend.modules.execution.chain import artifact
from treasury_backend.modules.execution.simulation.runner import rpc
from treasury_backend.operations.execution import send
from treasury_contracts.crypto import content_hash
from treasury_contracts.v3 import Manifest


def deploy_local(w3, settings, root: Path):
    if (
        w3.eth.chain_id != 31337
        or not w3.client_version.lower().startswith("anvil")
        or urlsplit(w3.provider.endpoint_uri).hostname not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError("LOCAL_ANVIL_ONLY")
    root.mkdir(parents=True, exist_ok=True)
    owner, attestor, relayer, payee = (Account.create() for _ in range(4))
    for account in (owner, relayer):
        rpc(w3, "anvil_setBalance", [account.address, hex(100 * 10**18)])

    def deploy(name, *args):
        compiled = artifact(name)
        factory = w3.eth.contract(abi=compiled["abi"], bytecode=compiled["bytecode"]["object"])
        receipt = send(w3, owner, factory.constructor(*args))
        return w3.eth.contract(address=receipt.contractAddress, abi=compiled["abi"])

    u, w = deploy("MockUSDC", owner.address), deploy("MockWAVAX", owner.address)
    v = deploy("PolicyVaultV3", owner.address, attestor.address, u.address, w.address)
    adapter = deploy("MockSwapAdapter", owner.address, u.address, w.address)
    shares = deploy("DemoERC4626", u.address)
    send(w3, owner, v.functions.setRouter(adapter.address, True))
    send(
        w3,
        owner,
        v.functions.configureProofPolicy(
            adapter.address,
            (
                10 * 10**18,
                300,
                0,
                100,
                40,
                180,
                100 * 10**8,
                200 * 10**8,
                Web3.keccak(text="LOCAL_TEST_REFERENCE_ONLY"),
                False,
            ),
        ),
    )
    send(w3, owner, v.functions.setApprovalTtl(180))
    send(
        w3,
        owner,
        v.functions.configureV3(
            shares.address,
            990000,
            1010000,
            200 * 10**8,
            1000 * 10**8,
            200 * 10**6,
            1000 * 10**6,
            2500,
        ),
    )
    send(w3, owner, v.functions.setPayee(u.address, payee.address, 25 * 10**6, 50 * 10**6))
    send(w3, owner, v.functions.setPayee(w.address, payee.address, 10**18, 2 * 10**18))
    send(w3, owner, v.functions.setPayee("0x" + "00" * 20, payee.address, 10**17, 2 * 10**17))
    now = w3.eth.get_block("latest").timestamp
    send(
        w3,
        owner,
        v.functions.configurePolicy(
            content_hash({"LOCAL_V3": v.address}), 200 * 10**6, 1000 * 10**6, 100, now + 86400
        ),
    )
    session_id = content_hash({"LOCAL_SESSION": v.address})
    send(w3, owner, v.functions.createSession(session_id, now, now + 3600, 100 * 10**8))
    send(w3, owner, v.functions.authorizeSession(session_id, 31, 500 * 10**8, 10, 60))
    send(w3, owner, u.functions.mint(v.address, 1000 * 10**6))
    send(w3, owner, w.functions.mint(adapter.address, 10000 * 10**18))
    send(w3, owner, u.functions.mint(adapter.address, 100000 * 10**6))
    identities = {
        "treasury": v.address,
        "usdc": u.address,
        "wavax": w.address,
        "shares": shares.address,
        "adapter": adapter.address,
    }
    manifest = Manifest(
        environment="LOCAL",
        chain_id=31337,
        owner=owner.address,
        attestor=attestor.address,
        relayer=relayer.address,
        default_session_id=session_id,
        payee_candidates=(payee.address,),
        **identities,
        code_hashes={
            k: Web3.to_hex(Web3.keccak(w3.eth.get_code(a))) for k, a in identities.items()
        },
    )
    manifest = manifest.model_copy(
        update={
            "owner_signature": Web3.to_hex(owner.sign_message(manifest.signing_message()).signature)
        }
    )
    (root / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    # Keys are returned in memory only; never added to the manifest, logs, API or evidence.
    configured = settings.model_copy(
        update={
            "relayer_private_key": type(settings.relayer_private_key)(relayer.key.hex()),
            "max_ttl": 180,
        }
    )
    return {
        "manifest": manifest,
        "settings": configured,
        "owner": owner,
        "attestor": attestor,
        "relayer": relayer,
        "payee": payee.address.lower(),
        "session_id": session_id,
        "contracts": (v, u, w, adapter, shares),
    }
