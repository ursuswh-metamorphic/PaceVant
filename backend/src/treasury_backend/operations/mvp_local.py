"""Three-EOA local test deployment. Never loads owner secrets or writes to public RPCs."""

from pathlib import Path
from urllib.parse import urlsplit

from eth_account import Account
from web3 import Web3

from treasury_backend.modules.execution.chain import artifact
from treasury_backend.modules.execution.simulation.runner import rpc
from treasury_backend.operations.execution import send
from treasury_contracts.crypto import content_hash
from treasury_contracts.mvp import MvpManifest


def deploy_mvp_local(w3, settings, root: Path):
    if (
        w3.eth.chain_id != 31337
        or not w3.client_version.lower().startswith("anvil")
        or urlsplit(w3.provider.endpoint_uri).hostname not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError("LOCAL_ANVIL_ONLY")
    root.mkdir(parents=True, exist_ok=True)
    owner, attestor, relayer = (Account.create() for _ in range(3))
    for account in (owner, relayer):
        rpc(w3, "anvil_setBalance", [account.address, hex(10**20)])

    def deploy(name, *args):
        a = artifact(name)
        factory = w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"]["object"])
        receipt = send(w3, owner, factory.constructor(*args))
        return w3.eth.contract(address=receipt.contractAddress, abi=a["abi"])

    u, w = deploy("MockUSDC", owner.address), deploy("MockWAVAX", owner.address)
    v = deploy("PolicyVaultMVP", owner.address, attestor.address, u.address, w.address)
    adapter = deploy("MockSwapAdapter", owner.address, u.address, w.address)
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
        v.functions.configureMVP(200 * 10**8, 1000 * 10**8, 25 * 10**6, 100 * 10**6, 2500),
    )
    send(w3, owner, v.functions.setMvpPayee(owner.address, 25 * 10**6, 50 * 10**6, 100 * 10**6))
    now = w3.eth.get_block("latest").timestamp
    send(
        w3,
        owner,
        v.functions.configurePolicy(
            content_hash({"LOCAL_MVP": v.address}), 200 * 10**6, 1000 * 10**6, 100, now + 86400
        ),
    )
    session = content_hash({"LOCAL_MVP_SESSION": v.address})
    send(w3, owner, v.functions.createSession(session, now, now + 3600, 100 * 10**8))
    send(w3, owner, v.functions.authorizeMvpSession(session, 19, 500 * 10**8, 50 * 10**6, 10, 60))
    send(w3, owner, u.functions.mint(v.address, 1000 * 10**6))
    send(w3, owner, u.functions.mint(adapter.address, 100000 * 10**6))
    send(w3, owner, w.functions.mint(adapter.address, 10000 * 10**18))
    ids = {"treasury": v.address, "usdc": u.address, "wavax": w.address, "adapter": adapter.address}
    m = MvpManifest(
        environment="LOCAL_TEST",
        chain_id=31337,
        **ids,
        owner=owner.address,
        attestor=attestor.address,
        relayer=relayer.address,
        default_session_id=session,
        payee_candidates=(owner.address,),
        code_hashes={k: Web3.to_hex(Web3.keccak(w3.eth.get_code(a))) for k, a in ids.items()},
    )
    m = m.model_copy(
        update={"owner_signature": Web3.to_hex(owner.sign_message(m.signing_message()).signature)}
    )
    (root / "mvp-manifest.json").write_text(m.model_dump_json(indent=2), encoding="utf-8")
    configured = settings.model_copy(
        update={
            "relayer_private_key": type(settings.relayer_private_key)(relayer.key.hex()),
            "max_ttl": 180,
        }
    )
    return {
        "manifest": m,
        "settings": configured,
        "owner": owner,
        "attestor": attestor,
        "relayer": relayer,
        "payee": owner.address.lower(),
        "session_id": session,
        "contracts": (v, u, w, adapter),
    }
